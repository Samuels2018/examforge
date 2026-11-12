import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_image(path: Path, *, language: str) -> str:
    """Extrae texto de una imagen con Tesseract.

    pytesseract es una dependencia opcional: si no está instalada, se devuelve
    un error claro en lugar de romper la subida de otros formatos.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise ValueError(
            "OCR no disponible. Instala pytesseract y Pillow, y el binario tesseract "
            "para poder importar imágenes."
        ) from exc

    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image, lang=language)
    except pytesseract.TesseractNotFoundError as exc:
        raise ValueError(
            "OCR no disponible: no se encontró el binario tesseract en el sistema."
        ) from exc
    except Exception as exc:
        raise ValueError(f"No se pudo aplicar OCR a la imagen: {exc}") from exc

    text = text.strip()
    if not text:
        raise ValueError("El OCR no detectó texto legible en la imagen.")
    return text
