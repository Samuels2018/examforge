import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")


def chunk_text(text: str, *, max_chars: int = 1_200, overlap: int = 180) -> list[str]:
    """Divide texto en fragmentos con solapamiento, sin cortar palabras si es posible.

    Se respetan los límites de párrafo para no fusionar títulos con el cuerpo del
    texto, algo que degrada la calidad de los ejercicios generados.
    """
    text = text.strip()
    if not text:
        return []

    max_chars = max(200, max_chars)
    overlap = max(0, min(overlap, max_chars // 2))
    base_limit = max(100, max_chars - overlap)

    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in _PARAGRAPH_SPLIT.split(text)
        if paragraph.strip()
    ]
    pieces: list[tuple[str, bool]] = []
    for paragraph in paragraphs:
        for position, piece in enumerate(_split_paragraph(paragraph, base_limit)):
            pieces.append((piece, position == 0))

    base_chunks: list[tuple[str, bool]] = []
    current = ""
    current_starts_paragraph = True
    for piece, starts_paragraph in pieces:
        if current:
            separator = "\n\n" if starts_paragraph else " "
            candidate = f"{current}{separator}{piece}"
        else:
            candidate = piece
        if len(candidate) <= base_limit:
            current = candidate
        else:
            if current:
                base_chunks.append((current, current_starts_paragraph))
            current = piece
            current_starts_paragraph = starts_paragraph
    if current:
        base_chunks.append((current, current_starts_paragraph))

    if overlap == 0 or len(base_chunks) <= 1:
        return [chunk for chunk, _ in base_chunks]

    chunks: list[str] = [base_chunks[0][0]]
    for (previous, _), (current_chunk, starts_paragraph) in zip(
        base_chunks, base_chunks[1:], strict=False
    ):
        tail = _tail_at_word_boundary(previous, overlap)
        separator = "\n\n" if starts_paragraph else " "
        merged = f"{tail}{separator}{current_chunk}".strip() if tail else current_chunk
        if len(merged) > max_chars:
            merged = merged[-max_chars:].lstrip()
        chunks.append(merged)
    return chunks


def _split_paragraph(paragraph: str, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]

    units = [unit.strip() for unit in _SENTENCE_SPLIT.split(paragraph) if unit.strip()]
    pieces: list[str] = []
    current = ""
    for unit in units:
        for piece in _split_long_unit(unit, limit):
            candidate = f"{current} {piece}".strip() if current else piece
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    pieces.append(current)
                current = piece
    if current:
        pieces.append(current)
    return pieces


def _split_long_unit(unit: str, limit: int) -> list[str]:
    if len(unit) <= limit:
        return [unit]
    pieces: list[str] = []
    start = 0
    while start < len(unit):
        end = min(start + limit, len(unit))
        if end < len(unit):
            cut = unit.rfind(" ", start, end)
            if cut > start + limit // 2:
                end = cut
        piece = unit[start:end].strip()
        if piece:
            pieces.append(piece)
        start = end
    return pieces


def _tail_at_word_boundary(text: str, overlap: int) -> str:
    if overlap <= 0:
        return ""
    if len(text) <= overlap:
        return text
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail
