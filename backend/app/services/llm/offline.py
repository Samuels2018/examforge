import re
import unicodedata
from collections import Counter

from app.core.errors import LLMUnavailableError
from app.models.enums import Difficulty, ExerciseKind
from app.schemas.exercise import ExerciseOption, GeneratedExercise
from app.schemas.llm import GenerationResult, GradeResult
from app.services.llm.base import LLMProvider

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+|\n+")
_MATERIAL_HEADER = re.compile(r"\[Material:[^\]]*\]|--- (?:Página|Diapositiva|Hoja):?[^-]*---")
_MISSING_SPACE = re.compile(r"([.!?;:])(?=[^\W\d_])", re.UNICODE)
_TOPIC_HEADING = re.compile(r"(?:^|\n)\s*Tema\s+\d+\s*[.:\-]\s*([^\n]{3,120})", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W\d_][\wáéíóúüñÁÉÍÓÚÜÑ-]*", re.UNICODE)

_STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "que", "en",
    "con", "por", "para", "del", "al", "se", "su", "sus", "es", "son", "como", "mas",
    "más", "pero", "sin", "sobre", "entre", "este", "esta", "estos", "estas", "ese",
    "esa", "esos", "esas", "lo", "le", "les", "me", "mi", "mis", "tu", "tus", "no",
    "sí", "si", "cuando", "donde", "porque", "también", "muy", "ya", "hay", "ser",
    "estar", "tiene", "tienen", "puede", "pueden", "desde", "hasta", "cada", "otro",
    "otra", "todo", "toda", "todos", "todas", "durante", "mediante", "según", "the",
    "and", "for", "with", "that", "this", "from", "are", "was", "were", "have", "has",
}


class OfflineProvider(LLMProvider):
    """Generador heurístico local: permite usar la app sin Ollama y testear sin red."""

    name = "offline"

    def __init__(self) -> None:
        self._generation_calls = 0

    def generate_exercises(
        self,
        *,
        context: str,
        count: int,
        difficulties: list[Difficulty],
        focus: str | None,
        language: str,
    ) -> GenerationResult:
        sentences = _candidate_sentences(context)
        if not sentences:
            raise LLMUnavailableError(
                "El material no contiene texto suficiente para generar ejercicios. "
                "Sube un archivo con más contenido o levanta Ollama."
            )

        topic = focus or _guess_topic(context)
        exercises: list[GeneratedExercise] = []
        seen_questions: set[str] = set()
        call_number = self._generation_calls
        offset = call_number * count
        self._generation_calls += 1

        for index in range(count):
            difficulty = difficulties[index % len(difficulties)]
            exercise = self._build_exercise(
                sentences=sentences,
                index=offset + index,
                difficulty=difficulty,
                topic=topic,
                language=language,
                nonce=call_number,
            )
            if exercise is None or exercise.question in seen_questions:
                continue
            seen_questions.add(exercise.question)
            exercises.append(exercise)

        if not exercises:
            raise LLMUnavailableError("No se pudieron construir ejercicios con el material disponible")

        warning = None
        if len(exercises) < count:
            warning = (
                f"El generador offline creó {len(exercises)} de {count} ejercicios "
                "porque el material es corto. Añade más contenido para ampliar el banco."
            )
        return GenerationResult(exercises=exercises, provider=self.name, warning=warning)

    def grade_short_answer(
        self,
        *,
        question: str,
        expected_answer: str,
        rubric: str | None,
        student_answer: str,
        language: str,
    ) -> GradeResult:
        answer = student_answer.strip()
        if not answer:
            return GradeResult(
                score=0.0,
                is_correct=False,
                feedback="No has respondido. Intenta escribir al menos la idea principal.",
                explanation=f"Respuesta esperada: {expected_answer}",
                provider=self.name,
            )

        expected_keywords = _keywords(expected_answer)
        answer_tokens = set(_keywords(answer))
        if not expected_keywords:
            score = 1.0 if _normalize(answer) == _normalize(expected_answer) else 0.0
            missing: list[str] = []
        elif len(expected_keywords) <= 2:
            matched = [word for word in expected_keywords if word in answer_tokens]
            score = 1.0 if matched else 0.0
            missing = [word for word in expected_keywords if word not in answer_tokens]
        else:
            keywords = expected_keywords[:5]
            matched = [word for word in keywords if word in answer_tokens]
            score = len(matched) / len(keywords)
            missing = [word for word in keywords if word not in answer_tokens]

        is_correct = score >= 0.6
        if is_correct:
            feedback = "¡Bien! Tu respuesta recoge las ideas clave del material."
        else:
            detail = ", ".join(missing) if missing else "la idea principal"
            feedback = f"Tu respuesta se queda corta. Faltan conceptos clave: {detail}."
        explanation = f"Respuesta esperada: {expected_answer}"
        if rubric:
            explanation += f"\nCriterio de corrección: {rubric}"
        return GradeResult(
            score=round(score, 3),
            is_correct=is_correct,
            feedback=feedback,
            explanation=explanation,
            provider=self.name,
        )

    def _build_exercise(
        self,
        *,
        sentences: list[str],
        index: int,
        difficulty: Difficulty,
        topic: str,
        language: str,
        nonce: int = 0,
    ) -> GeneratedExercise | None:
        if difficulty is Difficulty.BASIC and len(sentences) >= 4:
            exercise = _multiple_choice(sentences, index, topic, language, nonce=nonce)
            if exercise is not None:
                return exercise
        if difficulty is Difficulty.ADVANCED:
            return _advanced(sentences, index, topic, language)
        cloze = _cloze(
            sentences, index, topic, language, difficulty=difficulty, nonce=nonce
        )
        if cloze is not None:
            return cloze
        return _advanced(sentences, index, topic, language, nonce=nonce)


