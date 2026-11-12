import type { Guide } from "../lib/types";
import { BulbIcon, SparkIcon } from "./Icons";

interface GuidePanelProps {
  guide: Guide | null;
  loading: boolean;
  error: string | null;
  variationLoading: boolean;
  variationNotice: string | null;
  onVariation: () => void;
}

export function GuidePanel({
  guide,
  loading,
  error,
  variationLoading,
  variationNotice,
  onVariation,
}: GuidePanelProps) {
  return (
    <div className="guide-card">
      <div className="guide-head">
        <span className="guide-icon">
          <BulbIcon size={19} />
        </span>
        <div>
          <h3>Guía guiada</h3>
          <p>Entiende el concepto, revisa el ejemplo y comprueba el razonamiento paso a paso.</p>
        </div>
      </div>

      {loading && <p className="muted">Preparando la guía…</p>}
      {error && <div className="alert danger">{error}</div>}

      {guide && !loading && (
        <>
          <div className="guide-section">
            <span className="result-label">Concepto clave</span>
            <p>{guide.concept}</p>
          </div>
          <div className="guide-section guide-example">
            <span className="result-label">Ejemplo del material</span>
            <p>{guide.example}</p>
          </div>
          <ol className="guide-steps">
            {guide.steps.map((step, position) => (
              <li key={`${step.title}-${position}`}>
                <span className="guide-step-number">{position + 1}</span>
                <div>
                  <strong>{step.title}</strong>
                  <p>{step.detail}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="guide-footer">
            <button
              className="secondary-button"
              onClick={onVariation}
              disabled={variationLoading}
            >
              <SparkIcon size={16} />
              {variationLoading ? "Creando variación…" : "Probar una variación"}
            </button>
            {variationNotice && <span className="inline-success">{variationNotice}</span>}
          </div>
        </>
      )}
    </div>
  );
}
