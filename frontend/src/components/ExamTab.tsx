import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "../lib/api";
import { difficultyLabels, errorMessage, kindLabels, percent } from "../lib/format";
import type {
  Difficulty,
  Exam,
  ExamResult,
  ExamResultItem,
  WorkspaceSummary,
} from "../lib/types";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  FlagIcon,
  TimerIcon,
  XIcon,
} from "./Icons";

interface ExamTabProps {
  workspace: WorkspaceSummary;
  onChanged: () => void;
}

const ALL_DIFFICULTIES: Difficulty[] = ["basic", "intermediate", "advanced"];

export function ExamTab({ workspace, onChanged }: ExamTabProps) {
  const [phase, setPhase] = useState<"setup" | "active" | "result">("setup");
  const [count, setCount] = useState(5);
  const [minutes, setMinutes] = useState(20);
  const [difficulties, setDifficulties] = useState<Difficulty[]>(ALL_DIFFICULTIES);
  const [exam, setExam] = useState<Exam | null>(null);
  const [result, setResult] = useState<ExamResult | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [index, setIndex] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const examRef = useRef<Exam | null>(null);
  const answersRef = useRef<Record<string, string>>({});
  const submitInFlight = useRef(false);

  useEffect(() => {
    examRef.current = exam;
  }, [exam]);

  useEffect(() => {
    answersRef.current = answers;
  }, [answers]);

  const submitExam = useCallback(
    async (automatic: boolean) => {
      const currentExam = examRef.current;
      if (!currentExam || submitInFlight.current) {
        return;
      }
      const answered = currentExam.questions.filter(
        (question) => (answersRef.current[question.id] ?? "").trim().length > 0,
      ).length;
      if (!automatic && answered < currentExam.questions.length) {
        const missing = currentExam.questions.length - answered;
        const confirmed = window.confirm(
          `Quedan ${missing} pregunta${missing === 1 ? "" : "s"} sin responder. ¿Entregar igualmente?`,
        );
        if (!confirmed) {
          return;
        }
      }

      submitInFlight.current = true;
      setSubmitting(true);
      setError(null);
      try {
        const elapsed = Math.max(
          0,
          Math.floor((Date.now() - Date.parse(currentExam.started_at)) / 1000),
        );
        const response = await api.submitExam(workspace.id, currentExam.id, {
          answers: currentExam.questions.map((question) => ({
            item_id: question.id,
            answer: answersRef.current[question.id] ?? "",
          })),
          duration_seconds: Math.min(elapsed, currentExam.time_limit_seconds + 30),
        });
        setResult(response);
        setExam(null);
        setPhase("result");
        onChanged();
      } catch (cause) {
        setError(errorMessage(cause));
      } finally {
        submitInFlight.current = false;
        setSubmitting(false);
      }
    },
    [onChanged, workspace.id],
  );

  useEffect(() => {
    if (phase !== "active" || !exam) {
      return;
    }
    const deadline = Date.parse(exam.expires_at);
    const tick = () => {
      const left = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
      setRemaining(left);
      if (left === 0) {
        void submitExam(true);
      }
    };
    tick();
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
  }, [exam, phase, submitExam]);

  function toggleDifficulty(difficulty: Difficulty) {
    setDifficulties((current) =>
      current.includes(difficulty)
        ? current.filter((item) => item !== difficulty)
        : [...current, difficulty],
    );
  }

  async function handleStart(event: FormEvent) {
    event.preventDefault();
    if (difficulties.length === 0) {
      setError("Elige al menos una dificultad.");
      return;
    }
    if (count > workspace.exercise_count) {
      setError(
        `Solo hay ${workspace.exercise_count} ejercicios en el banco. Baja el número o genera más.`,
      );
      return;
    }
    setStarting(true);
    setError(null);
    try {
      const started = await api.startExam(workspace.id, {
        count,
        difficulties,
        time_limit_minutes: minutes,
      });
      setExam(started);
      setAnswers(Object.fromEntries(started.questions.map((question) => [question.id, ""])));
      setIndex(0);
      setRemaining(started.seconds_remaining);
      setResult(null);
      setPhase("active");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setStarting(false);
    }
  }

  function reset() {
    setPhase("setup");
    setExam(null);
    setResult(null);
    setAnswers({});
    setIndex(0);
    setError(null);
  }

  if (phase === "result" && result) {
    return <ExamResultView result={result} onReset={reset} />;
  }

  if (phase === "active" && exam) {
    const question = exam.questions[index];
    const answer = answers[question.id] ?? "";
    const answeredCount = exam.questions.filter(
      (item) => (answers[item.id] ?? "").trim().length > 0,
    ).length;
    return (
      <section className="panel-stack">
        <div className="exam-topbar">
          <div>
            <span className="eyebrow">Examen cronometrado</span>
            <h2>{answeredCount} de {exam.total_questions} respondidas</h2>
          </div>
          <div className={`exam-clock ${remaining <= 60 ? "urgent" : ""}`}>
            <TimerIcon size={20} />
            <strong>{formatClock(remaining)}</strong>
            <span>restante</span>
          </div>
        </div>

        {error && <div className="alert danger">{error}</div>}

        <div className="exam-question-nav" aria-label="Preguntas del examen">
          {exam.questions.map((item, position) => {
            const done = (answers[item.id] ?? "").trim().length > 0;
            return (
              <button
                key={item.id}
                className={`exam-nav-dot ${position === index ? "active" : ""} ${
                  done ? "answered" : ""
                }`}
                onClick={() => setIndex(position)}
                aria-label={`Ir a la pregunta ${position + 1}${done ? ", respondida" : ""}`}
              >
                {position + 1}
              </button>
            );
          })}
        </div>

        <div className="runner exam-runner">
          <div className="runner-topline">
            <span className="runner-count">
              Pregunta {index + 1} de {exam.total_questions}
            </span>
            <span className="runner-timer">{answeredCount} respondidas</span>
          </div>
          <div className="progress-track" aria-hidden="true">
            <div
              className="progress-fill"
              style={{ width: `${((index + 1) / exam.total_questions) * 100}%` }}
            />
          </div>

          <div className="runner-badges">
            <span className={`difficulty-badge difficulty-${question.difficulty}`}>
              {difficultyLabels[question.difficulty]}
            </span>
            <span className="kind-badge">{kindLabels[question.kind]}</span>
            <span className="topic-badge">{question.topic}</span>
          </div>

          <h3 className="question-text">{question.question}</h3>

          {question.kind === "multiple_choice" && (
            <div className="option-list">
              {question.options.map((option) => (
                <button
                  key={option.id}
                  className={`option-button ${answer === option.id ? "selected" : ""}`}
                  onClick={() =>
                    setAnswers((current) => ({ ...current, [question.id]: option.id }))
                  }
                >
                  <span className="option-letter">{option.id.toUpperCase()}</span>
                  <span>{option.text}</span>
                </button>
              ))}
            </div>
          )}

          {question.kind === "true_false" && (
            <div className="true-false-grid">
              {[
                { value: "true", label: "Verdadero" },
                { value: "false", label: "Falso" },
              ].map((option) => (
                <button
                  key={option.value}
                  className={`tf-button ${answer === option.value ? "selected" : ""}`}
                  onClick={() =>
                    setAnswers((current) => ({ ...current, [question.id]: option.value }))
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}

          {question.kind === "short_answer" && (
            <label className="short-answer-field">
              Tu respuesta
              <textarea
                value={answer}
                onChange={(event) =>
                  setAnswers((current) => ({ ...current, [question.id]: event.target.value }))
                }
                placeholder="Responde con tus palabras. No hay corrección hasta entregar."
                rows={5}
              />
            </label>
          )}

          <div className="runner-actions">
            <button
              className="ghost-button"
              onClick={() => setIndex((current) => Math.max(0, current - 1))}
              disabled={index === 0}
            >
              <ArrowLeftIcon size={16} />
              Anterior
            </button>
            {index + 1 < exam.total_questions ? (
              <button
                className="primary-button"
                onClick={() =>
                  setIndex((current) => Math.min(exam.total_questions - 1, current + 1))
                }
              >
                Siguiente
                <ArrowRightIcon size={16} />
              </button>
            ) : (
              <button
                className="primary-button"
                onClick={() => void submitExam(false)}
                disabled={submitting}
              >
                <FlagIcon size={16} />
                {submitting ? "Corrigiendo…" : "Entregar examen"}
              </button>
            )}
          </div>
        </div>

        <div className="exam-submit-row">
          <span className="muted">
            Puedes navegar y cambiar respuestas hasta entregar. El tiempo se agota solo.
          </span>
          <button
            className="secondary-button"
            onClick={() => void submitExam(false)}
            disabled={submitting}
          >
            {submitting ? "Corrigiendo…" : "Entregar ahora"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="panel-stack">
      <div className="section-heading">
        <div>
          <h2>Modo examen</h2>
          <p>
            Simula el día del examen: preguntas del banco, tiempo límite y corrección al entregar.
          </p>
        </div>
        <div className="heading-stat">
          <strong>{workspace.exercise_count}</strong>
          <span>disponibles</span>
        </div>
      </div>

      {error && <div className="alert danger">{error}</div>}

      <form className="generator-card" onSubmit={handleStart}>
        <div className="generator-head">
          <span className="generator-icon">
            <TimerIcon size={20} />
          </span>
          <div>
            <h3>Configura tu simulacro</h3>
            <p>Sin pistas ni corrección inmediata. Al terminar verás el detalle de cada fallo.</p>
          </div>
        </div>

        <div className="generator-grid exam-config-grid">
          <label className="field">
            Preguntas
            <input
              type="number"
              min={1}
              max={Math.max(1, workspace.exercise_count)}
              value={count}
              onChange={(event) =>
                setCount(Math.max(1, Number(event.target.value) || 1))
              }
            />
          </label>

          <label className="field">
            Minutos
            <input
              type="number"
              min={5}
              max={240}
              value={minutes}
              onChange={(event) =>
                setMinutes(Math.max(5, Math.min(240, Number(event.target.value) || 5)))
              }
            />
          </label>

          <div className="field">
            Dificultad
            <div className="difficulty-picker">
              {ALL_DIFFICULTIES.map((difficulty) => (
                <button
                  type="button"
                  key={difficulty}
                  className={`choice-chip ${difficulties.includes(difficulty) ? "active" : ""}`}
                  onClick={() => toggleDifficulty(difficulty)}
                >
                  {difficultyLabels[difficulty]}
                </button>
              ))}
            </div>
          </div>
        </div>

        {workspace.exercise_count === 0 && (
          <p className="inline-hint">
            Primero genera ejercicios en la pestaña «Ejercicios». El examen reutiliza tu banco.
          </p>
        )}

        <div className="generator-actions">
          <button
            className="primary-button"
            type="submit"
            disabled={
              starting ||
              difficulties.length === 0 ||
              workspace.exercise_count === 0 ||
              count > workspace.exercise_count
            }
          >
            <TimerIcon size={17} />
            {starting ? "Preparando examen…" : "Empezar examen"}
          </button>
          <span className="generator-footnote">
            {count} preguntas · {minutes} minutos · sin ayudas
          </span>
        </div>
      </form>

      <div className="exam-info-grid">
        <div className="panel-card">
          <h3>Qué mide</h3>
          <p className="muted">
            Recuperación activa bajo presión: sin pistas, con navegación libre y un límite de
            tiempo real.
          </p>
        </div>
        <div className="panel-card">
          <h3>Qué ocurre al entregar</h3>
          <p className="muted">
            Se corrigen todas las respuestas, se actualiza tu dominio por tema y se añaden los
            fallos al diagnóstico de patrones.
          </p>
        </div>
      </div>
    </section>
  );
}

function ExamResultView({ result, onReset }: { result: ExamResult; onReset: () => void }) {
  return (
    <section className="panel-stack">
      <div className="exam-result-hero">
        <div>
          <span className="eyebrow">
            {result.status === "expired" ? "Tiempo agotado" : "Examen entregado"}
          </span>
          <h2>
            {result.correct_count} de {result.total_questions} correctas
          </h2>
          <p>
            {result.duration_seconds !== null
              ? `Tiempo empleado: ${formatClock(result.duration_seconds)}.`
              : "Sin tiempo registrado."}{" "}
            Revisa abajo cada respuesta y el porqué.
          </p>
        </div>
        <div className="exam-score-ring">
          <strong>{percent(result.score)}</strong>
          <span>puntuación</span>
        </div>
      </div>

      <div className="exam-result-list">
        {result.items.map((item) => (
          <ExamResultCard key={item.id} item={item} />
        ))}
      </div>

      <div className="runner-actions">
        <button className="primary-button" onClick={onReset}>
          <TimerIcon size={16} />
          Hacer otro examen
        </button>
      </div>
    </section>
  );
}

function ExamResultCard({ item }: { item: ExamResultItem }) {
  return (
    <article className={`exam-result-card ${item.is_correct ? "ok" : "ko"}`}>
      <div className="exam-result-head">
        <span className="attempt-status">
          {item.is_correct ? <CheckIcon size={16} /> : <XIcon size={16} />}
        </span>
        <div>
          <strong>
            {item.position}. {item.question}
          </strong>
          <span className="attempt-meta">
            {item.topic} · {difficultyLabels[item.difficulty]} · {kindLabels[item.kind]}
          </span>
        </div>
        <span className="score-pill">{Math.round(item.score * 100)}%</span>
      </div>
      <div className="exam-answer-grid">
        <div>
          <span className="result-label">Tu respuesta</span>
          <p>{formatExamAnswer(item, item.answer) || "Sin responder"}</p>
        </div>
        <div>
          <span className="result-label">Respuesta correcta</span>
          <p>{item.correct_answer}</p>
        </div>
      </div>
      <p className="exam-feedback">{item.feedback}</p>
      <div className="result-block">
        <span className="result-label">Por qué</span>
        <p>{item.explanation}</p>
      </div>
    </article>
  );
}

function formatExamAnswer(item: ExamResultItem, answer: string) {
  if (!answer) {
    return "";
  }
  if (item.kind === "multiple_choice") {
    const option = item.options.find((candidate) => candidate.id === answer);
    return option ? `${answer.toUpperCase()}: ${option.text}` : answer;
  }
  if (item.kind === "true_false") {
    return answer === "true" ? "Verdadero" : answer === "false" ? "Falso" : answer;
  }
  return answer;
}

function formatClock(totalSeconds: number) {
  const safe = Math.max(0, totalSeconds);
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