def _candidate_sentences(context: str) -> list[str]:
    cleaned_context = _MATERIAL_HEADER.sub(" ", context)
    cleaned_context = _MISSING_SPACE.sub(r"\1 ", cleaned_context)
    raw = [part.strip() for part in _SENTENCE_SPLIT.split(cleaned_context) if part and part.strip()]
    seen: set[str] = set()
    sentences: list[str] = []
    for sentence in raw:
        cleaned = re.sub(r"\s+", " ", sentence).strip(" -–—")
        key = _normalize(cleaned)
        if not (40 <= len(cleaned) <= 420) or key in seen:
            continue
        if not (cleaned[0].isupper() or cleaned[0].isdigit()):
            continue
        seen.add(key)
        sentences.append(cleaned)
    return sentences


def _multiple_choice(
    sentences: list[str], index: int, topic: str, language: str, *, nonce: int = 0
) -> GeneratedExercise | None:
    """Construye un cloze con opciones: una frase real y términos distractores.

    No usamos varias frases verdaderas como opciones porque entonces todas las
    respuestas serían válidas y el ejercicio no mediría nada.
    """
    start = (index * 3 + nonce) % len(sentences)
    terms = _unique_terms(sentences)

    for offset in range(len(sentences)):
        sentence = sentences[(start + offset) % len(sentences)]
        word = _pick_keyword(sentence, variant=index)
        if word is None:
            continue
        blanked = sentence.replace(word, "_____", 1)
        if blanked == sentence:
            continue

        normalized_word = _normalize(word)
        distractors = [
            term
            for term in _rotate(terms, index + offset)
            if _normalize(term) != normalized_word
        ][:3]
        if len(distractors) < 3:
            continue

        correct_position = index % 4
        options_text = distractors[:]
        options_text.insert(correct_position, word)
        options = [
            ExerciseOption(id=chr(ord("a") + position), text=text)
            for position, text in enumerate(options_text)
        ]
        correct_id = chr(ord("a") + correct_position)

        if language == "en":
            question = f"Complete the sentence according to the material: “{blanked}”"
            explanation = f"The original sentence in the material is: “{sentence}”."
            hint = "Look for the key term that was removed."
        else:
            question = f"Completa la frase según el material: «{blanked}»"
            explanation = f"La frase original del material es: «{sentence}»."
            hint = "Fíjate en el término técnico que falta."

        return GeneratedExercise(
            topic=topic,
            difficulty=Difficulty.BASIC,
            kind=ExerciseKind.MULTIPLE_CHOICE,
            question=question,
            options=options,
            correct_answer=correct_id,
            explanation=explanation,
            hint=hint,
        )
    return None


