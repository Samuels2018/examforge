import { useEffect, useRef } from "react";

interface ShortcutsDialogProps {
  open: boolean;
  onClose: () => void;
}

const SHORTCUTS = [
  { keys: ["?"], label: "Abrir esta ayuda" },
  { keys: ["Alt", "1"], label: "Ir a Materiales" },
  { keys: ["Alt", "2"], label: "Ir a Ejercicios" },
  { keys: ["Alt", "3"], label: "Ir a Examen" },
  { keys: ["Alt", "4"], label: "Ir a Progreso" },
  { keys: ["Esc"], label: "Cerrar diálogos" },
];

export function ShortcutsDialog({ open, onClose }: ShortcutsDialogProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    closeRef.current?.focus();
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

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        className="shortcuts-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
      >
        <div className="auth-head">
          <div>
            <span className="eyebrow">Productividad</span>
            <h2 id="shortcuts-title">Atajos de teclado</h2>
          </div>
          <button ref={closeRef} className="icon-button" onClick={onClose} aria-label="Cerrar">
            ×
          </button>
        </div>
        <dl className="shortcut-list">
          {SHORTCUTS.map((shortcut) => (
            <div key={shortcut.label} className="shortcut-row">
              <dt>{shortcut.label}</dt>
              <dd>
                {shortcut.keys.map((key) => (
                  <kbd key={key}>{key}</kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
        <p className="muted">Los atajos no se activan mientras escribes en un campo de texto.</p>
      </section>
    </div>
  );
}
