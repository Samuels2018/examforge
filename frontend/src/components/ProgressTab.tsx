import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { difficultyLabels, errorMessage, formatDateTime, percent } from "../lib/format";
import type {
  GenerationMetrics,
  PlanStep,
  Progress,
  StudyPlan,
  WorkspaceSummary,
} from "../lib/types";
import { CheckIcon, SparkIcon, XIcon } from "./Icons";

interface ProgressTabProps {
  workspace: WorkspaceSummary;
  onPractice: (step: PlanStep) => Promise<void>;
}

interface ProgressData {
  progress: Progress;
  plan: StudyPlan;
  metrics: GenerationMetrics;
}

export function ProgressTab({ workspace, onPractice }: ProgressTabProps) {
  const [data, setData] = useState<ProgressData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [practicing, setPracticing] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      api.getProgress(workspace.id),
      api.getStudyPlan(workspace.id),
      api.getGenerationMetrics(workspace.id),
    ])
      .then(([progress, plan, metrics]) => {
        if (alive) {
          setData({ progress, plan, metrics });
          setError(null);
        }
      })
      .catch((cause) => {
        if (alive) {
          setError(errorMessage(cause));
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [workspace.id]);

  async function handlePractice(step: PlanStep) {
    setPracticing(step.title);
    setError(null);
    try {
      await onPractice(step);
    } catch (cause) {
      setError(errorMessage(cause));
      setPracticing(null);
    }
  }

  if (loading) {
    return <p className="muted">Calculando progreso y plan de ataque…</p>;
  }

  if (!data) {
    return (
      <section className="panel-stack">
        {error && <div className="alert danger">{error}</div>}
      </section>
    );
  }

  const { progress, plan, metrics } = data;
  const hasAttempts = progress.total_attempts > 0;

  return (
    <section className="panel-stack">
      <div className="section-heading">
        <div>
          <h2>Progreso y plan de ataque</h2>
          <p>
            Métricas reales de tus intentos, temas débiles y el siguiente paso concreto para
            mejorar.
          </p>
        </div>
      </div>

      {error && <div className="alert danger">{error}</div>}

      <div className="progress-overview">
        <div className="accuracy-card">
          <div
            className="accuracy-ring"
            style={{
              background: `conic-gradient(var(--accent) ${progress.accuracy * 360}deg, var(--surface-3) 0deg)`,
            }}
          >
            <div className="accuracy-inner">
              <strong>{percent(progress.accuracy)}</strong>
              <span>acierto</span>
            </div>
          </div>
          <div className="accuracy-copy">
            <h3>{hasAttempts ? "Tu precisión actual" : "Sin datos todavía"}</h3>
            <p>
              {hasAttempts
                ? `${progress.correct_attempts} aciertos de ${progress.total_attempts} intentos.`
                : "Haz el diagnóstico inicial para desbloquear el plan personalizado."}
            </p>
          </div>
        </div>

        <div className="stat-grid">
          <div className="stat-card">
            <strong>{progress.total_attempts}</strong>
            <span>intentos</span>
          </div>
          <div className="stat-card">
            <strong>
              {progress.attempted_exercises}/{progress.total_exercises}
            </strong>
            <span>ejercicios practicados</span>
          </div>
          <div className="stat-card">
            <strong>{progress.weak_topics.length}</strong>
            <span>temas a reforzar</span>
          </div>
          <div className="stat-card">
            <strong>{percent(progress.average_mastery)}</strong>
            <span>dominio medio</span>
          </div>
        </div>
      </div>

      <div className="panel-card">
        <h3>Rendimiento de generación</h3>
        <p className="muted">
          Control local de latencia, tokens y caché. Los tokens son estimados cuando el
          proveedor no los devuelve.
        </p>
        <div className="stat-grid">
          <div className="stat-card">
            <strong>{metrics.total_generations}</strong>
            <span>generaciones</span>
          </div>
          <div className="stat-card">
            <strong>{metrics.average_duration_ms} ms</strong>
            <span>latencia media</span>
          </div>
          <div className="stat-card">
            <strong>{metrics.average_tokens.toLocaleString("es")}</strong>
            <span>tokens medios</span>
          </div>
          <div className="stat-card">
            <strong>{percent(metrics.cache_hit_rate)}</strong>
            <span>aciertos de caché</span>
          </div>
        </div>
        {metrics.recent.length > 0 && (
          <p className="inline-hint-line">
            Última generación: {metrics.recent[0].status}
            {metrics.recent[0].cached ? " · servida desde caché" : ""} ·{" "}
            {metrics.recent[0].duration_ms} ms ·{" "}
            {metrics.recent[0].total_tokens.toLocaleString("es")} tokens.
          </p>
        )}
      </div>

      <div className="two-column">
        <div className="panel-card">
          <h3>Dominio y repaso espaciado</h3>
          {progress.mastery.length === 0 ? (
            <p className="muted">
              Responde algunos ejercicios para estimar tu dominio y programar repasos.
            </p>
          ) : (
            <div className="mastery-list">
              {progress.mastery.map((topic) => (
                <div key={topic.topic_key} className="mastery-row">
                  <div className="mastery-head">
                    <span>{topic.topic}</span>
                    <span className="mastery-value">
                      {percent(topic.mastery)}
                      {topic.is_due && <em className="due-pill">toca repasar</em>}
                    </span>
                  </div>
                  <div className="bar-track">
                    <div
                      className={`bar-fill mastery-fill ${topic.mastery < 0.5 ? "low" : ""}`}
                      style={{ width: `${Math.round(topic.mastery * 100)}%` }}
                    />
                  </div>
                  <span className="mastery-meta">
                    {topic.correct}/{topic.attempts} aciertos · próxima revisión en{" "}
                    {topic.interval_days} día{topic.interval_days === 1 ? "" : "s"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel-card">
          <h3>Errores recurrentes</h3>
          {progress.error_patterns.length === 0 ? (
            <p className="muted">
              Todavía no hay patrones repetidos. Si fallas dos veces del mismo modo, aparecerán aquí
              con una acción concreta.
            </p>
          ) : (
            <div className="pattern-list">
              {progress.error_patterns.map((pattern) => (
                <div key={`${pattern.topic}-${pattern.error_type}`} className="pattern-row">
                  <span className="pattern-count">×{pattern.count}</span>
                  <div>
                    <strong>
                      {pattern.topic} · {errorTypeLabels[pattern.error_type] ?? pattern.error_type}
                    </strong>
                    <p>{pattern.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="two-column">
        <div className="panel-card">
          <h3>Por dificultad</h3>
          <div className="bar-list">
            {progress.by_difficulty.map((stat) => (
              <div key={stat.difficulty} className="bar-row">
                <div className="bar-head">
                  <span>{difficultyLabels[stat.difficulty]}</span>
                  <span>
                    {stat.correct}/{stat.attempts}
                  </span>
                </div>
                <div className="bar-track">
                  <div
                    className={`bar-fill difficulty-${stat.difficulty}`}
                    style={{ width: `${Math.round(stat.accuracy * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel-card">
          <h3>Temas a reforzar</h3>
          {progress.weak_topics.length === 0 ? (
            <p className="muted">
              {hasAttempts
                ? "Ningún tema por debajo del 70% de acierto. Buen trabajo."
                : "Aún no hay suficiente información por tema."}
            </p>
          ) : (
            <div className="topic-list">
              {progress.weak_topics.map((topic) => (
                <div key={topic.topic} className="topic-chip">
                  <span>{topic.topic}</span>
                  <strong>{percent(topic.accuracy)}</strong>
                  <small>
                    {topic.correct}/{topic.attempts}
                  </small>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="plan-card">
        <div className="plan-head">
          <span className="plan-icon">
            <SparkIcon size={20} />
          </span>
          <div>
            <h3>Plan de ataque</h3>
            <p>{plan.summary}</p>
          </div>
        </div>

        <ol className="plan-steps">
          {plan.steps.map((step, position) => (
            <li key={`${step.title}-${position}`} className="plan-step">
              <span className="step-number">{position + 1}</span>
              <div className="step-body">
                <strong>{step.title}</strong>
                <p className="step-reason">{step.reason}</p>
                <p className="step-action">{step.action}</p>
                <div className="step-footer">
                  <span className={`difficulty-badge difficulty-${step.suggested_difficulty}`}>
                    {difficultyLabels[step.suggested_difficulty]}
                  </span>
                  <span className="step-count">{step.suggested_count} ejercicios</span>
                  <button
                    className="primary-button small"
                    onClick={() => void handlePractice(step)}
                    disabled={practicing !== null || workspace.material_count === 0}
                  >
                    {practicing === step.title ? "Generando…" : "Generar refuerzo"}
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div className="panel-card">
        <h3>Historial reciente</h3>
        {progress.recent_attempts.length === 0 ? (
          <p className="muted">Cuando respondas ejercicios verás aquí tu historial.</p>
        ) : (
          <div className="attempt-list">
            {progress.recent_attempts.map((attempt) => (
              <div
                key={attempt.id}
                className={`attempt-row ${attempt.is_correct ? "ok" : "ko"}`}
              >
                <span className="attempt-status">
                  {attempt.is_correct ? <CheckIcon size={15} /> : <XIcon size={15} />}
                </span>
                <div className="attempt-main">
                  <span className="attempt-question">{attempt.question}</span>
                  <span className="attempt-meta">
                    {attempt.topic} · {difficultyLabels[attempt.difficulty]} ·{" "}
                    {formatDateTime(attempt.created_at)}
                  </span>
                </div>
                <span className="attempt-score">{Math.round(attempt.score * 100)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}


const errorTypeLabels: Record<string, string> = {
  sin_respuesta: "sin respuesta",
  seleccion_incorrecta: "opción incorrecta",
  confusion_verdadero_falso: "confusión V/F",
  concepto_ausente: "concepto ausente",
  respuesta_incompleta: "respuesta incompleta",
};