def _cloze(
    sentences: list[str],
    index: int,
    topic: str,
    language: str,
    *,
    difficulty: Difficulty = Difficulty.INTERMEDIATE,
    nonce: int = 0,
) -> GeneratedExercise | None:
    start = (index * 2 + nonce) % len(sentences)
    for offset in range(len(sentences)):
        sentence = sentences[(start + offset) % len(sentences)]
        word = _pick_keyword(sentence, variant=index)
        if word is None:
            continue
        blanked = sentence.replace(word, "_____", 1)
        if language == "en":
            question = f"Complete the sentence according to the material: “{blanked}”"
            explanation = f"The original sentence in the material is: “{sentence}”."
            hint = "Think about the key term that was removed."
        else:
            question = f"Completa la frase según el material: «{blanked}»"
            explanation = f"La frase original del material es: «{sentence}»."
            hint = "Fíjate en el término técnico que falta."
        return GeneratedExercise(
            topic=topic,
            difficulty=difficulty,
            kind=ExerciseKind.SHORT_ANSWER,
            question=question,
            correct_answer=word,
            explanation=explanation,
            hint=hint,
            rubric=f"La respuesta debe incluir el término «{word}».",
        )
    return None


def _advanced(
    sentences: list[str], index: int, topic: str, language: str, *, nonce: int = 0
) -> GeneratedExercise:
    sentence = sentences[(index * 5 + nonce) % len(sentences)]
    keywords = _keywords(sentence)[:5]
    rubric = "Menciona y relaciona: " + ", ".join(keywords) if keywords else None
    if language == "en":
        question = (
            "Explain in your own words the following concept from the material and connect it "
            f"to the topic “{topic}”: “{sentence}”"
        )
        explanation = f"A complete answer should cover the key ideas: {', '.join(keywords)}."
    else:
        question = (
            "Explica con tus propias palabras el siguiente concepto del material y relaciónalo "
            f"con el tema «{topic}»: «{sentence}»"
        )
        explanation = (
            f"Una respuesta completa debería cubrir estas ideas clave: {', '.join(keywords)}."
            if keywords
            else "La respuesta debe reformular la idea principal de la frase."
        )
    return GeneratedExercise(
        topic=topic,
        difficulty=Difficulty.ADVANCED,
        kind=ExerciseKind.SHORT_ANSWER,
        question=question,
        correct_answer=sentence,
        explanation=explanation,
        hint="No copies literalmente: explica la idea y añade un ejemplo o relación.",
        rubric=rubric,
    )


def _unique_terms(sentences: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        for word in _WORD_RE.findall(sentence):
            normalized = _normalize(word)
            if (
                len(word) >= 6
                and normalized not in _STOPWORDS
                and normalized not in seen
                and not word.isdigit()
            ):
                seen.add(normalized)
                terms.append(word)
    return terms


def _pick_keyword(sentence: str, *, variant: int = 0) -> str | None:
    candidates = sorted(
        {
            word
            for word in _WORD_RE.findall(sentence)
            if len(word) >= 6
            and _normalize(word) not in _STOPWORDS
            and not word.isdigit()
        },
        key=lambda word: (-len(word), _normalize(word)),
    )
    if not candidates:
        return None
    return candidates[variant % len(candidates)]


def _guess_topic(context: str) -> str:
    cleaned = _MATERIAL_HEADER.sub(" ", context)
    heading = _TOPIC_HEADING.search(cleaned)
    if heading:
        return heading.group(1).strip(" .-–—")[:160]

    generic = {"material", "materiales", "examen", "temario", "apuntes", "pagina", "hoja"}
    counts = Counter(
        word.capitalize()
        for word in _keywords(cleaned)
        if len(word) >= 5 and word not in generic
    )
    return counts.most_common(1)[0][0] if counts else "General"


def _keywords(text: str) -> list[str]:
    words = [
        _normalize(word)
        for word in _WORD_RE.findall(text)
        if len(word) >= 3 and _normalize(word) not in _STOPWORDS
    ]
    return list(dict.fromkeys(words))


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^\w\s]", " ", without_accents).strip()


def _rotate(items: list[str], amount: int) -> list[str]:
    if not items:
        return items
    shift = amount % len(items)
    return items[shift:] + items[:shift]
