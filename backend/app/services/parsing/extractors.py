import re
from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".xlsx",
    ".xlsm",
    ".json",
    ".parquet",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
}


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(
    path: Path,
    *,
    max_chars: int,
    ocr_language: str = "spa+eng",
    ocr_enabled: bool = True,
    sample_rows: int = 500,
) -> str:
    """Extrae texto plano del archivo. Lanza ValueError si no se puede leer."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Extensión no soportada: {suffix or 'sin extensión'}")

    if suffix in {".txt", ".md", ".markdown", ".json"}:
        text = _read_plain(path)
    elif suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix == ".docx":
        text = _read_docx(path)
    elif suffix == ".pptx":
        text = _read_pptx(path)
    elif suffix == ".csv":
        text = _read_csv(path, sample_rows=sample_rows)
    elif suffix in {".xlsx", ".xlsm"}:
        text = _read_xlsx(path, sample_rows=sample_rows)
    elif suffix == ".parquet":
        text = _read_parquet(path, sample_rows=sample_rows)
    elif suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
        if not ocr_enabled:
            raise ValueError("El OCR está desactivado en la configuración")
        from app.services.parsing.ocr import ocr_image

        text = ocr_image(path, language=ocr_language)
    else:  # pragma: no cover - cubierto por la validación anterior
        raise ValueError(f"Extensión no soportada: {suffix}")

    text = normalize_text(text)
    if not text:
        raise ValueError(
            "No se extrajo texto del archivo. Si es un PDF escaneado, necesitará OCR (fase 4)."
        )
    return text[:max_chars]


def _read_plain(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValueError("El PDF está protegido con contraseña") from exc
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        content = page.extract_text() or ""
        if content.strip():
            pages.append(f"--- Página {number} ---\n{content}")
    return "\n\n".join(pages)


def _read_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_pptx(path: Path) -> str:
    from pptx import Presentation

    presentation = Presentation(str(path))
    slides = []
    for number, slide in enumerate(presentation.slides, start=1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                content = shape.text_frame.text.strip()
                if content:
                    texts.append(content)
        if texts:
            slides.append(f"--- Diapositiva {number} ---\n" + "\n".join(texts))
    return "\n\n".join(slides)


def _read_csv(path: Path, *, sample_rows: int) -> str:
    import polars as pl

    try:
        frame = pl.scan_csv(
            path,
            encoding="utf8-lossy",
            infer_schema_length=1_000,
            ignore_errors=True,
        )
    except Exception as exc:
        raise ValueError(f"No se pudo leer el CSV: {exc}") from exc
    return _tabular_to_text(frame, kind="CSV", sample_rows=sample_rows)


def _read_xlsx(path: Path, *, sample_rows: int) -> str:
    import pandas as pd

    sheets = pd.read_excel(path, sheet_name=None, nrows=sample_rows)
    parts = []
    for name, frame in sheets.items():
        parts.append(f"--- Hoja: {name} ---\n{_dataframe_to_text(frame)}")
    return "\n\n".join(parts)


def _read_parquet(path: Path, *, sample_rows: int) -> str:
    import polars as pl

    try:
        frame = pl.scan_parquet(path)
    except Exception as exc:
        raise ValueError(f"No se pudo leer el Parquet: {exc}") from exc
    return _tabular_to_text(frame, kind="Parquet", sample_rows=sample_rows)


def _tabular_to_text(frame, *, kind: str, sample_rows: int) -> str:
    """Resumen compacto de un LazyFrame: recuento, perfil y muestra acotada."""
    import polars as pl

    schema = frame.collect_schema()
    if not schema:
        return ""
    row_count = int(frame.select(pl.len()).collect().item())
    sample = frame.head(sample_rows).collect()

    profile_exprs = []
    for name, dtype in schema.items():
        profile_exprs.append(pl.col(name).null_count().alias(f"{name}__nulls"))
        profile_exprs.append(pl.col(name).n_unique().alias(f"{name}__unique"))
        if dtype.is_numeric():
            profile_exprs.append(pl.col(name).mean().alias(f"{name}__mean"))
            profile_exprs.append(pl.col(name).min().alias(f"{name}__min"))
            profile_exprs.append(pl.col(name).max().alias(f"{name}__max"))
    profile = frame.select(profile_exprs).collect().row(0, named=True) if profile_exprs else {}

    lines = [
        f"Tipo: {kind}",
        f"Filas: {row_count} · Columnas: {len(schema)}: {', '.join(schema.names())}",
        "Perfil de columnas:",
    ]
    for name, dtype in schema.items():
        parts = [
            f"tipo={dtype}",
            f"nulos={profile.get(f'{name}__nulls', 0)}",
            f"únicos={profile.get(f'{name}__unique', 0)}",
        ]
        if dtype.is_numeric():
            parts.extend(
                [
                    f"media={_format_number(profile.get(f'{name}__mean'))}",
                    f"min={_format_number(profile.get(f'{name}__min'))}",
                    f"max={_format_number(profile.get(f'{name}__max'))}",
                ]
            )
        lines.append(f"- {name}: " + ", ".join(parts))

    lines.append(f"Muestra ({min(sample_rows, row_count)} filas):")
    lines.append(sample.write_csv())
    return "\n".join(lines)


def _format_number(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _dataframe_to_text(frame) -> str:
    if frame.empty:
        return ""
    summary = f"Filas: {len(frame)} · Columnas: {', '.join(map(str, frame.columns))}"
    return f"{summary}\n{frame.to_csv(index=False)}"
