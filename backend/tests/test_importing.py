import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.importing import ImportService
from tests.conftest import FakeLLMProvider
from tests.helpers import create_workspace


def _settings(tmp_path: Path, *, allow_private: bool = True) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'import.db'}",
        upload_dir=tmp_path / "uploads",
        llm_provider="offline",
        embedding_provider="offline",
        import_allow_private_hosts=allow_private,
        import_timeout_seconds=5,
    )


@contextmanager
def _html_server(html: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/apuntes"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_import_html_url_creates_ready_material(tmp_path):
    html = """
    <html><head><title>Tema de redes</title><script>ignorar()</script></head>
    <body><h1>Modelo OSI</h1><p>La capa de transporte usa TCP o UDP.</p></body></html>
    """
    app = create_app(settings=_settings(tmp_path), provider=FakeLLMProvider())
    with _html_server(html) as url, TestClient(app) as client:
        workspace_id = create_workspace(client)
        response = client.post(
            f"/api/workspaces/{workspace_id}/materials/import", json={"url": url}
        )
        assert response.status_code == 201, response.text
        material = response.json()[0]
        assert material["status"] == "ready"
        assert material["filename"] == "Tema_de_redes.txt"
        assert material["chunk_count"] >= 1

        detail = client.get(
            f"/api/workspaces/{workspace_id}/materials/{material['id']}"
        ).json()
        assert "Modelo OSI" in detail["preview"]
        assert "TCP o UDP" in detail["preview"]
        assert "ignorar" not in detail["preview"]


def test_import_blocks_private_hosts_by_default(tmp_path):
    app = create_app(
        settings=_settings(tmp_path, allow_private=False), provider=FakeLLMProvider()
    )
    with _html_server("<p>no</p>") as url, TestClient(app) as client:
        workspace_id = create_workspace(client)
        response = client.post(
            f"/api/workspaces/{workspace_id}/materials/import", json={"url": url}
        )
        assert response.status_code == 400
        assert "privadas" in response.json()["error"]["message"]


def test_ocr_image_uses_optional_extractor(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.parsing.ocr.ocr_image",
        lambda path, *, language: f"texto OCR de {path.name}",
    )
    app = create_app(settings=_settings(tmp_path), provider=FakeLLMProvider())
    with TestClient(app) as client:
        workspace_id = create_workspace(client)
        response = client.post(
            f"/api/workspaces/{workspace_id}/materials",
            files={"files": ("escaneo.png", b"\x89PNG fake", "image/png")},
        )
        assert response.status_code == 201, response.text
        material = response.json()[0]
        assert material["status"] == "ready"
        assert "texto OCR" in client.get(
            f"/api/workspaces/{workspace_id}/materials/{material['id']}"
        ).json()["preview"]


def test_youtube_import_uses_captions(tmp_path, monkeypatch):
    watch_page = (
        '<html><head><title>Clase de álgebra</title></head><body>'
        '"captionTracks":[{"languageCode":"es","baseUrl":'
        '"https://www.youtube.com/api/timedtext?v=abc12345678&lang=es"}]'
        "</body></html>"
    )
    captions = (
        '{"events":[{"segs":[{"utf8":"Primera línea"}]},'
        '{"segs":[{"utf8":"Segunda línea"}]}]}'
    )

    def fake_fetch(self, url):
        from app.services.importing import _FetchedDocument

        if "timedtext" in url:
            return _FetchedDocument(url, "application/json", captions.encode(), "utf-8")
        return _FetchedDocument(url, "text/html", watch_page.encode(), "utf-8")

    monkeypatch.setattr(ImportService, "_fetch", fake_fetch)
    app = create_app(settings=_settings(tmp_path), provider=FakeLLMProvider())
    with TestClient(app) as client:
        workspace_id = create_workspace(client)
        response = client.post(
            f"/api/workspaces/{workspace_id}/materials/import",
            json={"url": "https://www.youtube.com/watch?v=abc12345678"},
        )
        assert response.status_code == 201, response.text
        material = response.json()[0]
        assert material["status"] == "ready"
        detail = client.get(
            f"/api/workspaces/{workspace_id}/materials/{material['id']}"
        ).json()
        assert "Clase de álgebra" in detail["preview"]
        assert "Primera línea" in detail["preview"]


def test_youtube_without_captions_returns_clear_error(tmp_path, monkeypatch):
    def fake_fetch(self, url):
        from app.services.importing import _FetchedDocument

        return _FetchedDocument(url, "text/html", b"<title>Sin pistas</title>", "utf-8")

    monkeypatch.setattr(ImportService, "_fetch", fake_fetch)
    app = create_app(settings=_settings(tmp_path), provider=FakeLLMProvider())
    with TestClient(app) as client:
        workspace_id = create_workspace(client)
        response = client.post(
            f"/api/workspaces/{workspace_id}/materials/import",
            json={"url": "https://youtu.be/abc12345678"},
        )
        assert response.status_code == 422
        assert "subtítulos" in response.json()["error"]["message"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://youtu.be/abc12345678", "abc12345678"),
        ("https://www.youtube.com/shorts/abc12345678", "abc12345678"),
        ("https://example.com/watch?v=abc12345678", None),
    ],
)
def test_youtube_url_detection(url, expected):
    from app.services.importing import _youtube_video_id

    assert _youtube_video_id(url) == expected


def test_youtube_host_detection_is_strict():
    from app.services.importing import _youtube_video_id

    video = "dQw4w9WgXcQ"
    assert _youtube_video_id(f"https://www.youtube.com/watch?v={video}") == video
    assert _youtube_video_id(f"https://youtu.be/{video}") == video
    assert _youtube_video_id(f"https://notyoutube.com/watch?v={video}") is None
    assert _youtube_video_id(f"https://youtube.com.evil.test/watch?v={video}") is None
