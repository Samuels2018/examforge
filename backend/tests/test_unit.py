import pytest
from pydantic import ValidationError

from app.models.enums import Difficulty, ExerciseKind
from app.schemas.exercise import GeneratedExercise
from app.services.llm.offline import OfflineProvider
from app.services.parsing.chunking import chunk_text


def test_chunk_text_respects_limits_and_overlap():
    text = " ".join(
        f"La frase número {index} explica un concepto distinto del material de estudio."
        for index in range(60)
    )
    chunks = chunk_text(text, max_chars=300, overlap=60)

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert chunks[0] != chunks[1]
    assert len(set(chunks)) == len(chunks)


def test_chunk_text_empty():
    assert chunk_text("", max_chars=500, overlap=50) == []


def test_chunk_text_keeps_paragraph_boundaries():
    text = (
        "Tema 1. Bases de datos relacionales\n\n"
        "Una base de datos relacional organiza la información en tablas.\n\n"
        "Los índices aceleran las búsquedas y los filtros."
    )
    chunks = chunk_text(text, max_chars=400, overlap=0)

    assert len(chunks) == 1
    assert "relacionales\n\nUna base de datos" in chunks[0]
    assert "tablas.\n\nLos índices" in chunks[0]


def test_generated_exercise_normalizes_option_text_to_id():
    exercise = GeneratedExercise(
        topic="TCP",
        difficulty=Difficulty.BASIC,
        kind=ExerciseKind.MULTIPLE_CHOICE,
        question="¿Cuál es la respuesta correcta?",
        options=[
            {"id": "a", "text": "Primera"},
            {"id": "b", "text": "Segunda"},
        ],
        correct_answer="Segunda",
        explanation="La segunda es correcta.",
    )
    assert exercise.correct_answer == "b"


def test_generated_exercise_rejects_bad_multiple_choice():
    with pytest.raises(ValidationError):
        GeneratedExercise(
            topic="TCP",
            difficulty=Difficulty.BASIC,
            kind=ExerciseKind.MULTIPLE_CHOICE,
            question="¿Cuál es la respuesta correcta?",
            options=[{"id": "a", "text": "Primera"}],
            correct_answer="z",
            explanation="Explicación",
        )


def test_true_false_is_normalized():
    exercise = GeneratedExercise(
        topic="TCP",
        difficulty=Difficulty.BASIC,
        kind=ExerciseKind.TRUE_FALSE,
        question="¿TCP ofrece entrega fiable?",
        correct_answer="Verdadero",
        explanation="TCP es orientado a conexión y fiable.",
    )
    assert exercise.correct_answer == "true"
    assert exercise.options == []


def test_offline_provider_cleans_headers_and_builds_exercises():
    context = """[Material: redes.txt]
El modelo TCP/IP divide la comunicación en cuatro capas bien diferenciadas.
La capa de transporte usa TCP para ofrecer entrega fiable y UDP para baja latencia.
TCP realiza el saludo de tres vías para establecer una conexión confiable.
El protocolo IP se encarga del direccionamiento lógico y del enrutamiento.
El DNS traduce nombres de dominio legibles en direcciones IP numéricas.
HTTP es un protocolo de aplicación sin estado que se apoya en TCP.
Un cortafuegos filtra tráfico según reglas de puertos y direcciones.
La NAT permite que varios dispositivos compartan una dirección IP pública.
"""
    result = OfflineProvider().generate_exercises(
        context=context,
        count=6,
        difficulties=[Difficulty.BASIC, Difficulty.INTERMEDIATE, Difficulty.ADVANCED],
        focus="TCP",
        language="es",
    )

    assert result.provider == "offline"
    assert 1 <= len(result.exercises) <= 6
    for exercise in result.exercises:
        assert "[Material:" not in exercise.question
        assert all("[Material:" not in option.text for option in exercise.options)
        if exercise.kind is ExerciseKind.MULTIPLE_CHOICE:
            assert exercise.correct_answer in {option.id for option in exercise.options}
        assert exercise.explanation


