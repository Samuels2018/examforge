# ExamForge — Fases del proyecto

> Aplicación web local-first para convertir el material de un examen en un plan de
> estudio con ejercicios interactivos, corrección razonada y refuerzo adaptativo.
>
> Stack: **Python + FastAPI + SQLAlchemy + Pydantic v2** · **React + Vite + TypeScript**
> · **Ollama** como LLM local (con modo offline de respaldo) · **SQLite** (Postgres opcional).

## Visión

1. Crear una **evaluación** (workspace) por cada examen o materia.
2. Subir todo el material (PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, Parquet).
3. Generar un banco de **ejercicios interactivos** de básico a difícil.
4. Responder, recibir **corrección + explicación del fallo**.
5. Consultar el **historial** por evaluación y un **plan de ataque** con los temas débiles.
6. Practicar con **ejercicios guiados** hasta dominar el tema.

## Decisiones de arquitectura

- **Monolito modular** con capas: `api → services → repositories → models`.
- **Python** por parsing de documentos, pandas/polars y Pydantic; **React + Vite** por ser
  ligero y rápido de iterar (sin la complejidad de SSR que no aporta aquí).
- **LLM detrás de una interfaz** (`LLMProvider`): Ollama, offline heurístico o fake en tests.
  La app nunca se queda sin funcionar si Ollama no está levantado (modo `auto`).
- **Salidas estructuradas** validadas con Pydantic; nunca se confía en el JSON del LLM.
- **Sin N+1**: listados con agregaciones y `JOIN`; nada de consultas dentro de bucles.
- **Local-first**: SQLite, archivos en disco y secretos por variables de entorno.

---

## Fase 0 — Fundaciones (incluida en Fase 1)

- [x] Estructura del repositorio, `.env.example`, `.gitignore`, Makefile.
- [x] README con instalación, uso, API, arquitectura y troubleshooting.
- [x] Material de ejemplo en `backend/samples/`.
- [x] Configuración tipada con `pydantic-settings`.
- [x] SQLAlchemy 2.0 + SQLite con foreign keys e índices.
- [x] Manejo de errores uniforme y logging de peticiones.
- [x] Docker Compose para Ollama.

## Fase 1 — Evaluaciones, material e historial ✅

**Objetivo:** poder crear evaluaciones independientes, subir su material y consultar el historial.

- [x] CRUD de workspaces (evaluaciones) con fecha de examen y descripción.
- [x] Subida múltiple de archivos con límite de tamaño y saneado de nombres.
- [x] Parsers: PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, JSON, Parquet.
- [x] Extracción de texto + chunking con solapamiento.
- [x] Persistencia del texto y de los chunks (con `material_id`/`workspace_id`).
- [x] Estados de material: `processing`, `ready`, `failed` con error visible.
- [x] Listados paginados y resumen por evaluación (sin N+1).
- [x] UI: sidebar de evaluaciones, pestañas Materiales / Ejercicios / Progreso.
- [x] Tests de ingesta, parsers, chunking, CRUD y conteo de queries.

## Fase 2 — Motor de ejercicios y feedback ✅

**Objetivo:** generar ejercicios desde el material, corregirlos y explicar los fallos.

- [x] `LLMProvider` con implementaciones Ollama, offline y auto-fallback.
- [x] Recuperación de contexto por foco léxico y límite de caracteres.
- [x] Generación de ejercicios con salida JSON validada con Pydantic.
- [x] Tipos: opción múltiple, verdadero/falso y respuesta corta.
- [x] Dificultades: básico, intermedio y avanzado.
- [x] Corrección determinista (opción múltiple/VF) y con LLM (respuesta corta).
- [x] Feedback con respuesta correcta + explicación del porqué.
- [x] Registro de intentos, historial por evaluación y métricas.
- [x] Plan de ataque determinista basado en temas y dificultades débiles.
- [x] UI: generador, runner de ejercicios, feedback y panel de progreso/plan.
- [x] Tests de generación, intentos, corrección, progreso y plan.

---

## Fase 3 — Aprendizaje adaptativo de verdad ✅

- [x] Índice de embeddings local (Ollama `nomic-embed-text`) + búsqueda semántica.
- [x] Reranking y selección de contexto por relevancia al foco (híbrido léxico + MMR).
- [x] Modelo de dominio por tema (mastery) con repetición espaciada (SM-2 simplificado).
- [x] Generación automática de ejercicios guiados para cada fallo (pistas progresivas).
- [x] Secuencias guiadas: explicación corta → ejemplo → ejercicio → variación.
- [x] Detección de errores conceptuales recurrentes y plan personalizado (determinista + datos de mastery).
- [x] Modo examen cronometrado y simulación por dificultad.

## Fase 4 — Producto y experiencia ✅

- [x] Autenticación local (usuario/contraseña) y aislamiento de datos.
- [x] Importación desde URL/YouTube (transcripción) y OCR de imágenes (opcional).
- [x] Exportación de plan y banco de ejercicios (PDF/Markdown/JSON).
- [x] Atajos de teclado, accesibilidad WCAG 2.2 (base) y modo móvil.
- [x] Streaming de respuestas del LLM y cancelación de generaciones.

## Fase 5 — Rendimiento y datos masivos ✅

- [x] Procesamiento en background (cola) para archivos grandes.
- [x] Polars para CSV/Parquet masivos y resúmenes por columnas.
- [x] Paginación/keyset en historial y límites por workspace.
- [x] Caché de generaciones y deduplicación de ejercicios.
- [x] Métricas de tokens/tiempo por generación y control de coste (local).

## Fase 6 — Calidad, seguridad y despliegue ✅

- [x] Contract tests del contrato API y tests E2E con Playwright.
- [x] Sanitización/aislamiento de prompt injection desde materiales.
- [x] Rate limiting, límites de subida por configuración y auditoría.
- [x] Docker Compose completo (app + Ollama) y healthchecks.
- [x] Backup/restore de SQLite y migraciones Alembic.
- [x] CI (ruff, mypy, pytest, build de frontend).

---

## Criterios de "hecho" por fase

- Tests unitarios e integración pasando.
- Endpoints probados con la app levantada (estado, validación, errores).
- Lint y typecheck sin errores.
- Sin N+1 demostrado con conteo de queries cuando aplique.
- Documentación de uso actualizada en `README.md`.

## Estado actual

- **Fase 1:** implementada y verificada.
- **Fase 2:** implementada y verificada.
- **Fase 3:** implementada y verificada.
- **Fase 4:** implementada y verificada.
- **Fase 5:** implementada y verificada.
- **Fase 6:** implementada y verificada (75 tests backend, ruff, mypy, typecheck, build,
  contrato OpenAPI, E2E Playwright, Alembic, backup/restore y Docker Compose).
- **Documentación:** README, `.env.example` y material de ejemplo disponibles.
- **Siguiente:** mejoras opcionales (cola persistente, OCR de PDFs, auditoría WCAG completa).
