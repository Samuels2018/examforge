from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import Difficulty, ExerciseKind
from app.schemas.usage import TokenUsage

OptionId = Annotated[str, Field(min_length=1, max_length=8)]


class ExerciseOption(BaseModel):
    id: OptionId
    text: str = Field(min_length=1, max_length=2_000)


class GeneratedExercise(BaseModel):
    """Ejercicio tal y como lo devuelve el LLM, antes de persistirlo."""

    topic: str = Field(default="General", min_length=1, max_length=160)
    difficulty: Difficulty
    kind: ExerciseKind
    question: str = Field(min_length=8, max_length=4_000)
    options: list[ExerciseOption] = Field(default_factory=list, max_length=8)
    correct_answer: str = Field(min_length=1, max_length=4_000)
    explanation: str = Field(min_length=1, max_length=4_000)
    hint: str | None = Field(default=None, max_length=1_000)
    rubric: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_and_normalize(self) -> "GeneratedExercise":
        self.topic = self.topic.strip() or "General"

        if self.kind is ExerciseKind.MULTIPLE_CHOICE:
            if len(self.options) < 2:
                raise ValueError("multiple_choice necesita al menos 2 opciones")
            option_ids = {option.id for option in self.options}
            if self.correct_answer in option_ids:
                return self
            lowered = self.correct_answer.strip().casefold()
            for option in self.options:
                if option.text.strip().casefold() == lowered:
                    self.correct_answer = option.id
                    return self
            raise ValueError("correct_answer debe coincidir con el id o el texto de una opción")

        if self.kind is ExerciseKind.TRUE_FALSE:
            normalized = self.correct_answer.strip().casefold()
            mapping = {
                "true": "true",
                "verdadero": "true",
                "v": "true",
                "si": "true",
                "sí": "true",
                "false": "false",
                "falso": "false",
                "f": "false",
                "no": "false",
            }
            if normalized not in mapping:
                raise ValueError("correct_answer de true_false debe ser true/false")
            self.correct_answer = mapping[normalized]
            self.options = []

        return self


class ExerciseRead(BaseModel):
    """Vista pública: nunca incluye la respuesta correcta ni la explicación."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    topic: str
    difficulty: Difficulty
    kind: ExerciseKind
    question: str
    options: list[ExerciseOption]
    hint: str | None
    created_at: datetime


class GenerateRequest(BaseModel):
    count: int = Field(default=8, ge=1, le=30)
    difficulties: list[Difficulty] = Field(
        default_factory=lambda: [Difficulty.BASIC, Difficulty.INTERMEDIATE, Difficulty.ADVANCED],
        min_length=1,
        max_length=3,
    )
    focus: str | None = Field(default=None, max_length=300)
    language: Literal["es", "en"] = "es"

    @field_validator("difficulties")
    @classmethod
    def unique_difficulties(cls, value: list[Difficulty]) -> list[Difficulty]:
        deduped = list(dict.fromkeys(value))
        if not deduped:
            raise ValueError("Elige al menos una dificultad")
        return deduped

    @field_validator("focus")
    @classmethod
    def normalize_focus(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class GenerateResponse(BaseModel):
    exercises: list[ExerciseRead]
    requested: int
    created: int
    provider: str
    warning: str | None = None
    cached: bool = False
    duration_ms: int = 0
    usage: TokenUsage | None = None


class AttemptCreate(BaseModel):
    answer: str = Field(default="", max_length=8_000)
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)


class AttemptResult(BaseModel):
    attempt_id: str
    exercise_id: str
    is_correct: bool
    score: float = Field(ge=0.0, le=1.0)
    correct_answer: str
    feedback: str
    explanation: str
    provider: str
    warning: str | None = None


class AttemptHistoryItem(BaseModel):
    id: str
    exercise_id: str
    question: str
    topic: str
    difficulty: Difficulty
    kind: ExerciseKind
    answer: str
    is_correct: bool
    score: float
    created_at: datetime
