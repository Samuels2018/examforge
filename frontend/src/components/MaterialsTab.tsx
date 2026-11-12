import { useEffect, useState, type DragEvent, type ChangeEvent } from "react";

import { api } from "../lib/api";
import { errorMessage, formatBytes, materialStatusLabels } from "../lib/format";
import type { Material, WorkspaceSummary } from "../lib/types";
import { BookIcon, TrashIcon, UploadIcon } from "./Icons";

interface MaterialsTabProps {
  workspace: WorkspaceSummary;
  onChanged: () => void;
}

export function MaterialsTab({ workspace, onChanged }: MaterialsTabProps) {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    const hasProcessing = materials.some((material) => material.status === "processing");
    if (!hasProcessing) {
      return;
    }
    const timer = window.setInterval(() => {
      setReloadToken((token) => token + 1);
    }, 1_500);
    return () => window.clearInterval(timer);
  }, [materials]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .listMaterials(workspace.id)
      .then((page) => {
        if (!alive) {
          return;
        }
        setMaterials(page.items);
        setTotal(page.total);
        setError(null);
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
  }, [workspace.id, reloadToken]);

  function reload() {
    setReloadToken((token) => token + 1);
  }

  async function handleFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (files.length === 0) {
      return;
    }
    setUploading(true);
    setError(null);
    setNotice(null);
    try {
      const uploaded = await api.uploadMaterials(workspace.id, files);
      const failed = uploaded.filter((item) => item.status === "failed");
      const pending = uploaded.filter((item) => item.status === "processing");
      if (failed.length > 0) {
        setNotice(
          `${failed.length} archivo(s) no se pudieron procesar. Revisa el detalle en la lista.`,
        );
      } else if (pending.length > 0) {
        setNotice(
          `${uploaded.length} archivo(s) subidos. ${pending.length} en proceso; la lista se actualizará sola.`,
        );
      } else {
        setNotice(
          `${uploaded.length} archivo(s) procesados y listos para generar ejercicios.`,
        );
      }
      reload();
      onChanged();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setUploading(false);
    }
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) {
      void handleFiles(event.target.files);
    }
    event.target.value = "";
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 0) {
      void handleFiles(event.dataTransfer.files);
    }
  }

  async function handleImport(event: React.FormEvent) {
    event.preventDefault();
    const url = importUrl.trim();
    if (!url) {
      setError("Pega una URL http(s) o un enlace de YouTube.");
      return;
    }
    setImporting(true);
    setError(null);
    setNotice(null);
    try {
      const imported = await api.importMaterialUrl(workspace.id, url);
      const failed = imported.filter((item) => item.status === "failed");
      setNotice(
        failed.length > 0
          ? `${failed.length} importación(es) no se pudieron procesar.`
          : `${imported.length} contenido(s) importados desde la URL.`,
      );
      setImportUrl("");
      reload();
      onChanged();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setImporting(false);
    }
  }

  async function handleDelete(material: Material) {
    if (!window.confirm(`¿Eliminar «${material.filename}»?`)) {
      return;
    }
    setError(null);
    try {
      await api.deleteMaterial(workspace.id, material.id);
      reload();
      onChanged();
    } catch (cause) {
      setError(errorMessage(cause));
    }
  }

  return (
    <section className="panel-stack">
      <div className="section-heading">
        <div>
          <h2>Material del examen</h2>
          <p>
            Sube apuntes, diapositivas, PDFs o tablas. El texto se extrae y se trocea para
            generar ejercicios y citar el contexto.
          </p>
        </div>
        <div className="heading-stat">
          <strong>{total}</strong>
          <span>archivos</span>
        </div>
      </div>

      {error && <div className="alert danger">{error}</div>}
      {notice && <div className="alert info">{notice}</div>}

      <form className="import-card" onSubmit={handleImport}>
        <div>
          <h3>Importar desde URL o YouTube</h3>
          <p>Descarga el texto de una página o la transcripción de un vídeo con subtítulos.</p>
        </div>
        <div className="import-row">
          <label className="sr-only" htmlFor="import-url">
            URL para importar
          </label>
          <input
            id="import-url"
            type="url"
            value={importUrl}
            onChange={(event) => setImportUrl(event.target.value)}
            placeholder="https://ejemplo.com/apuntes o https://youtu.be/…"
            disabled={importing}
            required
          />
          <button className="secondary-button" type="submit" disabled={importing}>
            {importing ? "Importando…" : "Importar"}
          </button>
        </div>
      </form>

      <label
        className={`dropzone ${dragging ? "dragging" : ""} ${uploading ? "busy" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          multiple
          onChange={handleInputChange}
          disabled={uploading}
          accept=".pdf,.docx,.pptx,.txt,.md,.markdown,.csv,.xlsx,.xlsm,.json,.parquet,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp"
        />
        <span className="dropzone-icon">
          <UploadIcon />
        </span>
        <strong>{uploading ? "Procesando archivos…" : "Arrastra archivos o haz clic para elegir"}</strong>
        <span className="dropzone-hint">
          PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, JSON, Parquet e imágenes con OCR · máx. 25 MB
        </span>
      </label>

      {loading && <p className="muted">Cargando material…</p>}

      {!loading && materials.length === 0 && (
        <div className="empty-card">
          <BookIcon size={28} />
          <h3>Todavía no hay material</h3>
          <p>Sube el contenido del examen y podrás generar ejercicios desde la siguiente pestaña.</p>
        </div>
      )}

      {materials.length > 0 && (
        <div className="material-list">
          {materials.map((material) => (
            <article key={material.id} className="material-row">
              <div className="material-icon">
                <BookIcon size={20} />
              </div>
              <div className="material-main">
                <div className="material-title-line">
                  <strong>{material.filename}</strong>
                  <span className={`status-badge status-${material.status}`}>
                    {materialStatusLabels[material.status]}
                  </span>
                </div>
                <div className="material-meta">
                  <span>{formatBytes(material.size_bytes)}</span>
                  <span>{material.char_count.toLocaleString("es")} caracteres</span>
                  <span>{material.chunk_count} fragmentos</span>
                </div>
                {material.error_message && (
                  <p className="material-error">{material.error_message}</p>
                )}
              </div>
              <button
                className="icon-button"
                onClick={() => void handleDelete(material)}
                aria-label={`Eliminar ${material.filename}`}
                title="Eliminar material"
              >
                <TrashIcon />
              </button>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
