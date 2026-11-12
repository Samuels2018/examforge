import { useState, type FormEvent } from "react";

import { formatDate, percent } from "../lib/format";
import type { AuthStatus, Health, WorkspaceSummary } from "../lib/types";
import { PlusIcon, TrashIcon } from "./Icons";

interface SidebarProps {
  workspaces: WorkspaceSummary[];
  selectedId: string | null;
  health: Health | null;
  loading: boolean;
  onSelect: (workspaceId: string) => void;
  onCreate: (payload: {
    name: string;
    description: string;
    exam_date: string | null;
  }) => Promise<void>;
  onDelete: (workspaceId: string) => Promise<void>;
  auth: AuthStatus | null;
  onOpenAuth: () => void;
  onLogout: () => Promise<void>;
}

function providerLabel(health: Health | null): string {
  if (!health) {
    return "Comprobando LLM…";
  }
  if (health.llm_mode === "offline") {
    return "Modo offline";
  }
  if (health.llm_mode === "ollama") {
    return health.model ? `Ollama · ${health.model}` : "Ollama";
  }
  return health.model ? `Auto · ${health.model}` : "Auto · Ollama / offline";
}

function providerClass(health: Health | null): string {
  if (!health) {
    return "neutral";
  }
  if (health.llm_mode === "offline") {
    return "offline";
  }
  if (health.llm_mode === "ollama") {
    return "online";
  }
  return "auto";
}

export function Sidebar({
  workspaces,
  selectedId,
  health,
  loading,
  onSelect,
  onCreate,
  onDelete,
  auth,
  onOpenAuth,
  onLogout,
}: SidebarProps) {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [examDate, setExamDate] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    if (!name.trim()) {
      setFormError("Ponle un nombre a la evaluación.");
      return;
    }
    setSubmitting(true);
    try {
      await onCreate({
        name: name.trim(),
        description: description.trim(),
        exam_date: examDate || null,
      });
      setName("");
      setDescription("");
      setExamDate("");
      setShowForm(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "No se pudo crear la evaluación");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(workspace: WorkspaceSummary) {
    const confirmed = window.confirm(
      `¿Eliminar «${workspace.name}» con todo su material y ejercicios?`,
    );
    if (confirmed) {
      await onDelete(workspace.id);
    }
  }

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">EF</div>
        <div className="brand-text">
          <strong>ExamForge</strong>
          <span>Material → ejercicios</span>
        </div>
      </div>

      <div className={`provider-badge ${providerClass(health)}`} title="Motor de generación activo">
        <span className="provider-dot" />
        <span>{providerLabel(health)}</span>
      </div>

      <div className="sidebar-heading">
        <span>Evaluaciones</span>
        <span className="count-pill">{workspaces.length}</span>
      </div>

      {!showForm && (
        <button className="new-workspace-button" onClick={() => setShowForm(true)}>
          <PlusIcon size={17} />
          Nueva evaluación
        </button>
      )}

      {showForm && (
        <form className="workspace-form" onSubmit={handleSubmit}>
          <label>
            Nombre
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ej.: Redes · parcial 2"
              autoFocus
              maxLength={200}
            />
          </label>
          <label>
            Fecha del examen
            <input
              type="date"
              value={examDate}
              onChange={(event) => setExamDate(event.target.value)}
            />
          </label>
          <label>
            Descripción
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Temas, profesor, apuntes…"
              rows={2}
              maxLength={2000}
            />
          </label>
          {formError && <p className="form-error">{formError}</p>}
          <div className="form-actions">
            <button type="submit" className="primary-button small" disabled={submitting}>
              {submitting ? "Creando…" : "Crear"}
            </button>
            <button
              type="button"
              className="ghost-button small"
              onClick={() => {
                setShowForm(false);
                setFormError(null);
              }}
              disabled={submitting}
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      <nav className="workspace-list" aria-label="Evaluaciones">
        {loading && <p className="sidebar-hint">Cargando…</p>}
        {!loading && workspaces.length === 0 && (
          <p className="sidebar-hint">
            Crea una evaluación por cada examen. Cada una guarda su material e historial.
          </p>
        )}
        {workspaces.map((workspace) => (
          <div
            key={workspace.id}
            className={`workspace-item ${workspace.id === selectedId ? "active" : ""}`}
          >
            <button
              className="workspace-select"
              onClick={() => onSelect(workspace.id)}
              aria-current={workspace.id === selectedId}
            >
              <span className="workspace-name">{workspace.name}</span>
              <span className="workspace-meta">
                {formatDate(workspace.exam_date)} · {workspace.exercise_count} ejercicios
              </span>
              <span className="workspace-meta subtle">
                {workspace.attempt_count > 0
                  ? `${percent(workspace.accuracy)} de acierto en ${workspace.attempt_count} intentos`
                  : "Sin intentos todavía"}
              </span>
            </button>
            <button
              className="icon-button workspace-delete"
              onClick={() => void handleDelete(workspace)}
              aria-label={`Eliminar evaluación ${workspace.name}`}
              title="Eliminar evaluación"
            >
              <TrashIcon />
            </button>
          </div>
        ))}
      </nav>

      <div className="sidebar-account">
        {auth?.authenticated && auth.user ? (
          <>
            <div className="account-identity">
              <span className="account-avatar" aria-hidden="true">
                {auth.user.display_name.slice(0, 1).toUpperCase()}
              </span>
              <div>
                <strong>{auth.user.display_name}</strong>
                <span>@{auth.user.username}</span>
              </div>
            </div>
            <button className="ghost-button small account-button" onClick={() => void onLogout()}>
              Cerrar sesión
            </button>
          </>
        ) : (
          <button className="ghost-button small account-button" onClick={onOpenAuth}>
            {auth?.auth_required ? "Iniciar sesión" : "Crear cuenta local"}
          </button>
        )}
      </div>

      <footer className="sidebar-footer">
        <span className="local-dot" />
        Local-first · tus apuntes se quedan en tu equipo
      </footer>
    </aside>
  );
}
