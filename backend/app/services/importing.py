import ipaddress
import json
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ImportBlockedError, ImportFailedError, NotFoundError
from app.repositories.workspaces import get_workspace
from app.schemas.material import MaterialRead
from app.services.background import BackgroundQueue
from app.services.ingestion import IncomingFile, MaterialService

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ExamForge/1.0"
)
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_MAX_REDIRECTS = 5


@dataclass(frozen=True)
class _FetchedDocument:
    url: str
    content_type: str
    content: bytes
    encoding: str | None

    @property
    def text(self) -> str:
        for encoding in (self.encoding, "utf-8", "latin-1"):
            if not encoding:
                continue
            try:
                return self.content.decode(encoding)
            except (LookupError, UnicodeDecodeError):
                continue
        return self.content.decode("utf-8", errors="replace")


class _HtmlTextExtractor(HTMLParser):
    _SKIPPED_TAGS = {"script", "style", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIPPED_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip_depth:
            self.text_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join("".join(self.title_parts).split())

    @property
    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.text_parts).splitlines()]
        return "\n".join(line for line in lines if line)


class ImportService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        queue: BackgroundQueue | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.queue = queue
        self.session_factory = session_factory

    def _material_service(self) -> MaterialService:
        return MaterialService(
            self.session,
            self.settings,
            queue=self.queue,
            session_factory=self.session_factory,
        )

    def import_url(self, workspace_id: str, url: str) -> list[MaterialRead]:
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")
        url = url.strip()
        video_id = _youtube_video_id(url)
        if video_id:
            title, text = self._youtube_transcript(video_id)
            filename = f"{_safe_stem(title) or video_id}.txt"
            content = self._truncate(f"{title}\n\n{text}").strip().encode("utf-8")
            return self._material_service().add_files(
                workspace_id,
                [
                    IncomingFile(
                        filename=filename,
                        content_type="text/plain; charset=utf-8",
                        data=content,
                    )
                ],
            )

        fetched = self._fetch(url)
        content_type = fetched.content_type.split(";", 1)[0].strip().lower()
        if content_type in {"text/html", "application/xhtml+xml"} or not content_type:
            parser = _HtmlTextExtractor()
            parser.feed(fetched.text)
            text = self._truncate(parser.text)
            if not text:
                raise ImportFailedError("La página no contiene texto legible")
            title = parser.title or _filename_from_url(fetched.url)
            filename = f"{_safe_stem(title) or 'importado'}.txt"
            return self._material_service().add_files(
                workspace_id,
                [
                    IncomingFile(
                        filename=filename,
                        content_type="text/plain; charset=utf-8",
                        data=text.encode("utf-8"),
                    )
                ],
            )

        filename = _filename_from_url(fetched.url)
        if not Path(filename).suffix:
            filename = f"{filename}.{_extension_for(content_type)}"
        return self._material_service().add_files(
            workspace_id,
            [
                IncomingFile(
                    filename=filename,
                    content_type=content_type,
                    data=fetched.content,
                )
            ],
        )

    def _youtube_transcript(self, video_id: str) -> tuple[str, str]:
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        page = self._fetch(watch_url).text
        title = _html_title(page) or video_id
        tracks = _caption_tracks(page)
        if not tracks:
            raise ImportFailedError(
                "El vídeo no tiene subtítulos disponibles. Prueba con otro vídeo o "
                "sube la transcripción como archivo."
            )

        preferred = [
            track
            for track in tracks
            if any(
                str(track.get("languageCode", "")).lower().startswith(lang.lower())
                for lang in self.settings.youtube_languages
            )
        ]
        track = (preferred or tracks)[0]
        caption_url = str(track.get("baseUrl") or "")
        if not caption_url:
            raise ImportFailedError("No se pudo obtener la pista de subtítulos del vídeo")
        if caption_url.startswith("//"):
            caption_url = f"https:{caption_url}"
        if "fmt=" not in caption_url:
            caption_url = f"{caption_url}&fmt=json3"

        payload = json.loads(self._fetch(caption_url).text)
        lines = []
        for event in payload.get("events", []):
            segments = event.get("segs") or []
            text = "".join(segment.get("utf8", "") for segment in segments).strip()
            if text:
                lines.append(text)
        transcript = self._truncate("\n".join(lines).strip())
        if not transcript:
            raise ImportFailedError("Los subtítulos del vídeo están vacíos")
        return title, transcript

    def _truncate(self, text: str) -> str:
        return text[: self.settings.import_max_chars]

    def _fetch(self, url: str) -> _FetchedDocument:
        max_bytes = min(self.settings.max_upload_bytes, 20 * 1024 * 1024)
        current = url
        with httpx.Client(
            timeout=self.settings.import_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "es,en;q=0.8"},
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                self._validate_url(current)
                try:
                    with client.stream("GET", current) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location:
                                raise ImportFailedError("Redirección sin destino")
                            current = urljoin(current, location)
                            continue
                        response.raise_for_status()
                        chunks = bytearray()
                        for chunk in response.iter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > max_bytes:
                                raise ImportFailedError(
                                    "El contenido remoto supera el tamaño máximo permitido"
                                )
                        return _FetchedDocument(
                            url=str(response.url),
                            content_type=response.headers.get("content-type", ""),
                            content=bytes(chunks),
                            encoding=response.encoding,
                        )
                except httpx.HTTPStatusError as exc:
                    raise ImportFailedError(
                        f"El servidor remoto respondió con estado {exc.response.status_code}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise ImportFailedError(f"No se pudo descargar la URL: {exc}") from exc
        raise ImportFailedError("Demasiadas redirecciones al descargar la URL")

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ImportBlockedError("Solo se permiten URLs http o https")
        if parsed.username or parsed.password:
            raise ImportBlockedError("La URL no puede incluir credenciales")
        host = parsed.hostname
        if not host:
            raise ImportBlockedError("La URL no tiene un host válido")
        if self.settings.import_allow_private_hosts:
            return
        try:
            addresses = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ImportFailedError(f"No se pudo resolver el host {host}") from exc
        for info in addresses:
            address = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
            if not address.is_global:
                raise ImportBlockedError(
                    "Por seguridad no se permiten URLs que apunten a redes privadas o locales"
                )


def _youtube_video_id(url: str) -> str | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    candidate = None
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/", 1)[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
            candidate = parsed.path.strip("/").split("/", 1)[1].split("/", 1)[0]
    return candidate if candidate and _YOUTUBE_ID.match(candidate) else None


def _caption_tracks(page: str) -> list[dict]:
    marker = '"captionTracks":'
    index = page.find(marker)
    if index == -1:
        return []
    start = index + len(marker)
    try:
        tracks, _ = json.JSONDecoder().raw_decode(page, start)
    except json.JSONDecodeError:
        return []
    return [track for track in tracks if isinstance(track, dict)]


def _html_title(page: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return " ".join(re.sub(r"<[^>]+>", "", match.group(1)).split())


def _filename_from_url(url: str) -> str:
    name = Path(unquote(urlsplit(url).path)).name
    return name or "importado"


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:120]


def _extension_for(content_type: str) -> str:
    return {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "text/plain": "txt",
        "text/markdown": "md",
        "text/csv": "csv",
        "application/json": "json",
    }.get(content_type, "txt")