def test_chunk_text_overlap_keeps_heading_separate_from_body():
    text = (
        "Tema 1. Bases de datos relacionales\n\n"
        + " ".join(
            f"La frase {index} explica un concepto distinto del material de estudio."
            for index in range(8)
        )
        + "\n\nTema 2. Índices y rendimiento\n\n"
        + " ".join(
            f"El índice {index} acelera las búsquedas por igualdad y por rango."
            for index in range(8)
        )
    )
    chunks = chunk_text(text, max_chars=420, overlap=90)

    assert len(chunks) > 1
    assert all("rendimiento Un índice" not in chunk for chunk in chunks)
    assert any("rendimiento\n\nEl índice" in chunk for chunk in chunks)


def test_offline_multiple_choice_has_one_true_answer():
    context = """[Material: db.txt]
Una base de datos relacional organiza la información en tablas y columnas.
La clave primaria identifica de forma única cada fila de la tabla.
Los índices aceleran las búsquedas aunque añaden coste de escritura.
Las transacciones agrupan operaciones que deben ejecutarse de forma atómica.
El problema N+1 ejecuta una consulta adicional por cada elemento.
La normalización reduce la redundancia y las anomalías de actualización.
"""
    result = OfflineProvider().generate_exercises(
        context=context,
        count=1,
        difficulties=[Difficulty.BASIC],
        focus=None,
        language="es",
    )

    exercise = result.exercises[0]
    assert exercise.kind is ExerciseKind.MULTIPLE_CHOICE
    assert "_____" in exercise.question
    assert len(exercise.options) == 4
    assert exercise.correct_answer in {option.id for option in exercise.options}
    assert all(len(option.text.split()) <= 2 for option in exercise.options)
    assert len({option.text.casefold() for option in exercise.options}) == 4


def test_offline_guesses_topic_without_material_header():
    context = """[Material: db.txt]
Tema 1. Bases de datos relacionales

Una base de datos relacional organiza la información en tablas y columnas.
La base de datos usa claves foráneas para relacionar entidades.
Los índices de la base de datos aceleran las búsquedas.
Las transacciones de la base de datos agrupan operaciones atómicas.
La normalización de la base de datos reduce la redundancia.
"""
    result = OfflineProvider().generate_exercises(
        context=context,
        count=2,
        difficulties=[Difficulty.BASIC],
        focus=None,
        language="es",
    )

    assert all(exercise.topic == "Bases de datos relacionales" for exercise in result.exercises)


def test_offline_grader():
    provider = OfflineProvider()
    correct = provider.grade_short_answer(
        question="¿Qué hace TCP?",
        expected_answer="TCP ofrece entrega fiable y orientada a conexión",
        rubric=None,
        student_answer="TCP proporciona entrega fiable",
        language="es",
    )
    assert correct.is_correct is True
    assert correct.score >= 0.6

    empty = provider.grade_short_answer(
        question="¿Qué hace TCP?",
        expected_answer="TCP ofrece entrega fiable",
        rubric=None,
        student_answer="",
        language="es",
    )
    assert empty.is_correct is False
    assert empty.score == 0.0


def test_offline_variation_does_not_repeat_the_source_question():
    context = """[Material: redes.txt]
El protocolo IP se encarga del direccionamiento lógico de los paquetes.
La capa de transporte usa TCP para ofrecer entrega fiable.
El DNS traduce nombres de dominio en direcciones IP numéricas.
Un cortafuegos filtra el tráfico según reglas de puertos y protocolos.
La NAT permite compartir una dirección IP pública entre dispositivos.
El enrutamiento dinámico actualiza las tablas de rutas de la red.
"""
    provider = OfflineProvider()
    first = provider.generate_exercises(
        context=context,
        count=6,
        difficulties=[Difficulty.BASIC],
        focus="redes",
        language="es",
    )
    variation = provider.generate_exercises(
        context=context,
        count=1,
        difficulties=[Difficulty.BASIC],
        focus="redes",
        language="es",
    )

    assert variation.exercises[0].question not in {item.question for item in first.exercises}
