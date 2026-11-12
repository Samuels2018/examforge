import { useEffect, useState } from "react";

import { difficultyLabels, kindLabels } from "../lib/format";
import type { AttemptResult, Exercise } from "../lib/types";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BulbIcon,
  CheckIcon,
  XIcon,
} from "./Icons";

interface ExerciseRunnerProps {
  exercise: Exercise;
  index: number;
  total: number;
  result: AttemptResult | null;
  submitting: boolean;
  onSubmit: (answer: string, durationSeconds: number) => void;
  onNext: () => void;
  onPrevious: () => void;
}

export function ExerciseRunner({
  exercise,
  index,
  total,
  result,
  submitting,
  onSubmit,
  onNext,
  onPrevious,
}: ExerciseRunnerProps) {
  const [answer, setAnswer] = useState("");
  const [showHint, setShowHint] = useState(false);
  const [startedAt, setStartedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setAnswer("");
    setShowHint(false);
    setStartedAt(Date.now());
    setElapsed(0);
  }, [exercise.id]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [startedAt]);

  const correctOptionId =
    result && exercise.kind === "multiple_choice"
      ? result.correct_answer.split(":")[0]?.trim()
      : null;

  const canSubmit = !result && !submitting && answer.trim().length > 0;

  function choose(value: string) {
    if (!result) {
      setAnswer(value);
    }
  }

  return (
    <div className="runner">
      <div className="runner-topline">
        <span className="runner-count">
          Ejercicio {index + 1} de {total}
        </span>
        <span className="runner-timer">{elapsed}s</span>
      </div>
      <div className="progress-track" aria-hidden="true">
        <div className="progress-fill" style={{ width: `${((index + 1) / total) * 100}%` }} />
      </div>

      <div className="runner-badges">
        <span className={`difficulty-badge difficulty-${exercise.difficulty}`}>
          {difficultyLabels[exercise.difficulty]}
        </span>
        <span className="kind-badge">{kindLabels[exercise.kind]}</span>
        <span className="topic-badge">{exercise.topic}</span>
      </div>

      <h3 className="question-text">{exercise.question}</h3>

      {exercise.kind === "multiple_choice" && (
        <div className="option-list">
          {exercise.options.map((option) => {
            const isSelected = answer === option.id;
            const isCorrect = correctOptionId === option.id;
            const isWrong = Boolean(result && isSelected && !isCorrect);
            const classes = [
              "option-button",
              isSelected ? "selected" : "",
              isCorrect ? "correct" : "",
              isWrong ? "wrong" : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <button
                key={option.id}
                className={classes}
                onClick={() => choose(option.id)}
                disabled={Boolean(result)}
              >
                <span className="option-letter">{option.id.toUpperCase()}</span>
                <span>{option.text}</span>
                {isCorrect && <span className="option-mark"><CheckIcon size={16} /></span>}
                {isWrong && <span className="option-mark"><XIcon size={16} /></span>}
              </button>
            );
          })}
        </div>
      )}

      {exercise.kind === "true_false" && (
        <div className="true-false-grid">
          {[
            { value: "true", label: "Verdadero" },
            { value: "false", label: "Falso" },
          ].map((option) => {
            const isSelected = answer === option.value;
            const isCorrect = Boolean(
              result &&
                result.correct_answer.toLocaleLowerCase("es").startsWith(
                  option.value === "true" ? "verdadero" : "falso",
                ),
            );
            return (
              <button
                key={option.value}
                className={`tf-button ${isSelected ? "selected" : ""} ${
                  isCorrect ? "correct" : ""
                }`}
                onClick={() => choose(option.value)}
                disabled={Boolean(result)}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      )}

      {exercise.kind === "short_answer" && (
        <label className="short-answer-field">
          Tu respuesta
          <textarea
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            placeholder="Escribe la respuesta con tus palabras…"
            rows={4}
            disabled={Boolean(result)}
          />
        </label>
      )}

      {exercise.hint && !result && (
        <div className="hint-row">
          <button className="ghost-button small" onClick={() => setShowHint((value) => !value)}>
            <BulbIcon size={16} />
            {showHint ? "Ocultar pista" : "Ver pista"}
          </button>
          {showHint && <span className="hint-text">{exercise.hint}</span>}
        </div>
      )}

      {!result && (
        <div className="runner-actions">
          <button className="ghost-button" onClick={onPrevious} disabled={total <= 1 || submitting}>
            <ArrowLeftIcon size={16} />
            Anterior
          </button>
          <button
            className="primary-button"
            onClick={() => onSubmit(answer.trim(), elapsed)}
            disabled={!canSubmit}
          >
            {submitting ? "Corrigiendo…" : "Comprobar respuesta"}
            <ArrowRightIcon size={16} />
          </button>
        </div>
      )}

      {result && (
        <div className={`result-card ${result.is_correct ? "success" : "failure"}`}>
          <div className="result-head">
            <span className="result-icon">
              {result.is_correct ? <CheckIcon size={20} /> : <XIcon size={20} />}
            </span>
            <div>
              <strong>{result.is_correct ? "Respuesta correcta" : "Todavía no"}</strong>
              <p>{result.feedback}</p>
            </div>
            <span className="score-pill">{Math.round(result.score * 100)}%</span>
          </div>

          <div className="result-block">
            <span className="result-label">Respuesta correcta</span>
            <p>{result.correct_answer}</p>
          </div>

          <div className="result-block">
            <span className="result-label">Por qué</span>
            <p>{result.explanation}</p>
          </div>

          {(result.provider !== "deterministic" || result.warning) && (
            <p className="result-footnote">
              Corrección: {result.provider}
              {result.warning ? ` · ${result.warning}` : ""}
            </p>
          )}

          <div className="runner-actions">
            <button className="ghost-button" onClick={onPrevious} disabled={total <= 1}>
              <ArrowLeftIcon size={16} />
              Anterior
            </button>
            <button className="primary-button" onClick={onNext}>
              {index + 1 === total ? "Repetir desde el inicio" : "Siguiente ejercicio"}
              <ArrowRightIcon size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
