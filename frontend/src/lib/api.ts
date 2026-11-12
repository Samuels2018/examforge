import type {
  AttemptHistoryItem,
  AuthStatus,
  AuthToken,
  AttemptResult,
  Exam,
  ExamResult,
  ExamStartPayload,
  Exercise,
  GeneratePayload,
  GenerateResponse,
  GenerationMetrics,
  Guide,
  Health,
  Material,
  MaterialDetail,
  Page,
  Progress,
  StudyPlan,
  Workspace,
  WorkspaceSummary,
} from "./types";

const PREFIX = "/api";
const TOKEN_KEY = "examforge.auth_token";

let authToken: string | null =
  typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);

export function setAuthToken(token: string | null): void {
  authToken = token;
  if (typeof window === "undefined") {
    return;
  }
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export function getAuthToken(): string | null {
  return authToken;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  const headers = new Headers(init?.headers);
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  try {
    response = await fetch(`${PREFIX}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(
      "No se pudo conectar con el servidor. ¿Está levantado el backend?",
      "network_error",
      0,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const payload = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : null;

  if (!response.ok) {
    const error = payload?.error;
    throw new ApiError(
      error?.message ?? `Error ${response.status}`,
      error?.code ?? "http_error",
      response.status,
    );
  }
  return payload as T;
}

function jsonRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const api = {
  health: () => request<Health>("/health"),

  authStatus: async () => {
    try {
      return await request<AuthStatus>("/auth/status");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401 && authToken) {
        setAuthToken(null);
        return request<AuthStatus>("/auth/status");
      }
      throw cause;
    }
  },

  register: (payload: { username: string; password: string; display_name?: string }) =>
    jsonRequest<AuthToken>("POST", "/auth/register", payload),

  login: (payload: { username: string; password: string }) =>
    jsonRequest<AuthToken>("POST", "/auth/login", payload),

  logout: () => request<void>("/auth/logout", { method: "POST" }),

  listWorkspaces: () => request<WorkspaceSummary[]>("/workspaces"),

  createWorkspace: (payload: {
    name: string;
    description?: string;
    exam_date?: string | null;
  }) => jsonRequest<Workspace>("POST", "/workspaces", payload),

  deleteWorkspace: (workspaceId: string) =>
    request<void>(`/workspaces/${workspaceId}`, { method: "DELETE" }),

  listMaterials: (workspaceId: string) =>
    request<Page<Material>>(`/workspaces/${workspaceId}/materials?limit=100`),

  getMaterial: (workspaceId: string, materialId: string) =>
    request<MaterialDetail>(`/workspaces/${workspaceId}/materials/${materialId}`),

  uploadMaterials: (workspaceId: string, files: File[]) => {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }
    return request<Material[]>(`/workspaces/${workspaceId}/materials`, {
      method: "POST",
      body: form,
    });
  },

  deleteMaterial: (workspaceId: string, materialId: string) =>
    request<void>(`/workspaces/${workspaceId}/materials/${materialId}`, { method: "DELETE" }),

  importMaterialUrl: (workspaceId: string, url: string) =>
    jsonRequest<Material[]>("POST", `/workspaces/${workspaceId}/materials/import`, { url }),

  exportWorkspace: async (workspaceId: string, format: "markdown" | "json" | "pdf") => {
    const headers = new Headers();
    if (authToken) {
      headers.set("Authorization", `Bearer ${authToken}`);
    }
    const response = await fetch(
      `${PREFIX}/workspaces/${workspaceId}/export?format=${format}`,
      { headers },
    );
    if (!response.ok) {
      const contentType = response.headers.get("content-type") ?? "";
      const payload = contentType.includes("application/json")
        ? await response.json().catch(() => null)
        : null;
      throw new ApiError(
        payload?.error?.message ?? `Error ${response.status}`,
        payload?.error?.code ?? "http_error",
        response.status,
      );
    }
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") ?? "";
    const match = disposition.match(/filename="([^"]+)"/);
    return { blob, filename: match?.[1] ?? `evaluacion.${format}` };
  },

  generateExercises: (workspaceId: string, payload: GeneratePayload) =>
    jsonRequest<GenerateResponse>(
      "POST",
      `/workspaces/${workspaceId}/exercises/generate`,
      payload,
    ),

  generateExercisesStream: async (
    workspaceId: string,
    payload: GeneratePayload,
    handlers: {
      onStart?: (generationId: string) => void;
      onProgress?: (message: string, stage: string) => void;
    },
    signal?: AbortSignal,
  ): Promise<GenerateResponse> => {
    const headers = new Headers({ "Content-Type": "application/json" });
    if (authToken) {
      headers.set("Authorization", `Bearer ${authToken}`);
    }
    let response: Response;
    try {
      response = await fetch(
        `${PREFIX}/workspaces/${workspaceId}/exercises/generate/stream`,
        { method: "POST", headers, body: JSON.stringify(payload), signal },
      );
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") {
        throw cause;
      }
      throw new ApiError(
        "No se pudo conectar con el servidor. ¿Está levantado el backend?",
        "network_error",
        0,
      );
    }
    if (!response.ok) {
      const contentType = response.headers.get("content-type") ?? "";
      const errorPayload = contentType.includes("application/json")
        ? await response.json().catch(() => null)
        : null;
      throw new ApiError(
        errorPayload?.error?.message ?? `Error ${response.status}`,
        errorPayload?.error?.code ?? "http_error",
        response.status,
      );
    }
    const generationId = response.headers.get("x-generation-id");
    if (generationId) {
      handlers.onStart?.(generationId);
    }
    if (!response.body) {
      throw new ApiError("El servidor no devolvió un stream", "stream_error", 0);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: GenerateResponse | null = null;

    const consume = (block: string) => {
      const lines = block.split("\n");
      const eventName = lines.find((line) => line.startsWith("event: "))?.slice(7);
      const dataLine = lines.find((line) => line.startsWith("data: "))?.slice(6);
      if (!eventName || !dataLine) {
        return;
      }
      const data = JSON.parse(dataLine);
      if (eventName === "progress") {
        handlers.onProgress?.(data.message ?? "Generando…", data.stage ?? "generating");
      } else if (eventName === "result") {
        result = data as GenerateResponse;
      } else if (eventName === "error") {
        throw new ApiError(data.message ?? "Error generando ejercicios", data.code ?? "error", 0);
      } else if (eventName === "cancelled") {
        throw new DOMException(data.message ?? "Generación cancelada", "AbortError");
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        consume(block);
      }
    }
    if (buffer.trim()) {
      consume(buffer);
    }
    if (!result) {
      throw new ApiError("La generación terminó sin resultado", "stream_error", 0);
    }
    return result;
  },

  cancelGeneration: (workspaceId: string, generationId: string) =>
    request<void>(
      `/workspaces/${workspaceId}/exercises/generate/${generationId}/cancel`,
      { method: "POST" },
    ),

  listExercises: (workspaceId: string, limit = 100) =>
    request<Page<Exercise>>(`/workspaces/${workspaceId}/exercises?limit=${limit}`),

  getExercise: (workspaceId: string, exerciseId: string) =>
    request<Exercise>(`/workspaces/${workspaceId}/exercises/${exerciseId}`),

  submitAttempt: (
    workspaceId: string,
    exerciseId: string,
    payload: { answer: string; duration_seconds?: number },
  ) =>
    jsonRequest<AttemptResult>(
      `POST`,
      `/workspaces/${workspaceId}/exercises/${exerciseId}/attempts`,
      payload,
    ),

  listAttempts: (workspaceId: string) =>
    request<Page<AttemptHistoryItem>>(`/workspaces/${workspaceId}/attempts?limit=100`),

  getExerciseGuide: (workspaceId: string, exerciseId: string) =>
    request<Guide>(`/workspaces/${workspaceId}/exercises/${exerciseId}/guide`),

  generateVariation: (workspaceId: string, exerciseId: string) =>
    jsonRequest<GenerateResponse>(
      "POST",
      `/workspaces/${workspaceId}/exercises/${exerciseId}/variation`,
    ),

  getProgress: (workspaceId: string) =>
    request<Progress>(`/workspaces/${workspaceId}/progress`),

  getGenerationMetrics: (workspaceId: string) =>
    request<GenerationMetrics>(`/workspaces/${workspaceId}/generation-metrics`),

  getStudyPlan: (workspaceId: string) =>
    request<StudyPlan>(`/workspaces/${workspaceId}/study-plan`),

  startExam: (workspaceId: string, payload: ExamStartPayload) =>
    jsonRequest<Exam>("POST", `/workspaces/${workspaceId}/exams`, payload),

  getExam: (workspaceId: string, examId: string) =>
    request<Exam>(`/workspaces/${workspaceId}/exams/${examId}`),

  submitExam: (
    workspaceId: string,
    examId: string,
    payload: { answers: { item_id: string; answer: string }[]; duration_seconds?: number },
  ) =>
    jsonRequest<ExamResult>(
      "POST",
      `/workspaces/${workspaceId}/exams/${examId}/submit`,
      payload,
    ),
};
