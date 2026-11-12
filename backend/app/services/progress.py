from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import utcnow
from app.models.enums import Difficulty
from app.repositories.exercises import recent_attempts
from app.repositories.progress import overall_stats, stats_by_difficulty, stats_by_topic
from app.repositories.workspaces import get_workspace
from app.schemas.progress import (
    DifficultyStat,
    PlanStep,
    ProgressRead,
    RecentAttempt,
    StudyPlan,
    TopicStat,
)
from app.services.diagnostics import DiagnosticService
from app.services.mastery import MasteryService

_DIFFICULTY_ORDER = [Difficulty.BASIC, Difficulty.INTERMEDIATE, Difficulty.ADVANCED]


class ProgressService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_progress(self, workspace_id: str) -> ProgressRead:
        self._ensure_workspace(workspace_id)
        overall = overall_stats(self.session, workspace_id)

        difficulty_rows = stats_by_difficulty(self.session, workspace_id)
        difficulty_map = {row.key: row for row in difficulty_rows}
        by_difficulty = []
        for difficulty in _DIFFICULTY_ORDER:
            row = difficulty_map.get(difficulty.value)
            attempts = row.attempts if row else 0
            correct = row.correct if row else 0
            by_difficulty.append(
                DifficultyStat(
                    difficulty=difficulty,
                    attempts=attempts,
                    correct=correct,
                    accuracy=_accuracy(correct, attempts),
                )
            )

        topic_rows = sorted(
            stats_by_topic(self.session, workspace_id),
            key=lambda row: row.attempts,
            reverse=True,
        )
        by_topic = [
            TopicStat(
                topic=row.key,
                attempts=row.attempts,
                correct=row.correct,
                accuracy=_accuracy(row.correct, row.attempts),
            )
            for row in topic_rows
        ]
        weak_topics = sorted(
            [topic for topic in by_topic if topic.attempts > 0 and topic.accuracy < 0.7],
            key=lambda topic: (topic.accuracy, -topic.attempts),
        )[:5]

        mastery = MasteryService(self.session).overview(workspace_id)
        error_patterns = DiagnosticService(self.session).patterns(workspace_id, min_count=2)

        recent = [
            RecentAttempt(
                id=item.id,
                exercise_id=item.exercise_id,
                question=item.question,
                topic=item.topic,
                difficulty=item.difficulty,
                answer=item.answer,
                is_correct=item.is_correct,
                score=item.score,
                created_at=item.created_at,
            )
            for item in recent_attempts(self.session, workspace_id=workspace_id, limit=8)
        ]

        return ProgressRead(
            workspace_id=workspace_id,
            total_exercises=overall.total_exercises,
            attempted_exercises=overall.attempted_exercises,
            total_attempts=overall.attempts,
            correct_attempts=overall.correct,
            accuracy=_accuracy(overall.correct, overall.attempts),
            by_difficulty=by_difficulty,
            by_topic=by_topic,
            weak_topics=weak_topics,
            recent_attempts=recent,
            mastery=mastery.topics,
            due_topics=mastery.due_topics,
            error_patterns=error_patterns,
            average_mastery=mastery.average_mastery,
        )

    def get_study_plan(self, workspace_id: str) -> StudyPlan:
        progress = self.get_progress(workspace_id)

        if progress.total_attempts == 0:
            summary = (
                "Todavía no hay intentos. Empieza con un diagnóstico corto: así sabremos "
                "qué temas reforzar y podremos personalizar el plan."
            )
            initial_steps = [
                PlanStep(
                    title="Diagnóstico inicial",
                    reason="Necesitamos una muestra de tu nivel antes de adaptar el plan.",
                    action=(
                        "Genera 5 ejercicios básicos sobre todo el material "
                        "y respóndelos sin mirar apuntes."
                    ),
                    suggested_difficulty=Difficulty.BASIC,
                    suggested_count=5,
                ),
                PlanStep(
                    title="Revisa cada fallo",
                    reason="El primer objetivo es entender el porqué, no acertar por suerte.",
                    action="Lee la explicación de cada fallo y anota el concepto que no tenías claro.",
                    suggested_difficulty=Difficulty.BASIC,
                    suggested_count=3,
                ),
            ]
            return StudyPlan(
                workspace_id=workspace_id,
                summary=summary,
                steps=initial_steps,
                weak_topics=[],
                due_topics=[],
                error_patterns=[],
                generated_at=utcnow(),
            )

        steps: list[PlanStep] = []
        for due in progress.due_topics[:2]:
            steps.append(
                PlanStep(
                    title=f"Repaso programado: «{due.topic}»",
                    reason=(
                        f"El repaso espaciado marca este tema para hoy "
                        f"(dominio {due.mastery * 100:.0f}%)."
                    ),
                    action=f"Resuelve 3 ejercicios de «{due.topic}» sin mirar apuntes.",
                    focus_topic=due.topic,
                    suggested_difficulty=(
                        Difficulty.BASIC if due.mastery < 0.6 else Difficulty.INTERMEDIATE
                    ),
                    suggested_count=3,
                )
            )

        for pattern in progress.error_patterns[:2]:
            steps.append(
                PlanStep(
                    title=f"Rompe el patrón en «{pattern.topic}»",
                    reason=(
                        f"{pattern.count} fallos de tipo «{_error_label(pattern.error_type)}»: "
                        f"{pattern.detail}"
                    ),
                    action=(
                        "Abre la guía guiada de un ejercicio fallado, compara tu respuesta "
                        "con la explicación y genera una variación para comprobarlo."
                    ),
                    focus_topic=pattern.topic,
                    suggested_difficulty=Difficulty.BASIC,
                    suggested_count=3,
                )
            )

        for topic in progress.weak_topics[:3]:
            difficulty = Difficulty.BASIC if topic.accuracy < 0.6 else Difficulty.INTERMEDIATE
            steps.append(
                PlanStep(
                    title=f"Refuerza «{topic.topic}»",
                    reason=(
                        f"Aciertas el {topic.accuracy * 100:.0f}% en este tema "
                        f"({topic.correct}/{topic.attempts})."
                    ),
                    action=(
                        f"Genera {3 if difficulty is Difficulty.BASIC else 4} ejercicios "
                        f"{'básicos' if difficulty is Difficulty.BASIC else 'intermedios'} "
                        f"con foco «{topic.topic}» y explica en voz alta cada respuesta."
                    ),
                    focus_topic=topic.topic,
                    suggested_difficulty=difficulty,
                    suggested_count=3 if difficulty is Difficulty.BASIC else 4,
                )
            )

        if not progress.weak_topics:
            if progress.accuracy >= 0.8:
                summary = (
                    f"Buen dominio: {progress.accuracy * 100:.0f}% de acierto en "
                    f"{progress.total_attempts} intentos. Toca mantener y subir dificultad."
                )
                steps.append(
                    PlanStep(
                        title="Sube el listón",
                        reason="Tu precisión ya es alta; conviene practicar aplicación, no solo recuerdo.",
                        action="Genera 4 ejercicios avanzados mezclando temas y justifica cada respuesta.",
                        suggested_difficulty=Difficulty.ADVANCED,
                        suggested_count=4,
                    )
                )
            else:
                summary = (
                    f"Vas por {progress.accuracy * 100:.0f}% de acierto. No hay un tema claramente "
                    "débil todavía: conviene ampliar la muestra antes de decidir."
                )
                steps.append(
                    PlanStep(
                        title="Amplía el diagnóstico",
                        reason="Con pocos intentos las métricas por tema aún no son fiables.",
                        action="Genera 6 ejercicios mixtos (básico e intermedio) y revisa los fallos.",
                        suggested_difficulty=Difficulty.INTERMEDIATE,
                        suggested_count=6,
                    )
                )
        else:
            summary = (
                f"Llevas {progress.accuracy * 100:.0f}% de acierto en {progress.total_attempts} intentos. "
                f"Tu prioridad ahora es «{progress.weak_topics[0].topic}» "
                f"({progress.weak_topics[0].accuracy * 100:.0f}%)."
            )

        steps.append(
            PlanStep(
                title="Cierre con repaso espaciado",
                reason="Consolidar lo aprendido requiere volver a practicarlo en días distintos.",
                action=(
                    "Vuelve dentro de 2 días y repite 3 ejercicios de los temas trabajados, "
                    "incluyendo al menos uno avanzado."
                ),
                suggested_difficulty=Difficulty.ADVANCED,
                suggested_count=3,
            )
        )

        return StudyPlan(
            workspace_id=workspace_id,
            summary=summary,
            steps=steps,
            weak_topics=progress.weak_topics,
            due_topics=progress.due_topics,
            error_patterns=progress.error_patterns,
            generated_at=utcnow(),
        )

    def _ensure_workspace(self, workspace_id: str) -> None:
        if get_workspace(self.session, workspace_id) is None:
            raise NotFoundError("Evaluación no encontrada")


def _accuracy(correct: int, attempts: int) -> float:
    return round(correct / attempts, 3) if attempts else 0.0


_ERROR_LABELS = {
    "sin_respuesta": "sin respuesta",
    "seleccion_incorrecta": "opción incorrecta",
    "confusion_verdadero_falso": "confusión V/F",
    "concepto_ausente": "concepto ausente",
    "respuesta_incompleta": "respuesta incompleta",
}


def _error_label(error_type: str) -> str:
    return _ERROR_LABELS.get(error_type, error_type.replace("_", " "))
