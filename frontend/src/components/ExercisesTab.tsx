import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { api } from "../lib/api";
import { difficultyLabels, kindLabels, errorMessage } from "../lib/format";
import type {
  AttemptResult,
  Difficulty,
  Exercise,
  Guide,
  WorkspaceSummary,
} from "../lib/types";
import { ExerciseRunner } from "./ExerciseRunner";
import { GuidePanel } from "./GuidePanel";
import { BulbIcon, SparkIcon } from "./Icons";

interface ExercisesTabProps {
  workspace: WorkspaceSummary;
  onChanged: () => void;
}

interface GenerationNotice {
  created: number;
  provider: string;
  warning: string | null;
  cached: boolean;
  durationMs: number;
  totalTokens: number;
}

const ALL_DIFFICULTIES: Difficulty[] = ["basic", "intermediate", "advanced"];

export function ExercisesTab({ workspace, onChanged }: ExercisesTabProps) {
  const [items, setItems] = useState<Exercise[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<GenerationNotice | null>(null);

  const [count, setCount] = useState(6);
  const [difficulties, setDifficulties] = useState<Difficulty[]>(ALL_DIFFICULTIES);
  const [focus, setFocus] = useState("");
  const [generating, setGenerating] = useState(false);
  const [generationId, setGenerationId] = useState<string | null>(null);
  const [progressMessage, setProgressMessage] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  const [index, setIndex] = useState(0);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideLoading, setGuideLoading] = useState(false);
  const [guideError, setGuideError] = useState<string | null>(null);
  const [variationLoading, setVariationLoading] = useState(false);
  const [variationNotice, setVariationNotice] = useState<string | null>(null);

  const loadExercises = useCallback(async () => {
    setLoading(true);
    try {
      const page = await api.listExercises(workspace.id);
      setItems(page.items);
      setTotal(page.total);
      setIndex(0);
      setResult(null);
      setGuide(null);
      setGuideOpen(false);
      setGuideError(null);
      setVariationNotice(null);
      setError(null);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, [workspace.id]);

  useEffect(() => {
    void loadExercises();
  }, [loadExercises]);

  function toggleDifficulty(difficulty: Difficulty) {
    setDifficulties((current) =>
      current.includes(difficulty)
        ? current.filter((item) => item !== difficulty)
        : [...current, difficulty],
    );
  }

  async function handleGenerate(event: FormEvent) {
    event.preventDefault();
    if (difficulties.length === 0) {
      setError("Elige al menos una dificultad.");
      return;
    }
    setGenerating(true);
    setError(null);
    setNotice(null);
    setProgressMessage("Iniciando generación…");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await api.generateExercisesStream(
        workspace.id,
        {
          count,
          difficulties,
          focus: focus.trim() || null,
        },
        {
          onStart: setGenerationId,
          onProgress: (message) => setProgressMessage(message),
        },
        controller.signal,
      );
      setNotice({
        created: response.created,
        provider: response.provider,
        warning: response.warning,
        cached: response.cached,
        durationMs: response.duration_ms,
        totalTokens: response.usage?.total_tokens ?? 0,
      });
      await loadExercises();
      onChanged();
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        setProgressMessage("");
        setNotice(null);
      } else {
        setError(errorMessage(cause));
      }
    } finally {
      setGenerating(false);
      setGenerationId(null);
      setProgressMessage("");
      abortRef.current = null;
    }
  }

  async function handleCancelGeneration() {
    setProgressMessage("Cancelando generación…");
    if (generationId) {
      try {
        await api.cancelGeneration(workspace.id, generationId);
      } catch {
        // El abort local sigue siendo útil aunque la generación ya haya terminado.
      }
    }
    abortRef.current?.abort();
  }

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  async function handleSubmit(answer: string, durationSeconds: number) {
    const current = items[index];
    if (!current || result) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const attempt = await api.submitAttempt(workspace.id, current.id, {
        answer,
        duration_seconds: durationSeconds,
      });
      setResult(attempt);
      onChanged();
      if (!attempt.is_correct) {
        void openGuideFor(current.id);
      }
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  function goNext() {
    if (items.length === 0) {
      return;
    }
    setIndex((current) => (current + 1) % items.length);
    setResult(null);
    setGuide(null);
    setGuideOpen(false);
    setVariationNotice(null);
  }

  function goPrevious() {
    if (items.length === 0) {
      return;
    }
    setIndex((current) => (current - 1 + items.length) % items.length);
    setResult(null);
    setGuide(null);
    setGuideOpen(false);
    setVariationNotice(null);
  }

  async function openGuideFor(exerciseId: string) {
    setGuideOpen(true);
    if (guide?.exercise_id === exerciseId) {
      return;
    }
    setGuideLoading(true);
    setGuideError(null);
    try {
      const loaded = await api.getExerciseGuide(workspace.id, exerciseId);
      setGuide(loaded);
    } catch (cause) {
      setGuideError(errorMessage(cause));
    } finally {
      setGuideLoading(false);
    }
  }

  async function handleGuide() {
    if (!current) {
      return;
    }
    if (guideOpen) {
      setGuideOpen(false);
      return;
    }
    await openGuideFor(current.id);
  }

  async function handleVariation() {
    if (!current) {
      return;
    }
    setVariationLoading(true);
    setVariationNotice(null);
    setError(null);
    try {
      const response = await api.generateVariation(workspace.id, current.id);
      await loadExercises();
      setVariationNotice(
        `${response.created} variación${response.created === 1 ? "" : "es"} creada${
          response.created === 1 ? "" : "s"
        } para «${current.topic}».`,
      );
      onChanged();
    } catch (cause) {
      setGuideError(errorMessage(cause));
    } finally {
      setVariationLoading(false);
    }
  }

  const current = items[index] ?? null;

  return (
    <section className="panel-stack">
      <div className="section-heading">
        <div>
          <h2>Ejercicios interactivos</h2>
          <p>
            Genera lotes desde tu material, responde y recibe corrección con la explicación del
            concepto.
          </p>
        </div>
        <div className="heading-stat">
          <strong>{total}</strong>
          <span>en el banco</span>
        </div>
      </div>

      <form className="generator-card" onSubmit={handleGenerate}>
        <div className="generator-head">
          <span className="generator-icon">
            <SparkIcon size={20} />
          </span>
          <div>
            <h3>Crear un lote de práctica</h3>
            <p>Mezcla dificultades o céntrate en un tema concreto.</p>
          </div>
        </div>

        <div className="generator-grid">
          <label className="field">
            Ejercicios
            <input
              type="number"
              min={1}
              max={30}
              value={count}
              onChange={(event) =>
                setCount(Math.max(1, Math.min(30, Number(event.target.value) || 1)))
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

          <label className="field focus-field">
            Foco (opcional)
            <input
              value={focus}
              onChange={(event) => setFocus(event.target.value)}
              placeholder="Ej.: TCP, derivadas, Revolución francesa"
              maxLength={300}
            />
          </label>
        </div>

        {workspace.material_count === 0 && (
          <p className="inline-hint">
            Primero sube material en la pestaña «Materiales». Sin texto no hay de dónde generar.
          </p>
        )}

        <div className="generator-actions">
          {generating ? (
            <button
              className="secondary-button"
              type="button"
              onClick={() => void handleCancelGeneration()}
            >
              Cancelar generación
            </button>
          ) : (
            <button
              className="primary-button"
              type="submit"
              disabled={difficulties.length === 0 || count < 1 || workspace.material_count === 0}
            >
              <SparkIcon size={17} />
              Generar {count} ejercicios
            </button>
          )}
          <span className="generator-footnote" aria-live="polite">
            {generating
              ? progressMessage || "Generando y validando…"
              : `Proveedor: ${workspace.material_count > 0 ? "Ollama u offline" : "sin material"}`}
          </span>
        </div>
      </form>

      {notice && (
        <div className={`alert ${notice.warning ? "warning" : "info"}`}>
          <strong>{notice.created} ejercicios nuevos</strong> ·{" "}
          {notice.cached ? "recuperado de caché" : `generado con ${notice.provider}`} en{" "}
          {notice.durationMs} ms
          {notice.totalTokens > 0 ? ` · ${notice.totalTokens.toLocaleString("es")} tokens` : ""}.
          {notice.warning ? ` ${notice.warning}` : ""}
        </div>
      )}
      {variationNotice && <div className="alert info">{variationNotice}</div>}
      {error && <div className="alert danger">{error}</div>}

      {loading && <p className="muted">Cargando ejercicios…</p>}

      {!loading && items.length === 0 && (
        <div className="empty-card">
          <SparkIcon size={28} />
          <h3>Tu banco está vacío</h3>
          <p>
            Genera el primer lote. Si fallas, podrás ver la explicación y el plan de refuerzo se
            actualizará con tus temas débiles.
          </p>
        </div>
      )}

      {!loading && current && (
        <ExerciseRunner
          exercise={current}
          index={index}
          total={items.length}
          result={result}
          submitting={submitting}
          onSubmit={(answer, duration) => void handleSubmit(answer, duration)}
          onNext={goNext}
          onPrevious={goPrevious}
        />
      )}

      {result && current && (
        <div className="guide-launch">
          <button className="ghost-button" onClick={() => void handleGuide()}>
            <BulbIcon size={16} />
            {guideOpen ? "Ocultar guía" : "Guía guiada"}
          </button>
          <span className="inline-hint-line">
            Si el fallo se repite, la guía y la variación te ayudan a comprobar si ya lo entiendes.
          </span>
        </div>
      )}

      {result && guideOpen && (
        <GuidePanel
          guide={guide}
          loading={guideLoading}
          error={guideError}
          variationLoading={variationLoading}
          variationNotice={variationNotice}
          onVariation={() => void handleVariation()}
        />
      )}

      {items.length > 1 && (
        <div className="bank-card">
          <div className="bank-head">
            <h3>Lote actual</h3>
            <span>{items.length} ejercicios</span>
          </div>
          <div className="bank-list">
            {items.map((exercise, position) => (
              <button
                key={exercise.id}
                className={`bank-item ${position === index ? "active" : ""}`}
                onClick={() => {
                  setIndex(position);
                  setResult(null);
                  setGuide(null);
                  setGuideOpen(false);
                  setVariationNotice(null);
                }}
              >
                <span className={`bank-dot difficulty-${exercise.difficulty}`} />
                <span className="bank-question">{exercise.question}</span>
                <span className="bank-meta">
                  {difficultyLabels[exercise.difficulty]} · {kindLabels[exercise.kind]}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
