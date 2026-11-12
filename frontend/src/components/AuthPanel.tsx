import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, setAuthToken } from "../lib/api";
import { errorMessage } from "../lib/format";
import type { AuthToken } from "../lib/types";

interface AuthPanelProps {
  open: boolean;
  authRequired: boolean;
  hasUsers: boolean;
  onClose: () => void;
  onAuthenticated: (session: AuthToken) => void;
}

type Mode = "login" | "register";

export function AuthPanel({
  open,
  authRequired,
  hasUsers,
  onClose,
  onAuthenticated,
}: AuthPanelProps) {
  const [mode, setMode] = useState<Mode>(hasUsers ? "login" : "register");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const usernameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
    setMode(hasUsers ? "login" : "register");
    window.setTimeout(() => usernameRef.current?.focus(), 0);
  }, [open, hasUsers]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const session =
        mode === "login"
          ? await api.login({ username: username.trim(), password })
          : await api.register({
              username: username.trim(),
              password,
              display_name: displayName.trim() || undefined,
            });
      setAuthToken(session.access_token);
      onAuthenticated(session);
      setPassword("");
      onClose();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section
        className="auth-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
        aria-describedby="auth-description"
      >
        <div className="auth-head">
          <div>
            <span className="eyebrow">Cuenta local</span>
            <h2 id="auth-title">{mode === "login" ? "Inicia sesión" : "Crea tu cuenta"}</h2>
          </div>
          {!authRequired && (
            <button className="icon-button" onClick={onClose} aria-label="Cerrar">
              ×
            </button>
          )}
        </div>
        <p id="auth-description" className="muted">
          {authRequired
            ? "Este servidor exige una cuenta para separar tus evaluaciones del resto de usuarios."
            : "Opcional: crea una cuenta para proteger tus datos. Sin cuenta seguirás usando el perfil local."}
        </p>

        <div className="auth-tabs" role="group" aria-label="Acceso o registro">
          <button
            type="button"
            aria-pressed={mode === "login"}
            className={`auth-tab ${mode === "login" ? "active" : ""}`}
            onClick={() => {
              setMode("login");
              setError(null);
            }}
          >
            Entrar
          </button>
          <button
            type="button"
            aria-pressed={mode === "register"}
            className={`auth-tab ${mode === "register" ? "active" : ""}`}
            onClick={() => {
              setMode("register");
              setError(null);
            }}
          >
            Registrarme
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Usuario
            <input
              ref={usernameRef}
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              minLength={3}
              maxLength={80}
              required
            />
          </label>
          {mode === "register" && (
            <label>
              Nombre visible (opcional)
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                autoComplete="name"
                maxLength={120}
              />
            </label>
          )}
          <label>
            Contraseña
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={mode === "register" ? 8 : 1}
              maxLength={200}
              required
            />
          </label>
          {error && <div className="alert danger">{error}</div>}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting
              ? "Comprobando…"
              : mode === "login"
                ? "Entrar"
                : "Crear cuenta"}
          </button>
        </form>
        {!authRequired && (
          <button className="ghost-button small auth-later" onClick={onClose}>
            Seguir sin cuenta
          </button>
        )}
      </section>
    </div>
  );
}
