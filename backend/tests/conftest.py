import os

os.environ.setdefault("EXAMFORGE_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("EXAMFORGE_UPLOAD_DIR", "/tmp/examforge-default-uploads")
os.environ.setdefault("EXAMFORGE_ENVIRONMENT", "test")

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.enums import Difficulty, ExerciseKind  # noqa: E402
from app.schemas.exercise import ExerciseOption, GeneratedExercise  # noqa: E402
from app.schemas.llm import GenerationResult, GradeResult  # noqa: E402
from app.services.llm.base import LLMProvider  # noqa: E402


class FakeLLMProvider(LLMProvider):
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.last_context = ""
        self.generation_sequence = 0

    def generate_exercises(
        self,
        *,
        context: str,
        count: int,
        difficulties: list[Difficulty],
        focus: str | None,
        language: str,
    ) -> GenerationResult:
        self.last_context = context
        self.calls.append(
            {
                "context": context,
                "count": count,
                "difficulties": difficulties,
                "focus": focus,
                "language": language,
            }
        )
        self.generation_sequence += 1
        base = (self.generation_sequence - 1) * count
        kinds = [
            ExerciseKind.MULTIPLE_CHOICE,
            ExerciseKind.TRUE_FALSE,
            ExerciseKind.SHORT_ANSWER,
        ]
        exercises = []
        for index in range(count):
            difficulty = difficulties[index % len(difficulties)]
            kind = kinds[index % len(kinds)]
            if kind is ExerciseKind.MULTIPLE_CHOICE:
                options = [
                    ExerciseOption(id="a", text="Opción correcta"),
                    ExerciseOption(id="b", text="Opción incorrecta"),
                    ExerciseOption(id="c", text="Otra opción"),
                ]
                correct_answer = "a"
                rubric = None
            elif kind is ExerciseKind.TRUE_FALSE:
                options = []
                correct_answer = "true"
                rubric = None
            else:
                options = []
                correct_answer = "respuesta esperada"
                rubric = "Debe mencionar el concepto principal"
            exercises.append(
                GeneratedExercise(
                    topic=focus or "Tema de prueba",
                    difficulty=difficulty,
                    kind=kind,
                    question=f"Pregunta {base + index + 1}: ¿qué concepto aplica aquí?",
                    options=options,
                    correct_answer=correct_answer,
                    explanation=f"Explicación {base + index + 1}: el concepto se aplica así.",
                    hint="Piensa en el material.",
                    rubric=rubric,
                )
            )
        return GenerationResult(exercises=exercises, provider=self.name)

    def grade_short_answer(
        self,
        *,
        question: str,
        expected_answer: str,
        rubric: str | None,
        student_answer: str,
        language: str,
    ) -> GradeResult:
        is_correct = "correcta" in student_answer.casefold()
        return GradeResult(
            score=0.9 if is_correct else 0.2,
            is_correct=is_correct,
            feedback="Bien argumentado." if is_correct else "Falta el concepto principal.",
            explanation="El concepto correcto se explica en el material.",
            provider=self.name,
        )


@pytest.fixture
def provider() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads",
        llm_provider="offline",
        embedding_provider="offline",
        llm_max_context_chars=6_000,
    )


@pytest.fixture
def app(settings: Settings, provider: FakeLLMProvider):
    return create_app(settings=settings, provider=provider)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
