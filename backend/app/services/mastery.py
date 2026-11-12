import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Exercise, TopicMastery, new_id
from app.repositories.mastery import list_mastery, mastery_for_topics
from app.schemas.mastery import MasteryOverview, TopicMasteryRead


@dataclass(frozen=True)
class MasteryUpdate:
    topic: str
    score: float
    is_correct: bool


class MasteryService:
    """Actualiza dominio y agenda repasos con un SM-2 simplificado."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def overview(self, workspace_id: str) -> MasteryOverview:
        now = datetime.now(UTC)
        rows = list_mastery(self.session, workspace_id)
        topics = [_to_read(row, now) for row in rows]
        due = [topic for topic in topics if topic.is_due]
        average = round(sum(topic.mastery for topic in topics) / len(topics), 3) if topics else 0.0
        return MasteryOverview(
            workspace_id=workspace_id,
            topics=topics,
            due_topics=due,
            average_mastery=average,
        )

    def record_attempt(
        self,
        *,
        workspace_id: str,
        exercise: Exercise,
        score: float,
        is_correct: bool,
    ) -> TopicMastery:
        key = topic_key(exercise.topic)
        existing = mastery_for_topics(
            self.session, workspace_id=workspace_id, topic_keys=[key]
        ).get(key)
        if existing is None:
            existing = TopicMastery(
                id=new_id(),
                workspace_id=workspace_id,
                topic_key=key,
                topic=exercise.topic[:200],
                attempts=0,
                correct=0,
                mastery=0.0,
                streak=0,
                ease=2.5,
                interval_days=1,
                due_at=datetime.now(UTC),
            )
            self.session.add(existing)
        _apply(existing, topic=exercise.topic, score=score, is_correct=is_correct)
        return existing

    def record_many(self, *, workspace_id: str, updates: list[MasteryUpdate]) -> None:
        if not updates:
            return
        keys = [topic_key(update.topic) for update in updates]
        existing = mastery_for_topics(self.session, workspace_id=workspace_id, topic_keys=keys)
        for update, key in zip(updates, keys, strict=True):
            row = existing.get(key)
            if row is None:
                row = TopicMastery(
                    id=new_id(),
                    workspace_id=workspace_id,
                    topic_key=key,
                    topic=update.topic[:200],
                    attempts=0,
                    correct=0,
                    mastery=0.0,
                    streak=0,
                    ease=2.5,
                    interval_days=1,
                    due_at=datetime.now(UTC),
                )
                self.session.add(row)
                existing[key] = row
            _apply(row, topic=update.topic, score=update.score, is_correct=update.is_correct)


def topic_key(topic: str) -> str:
    normalized = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", " ", normalized.casefold())
    return " ".join(normalized.split())[:200] or "general"


def _apply(row: TopicMastery, *, topic: str, score: float, is_correct: bool) -> None:
    now = datetime.now(UTC)
    score = max(0.0, min(1.0, score))
    previous_attempts = row.attempts
    row.topic = topic[:200]
    row.attempts += 1
    if is_correct:
        row.correct += 1
    row.mastery = round(
        score if previous_attempts == 0 else max(0.0, min(1.0, 0.65 * row.mastery + 0.35 * score)),
        3,
    )

    quality = _quality(score)
    if quality < 3:
        row.streak = 0
        row.interval_days = 1
        row.ease = max(1.3, round(row.ease - 0.2, 2))
    else:
        row.ease = round(max(1.3, min(3.0, row.ease + (0.1 - (5 - quality) * 0.08))), 2)
        if row.streak == 0:
            row.interval_days = 1
        elif row.streak == 1:
            row.interval_days = 3
        else:
            row.interval_days = min(180, max(4, round(row.interval_days * row.ease)))
        row.streak += 1

    row.last_attempt_at = now
    row.due_at = now + timedelta(days=row.interval_days)
    row.updated_at = now


def _quality(score: float) -> int:
    if score >= 0.95:
        return 5
    if score >= 0.8:
        return 4
    if score >= 0.6:
        return 3
    if score >= 0.4:
        return 2
    if score > 0:
        return 1
    return 0


def _to_read(row: TopicMastery, now: datetime) -> TopicMasteryRead:
    due = row.due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=UTC)
    last = row.last_attempt_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return TopicMasteryRead(
        topic=row.topic,
        topic_key=row.topic_key,
        attempts=row.attempts,
        correct=row.correct,
        accuracy=round(row.correct / row.attempts, 3) if row.attempts else 0.0,
        mastery=round(row.mastery, 3),
        streak=row.streak,
        interval_days=row.interval_days,
        due_at=due,
        last_attempt_at=last,
        is_due=due <= now,
    )
