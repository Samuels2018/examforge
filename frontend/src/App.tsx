import { useCallback, useEffect, useState } from "react";

import { AuthPanel } from "./components/AuthPanel";
import { ExamTab } from "./components/ExamTab";
import { ExercisesTab } from "./components/ExercisesTab";
import { BookIcon, ChartIcon, TargetIcon, TimerIcon } from "./components/Icons";
import { MaterialsTab } from "./components/MaterialsTab";
import { ProgressTab } from "./components/ProgressTab";
import { ShortcutsDialog } from "./components/ShortcutsDialog";
import { Sidebar } from "./components/Sidebar";
import { api, setAuthToken } from "./lib/api";
import { errorMessage, formatDate, percent } from "./lib/format";
import type {
  AuthStatus,
  AuthToken,
  Health,
  PlanStep,
  Tab,
  WorkspaceSummary,
} from "./lib/types";

type ToastKind = "success" | "error";

interface ToastState {
  kind: ToastKind;
  message: string;
}

export default function App() {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("materials");
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const refreshWorkspaces = useCallback(async () => {
    const list = await api.listWorkspaces();
    setWorkspaces(list);
    setSelectedId((current) =>
      current && list.some((workspace) => workspace.id === current)
        ? current
        : (list[0]?.id ?? null),
    );
    return list;
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([api.authStatus(), api.health()])
      .then(async ([status, providerHealth]) => {
        if (!alive) {
          return;
        }
        setAuth(status);
        setHealth(providerHealth);
        if (!status.authenticated) {
          setAuthToken(null);
        }
        if (status.auth_required && !status.authenticated) {
          setWorkspaces([]);
          setSelectedId(null);
          setError(null);
          return;
        }
        const list = await api.listWorkspaces();
        if (!alive) {
          return;
        }
        setWorkspaces(list);
        setSelectedId(list[0]?.id ?? null);
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
  }, []);

  const selected = workspaces.find((workspace) => workspace.id === selectedId) ?? null;

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "SELECT" ||
        target?.isContentEditable;
      if (typing) {
        return;
      }
      if (event.key === "?") {
        event.preventDefault();
        setShortcutsOpen((current) => !current);
        return;
      }
      if (event.altKey && ["1", "2", "3", "4"].includes(event.key) && selected) {
        event.preventDefault();
        const next: Tab[] = ["materials", "exercises", "exam", "progress"];
        setTab(next[Number(event.key) - 1]);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [selected]);

  useEffect(() => {
    if (!toast) {
      return;
    }
    const timeout = window.setTimeout(() => setToast(null), 6000);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  const handleWorkspaceChanged = useCallback(() => {
    void refreshWorkspaces().catch((cause) => {
      setToast({ kind: "error", message: errorMessage(cause) });
    });
  }, [refreshWorkspaces]);

  async function handleCreate(payload: {
    name: string;
    description: string;
    exam_date: string | null;
  }) {
    const created = await api.createWorkspace(payload);
    await refreshWorkspaces();
    setSelectedId(created.id);
    setTab("materials");
    setToast({ kind: "success", message: `Evaluación «${created.name}» creada.` });
  }

  async function handleDelete(workspaceId: string) {
    try {
      await api.deleteWorkspace(workspaceId);
      await refreshWorkspaces();
      setToast({ kind: "success", message: "Evaluación eliminada." });
    } catch (cause) {
      setToast({ kind: "error", message: errorMessage(cause) });
    }
  }

  async function handleAuthenticated(session: AuthToken) {
    const status = await api.authStatus().catch(() => null);
    setAuth(
      status ?? {
        auth_required: auth?.auth_required ?? false,
        authenticated: true,
        user: session.user,
        has_users: true,
      },
    );
    await refreshWorkspaces();
    setToast({
      kind: "success",
      message: `Sesión iniciada como ${session.user.display_name}.`,
    });
  }

  async function handleLogout() {
    try {
      await api.logout();
    } catch {
      // El token local se limpia igualmente aunque el servidor ya no lo conozca.
    } finally {
      setAuthToken(null);
      const status = await api.authStatus();
      setAuth(status);
      if (status.auth_required) {
        setWorkspaces([]);
        setSelectedId(null);
        setTab("materials");
      } else {
        await refreshWorkspaces();
      }
      setToast({ kind: "success", message: "Sesión cerrada." });
    }
  }

  async function handleExport(format: "markdown" | "json" | "pdf") {
    if (!selected) {
      return;
    }
    try {
      const { blob, filename } = await api.exportWorkspace(selected.id, format);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setToast({ kind: "success", message: `Exportación ${format.toUpperCase()} descargada.` });
    } catch (cause) {
      setToast({ kind: "error", message: errorMessage(cause) });
    }
  }

  async function handlePractice(step: PlanStep) {
    if (!selected) {
      return;
    }
    const response = await api.generateExercises(selected.id, {
      count: step.suggested_count,
      difficulties: [step.suggested_difficulty],
      focus: step.focus_topic,
    });
    await refreshWorkspaces();
    setTab("exercises");
    setToast({
      kind: "success",
      message: `${response.created} ejercicios de refuerzo creados${
        step.focus_topic ? ` para «${step.focus_topic}»` : ""
      }.`,
    });
  }

  const tabs: { id: Tab; label: string; icon: React.ReactNode; count: number }[] = selected
    ? [
        {
          id: "materials",
          label: "Materiales",
          icon: <BookIcon size={17} />,
          count: selected.material_count,
        },
        {
          id: "exercises",
          label: "Ejercicios",
          icon: <TargetIcon size={17} />,
          count: selected.exercise_count,
        },
        {
          id: "exam",
          label: "Examen",
          icon: <TimerIcon size={17} />,
          count: selected.exercise_count,
        },
        {
          id: "progress",
          label: "Progreso",
          icon: <ChartIcon size={17} />,
          count: selected.attempt_count,
        },
      ]
    : [];

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Saltar al contenido
      </a>
      <Sidebar
        workspaces={workspaces}
        selectedId={selectedId}
        health={health}
        loading={loading}
        onSelect={(workspaceId) => setSelectedId(workspaceId)}
        onCreate={handleCreate}
        onDelete={handleDelete}
        auth={auth}
        onOpenAuth={() => setAuthOpen(true)}
        onLogout={handleLogout}
      />

      <main id="main-content" className="main" tabIndex={-1}>
        {loading && (
          <div className="loading-state">
            <div className="spinner" />
            <p>Cargando tu espacio de estudio…</p>
          </div>
        )}

        {!loading && error && workspaces.length === 0 && (
          <div className="welcome">
            <span className="welcome-kicker">Servidor no disponible</span>
            <h1>No se pudo cargar ExamForge</h1>
            <p>{error}</p>
            <p className="muted">
              Arranca el backend con <code>make backend</code> y recarga esta página.
            </p>
          </div>
        )}

        {!loading && auth?.auth_required && !auth.authenticated && (
          <div className="welcome auth-gate">
            <span className="welcome-kicker">Cuenta requerida</span>
            <h1>Inicia sesión para ver tus evaluaciones</h1>
            <p className="welcome-lead">
              Cada cuenta mantiene su material, ejercicios e historial separados del resto.
            </p>
            <button className="primary-button" onClick={() => setAuthOpen(true)}>
              Iniciar sesión o crear cuenta
            </button>
          </div>
        )}

        {!loading && !error && !selected && !(auth?.auth_required && !auth.authenticated) && (
          <div className="welcome">
            <span className="welcome-kicker">Empieza en 3 pasos</span>
            <h1>Convierte tus apuntes en práctica real</h1>
            <p className="welcome-lead">
              Crea una evaluación por examen, sube su material y genera ejercicios con corrección
              razonada. El plan de ataque se adapta a tus fallos.
            </p>
            <div className="welcome-steps">
              <div className="welcome-step">
                <span>01</span>
                <h3>Crea la evaluación</h3>
                <p>Una pestaña independiente para cada examen, con su historial.</p>
              </div>
              <div className="welcome-step">
                <span>02</span>
                <h3>Sube el material</h3>
                <p>PDF, DOCX, PPTX, apuntes o tablas. Se extrae y trocea el texto.</p>
              </div>
              <div className="welcome-step">
                <span>03</span>
                <h3>Practica y corrige</h3>
                <p>De básico a avanzado, con explicación del fallo y plan de refuerzo.</p>
              </div>
            </div>
            <p className="muted">Usa «Nueva evaluación» en la barra lateral para empezar.</p>
          </div>
        )}

        {selected && (
          <>
            <header className="workspace-header">
              <div className="workspace-title">
                <span className="eyebrow">Evaluación</span>
                <h1>{selected.name}</h1>
                <div className="workspace-subline">
                  <span>
                    {selected.exam_date
                      ? `Examen: ${formatDate(selected.exam_date)}`
                      : "Sin fecha de examen"}
                  </span>
                  {selected.description && (
                    <>
                      <span className="subline-divider" />
                      <span className="workspace-description">{selected.description}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="workspace-actions">
                <div className="export-actions" role="group" aria-label="Exportar evaluación">
                  {(["markdown", "json", "pdf"] as const).map((format) => (
                    <button
                      key={format}
                      className="ghost-button small"
                      onClick={() => void handleExport(format)}
                      aria-label={`Exportar evaluación en ${format}`}
                    >
                      {format === "markdown" ? "MD" : format.toUpperCase()}
                    </button>
                  ))}
                </div>
                <div className="header-stat">
                  <strong>{selected.attempt_count > 0 ? percent(selected.accuracy) : "—"}</strong>
                  <span>precisión</span>
                </div>
              </div>
            </header>

            <nav className="tabs" aria-label="Secciones de la evaluación" role="tablist">
              {tabs.map((item, position) => (
                <button
                  key={item.id}
                  id={`tab-${item.id}`}
                  role="tab"
                  aria-selected={tab === item.id}
                  aria-controls={`panel-${item.id}`}
                  tabIndex={tab === item.id ? 0 : -1}
                  className={`tab-button ${tab === item.id ? "active" : ""}`}
                  onClick={() => setTab(item.id)}
                  onKeyDown={(event) => {
                    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") {
                      return;
                    }
                    event.preventDefault();
                    const delta = event.key === "ArrowRight" ? 1 : -1;
                    const next = tabs[(position + delta + tabs.length) % tabs.length];
                    setTab(next.id);
                    document.getElementById(`tab-${next.id}`)?.focus();
                  }}
                >
                  {item.icon}
                  <span>{item.label}</span>
                  <span className="tab-count">{item.count}</span>
                </button>
              ))}
            </nav>

            <div
              className="tab-content"
              role="tabpanel"
              id={`panel-${tab}`}
              aria-labelledby={`tab-${tab}`}
            >
              {tab === "materials" && (
                <MaterialsTab workspace={selected} onChanged={handleWorkspaceChanged} />
              )}
              {tab === "exercises" && (
                <ExercisesTab workspace={selected} onChanged={handleWorkspaceChanged} />
              )}
              {tab === "exam" && (
                <ExamTab workspace={selected} onChanged={handleWorkspaceChanged} />
              )}
              {tab === "progress" && (
                <ProgressTab workspace={selected} onPractice={handlePractice} />
              )}
            </div>
          </>
        )}
      </main>

      {toast && (
        <div className={`toast ${toast.kind}`} role="status" aria-live="polite">
          <span className="toast-dot" />
          {toast.message}
        </div>
      )}

      <AuthPanel
        open={authOpen || Boolean(auth?.auth_required && !auth.authenticated && !loading)}
        authRequired={Boolean(auth?.auth_required)}
        hasUsers={Boolean(auth?.has_users)}
        onClose={() => {
          if (!auth?.auth_required) {
            setAuthOpen(false);
          }
        }}
        onAuthenticated={(session) => void handleAuthenticated(session)}
      />
      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
