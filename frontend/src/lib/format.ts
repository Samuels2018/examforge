import type { Difficulty, ExerciseKind, MaterialStatus } from "./types";

export function formatDate(value: string | null): string {
  if (!value) {
    return "Sin fecha";
  }
  const date = new Date(value.length <= 10 ? `${value}T12:00:00` : value);
  return new Intl.DateTimeFormat("es", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat("es", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export const difficultyLabels: Record<Difficulty, string> = {
  basic: "Básico",
  intermediate: "Intermedio",
  advanced: "Avanzado",
};

export const kindLabels: Record<ExerciseKind, string> = {
  multiple_choice: "Opción múltiple",
  true_false: "Verdadero / falso",
  short_answer: "Respuesta corta",
};

export const materialStatusLabels: Record<MaterialStatus, string> = {
  processing: "Procesando",
  ready: "Listo",
  failed: "Error",
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Ha ocurrido un error inesperado";
}
