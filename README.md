# ExamForge

Aplicación web **local-first** para convertir el material de un examen en un banco de
ejercicios interactivos, corrección razonada y un plan de ataque personalizado.

Cada **evaluación** es un workspace independiente con su propio material, banco de
ejercicios, historial y progreso. Todo se guarda en tu equipo: SQLite + archivos locales.

## Funcionalidad

- Crear una evaluación por examen o materia.
- Subir PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, JSON, Parquet e imágenes (OCR opcional).
- Importar contenido desde una URL o la transcripción de un vídeo de YouTube.
- Extraer texto, trocearlo con solapamiento y usarlo como contexto.
- Generar ejercicios de dificultad básica, intermedia y avanzada:
  - opción múltiple,
  - verdadero/falso,
  - respuesta corta.
- Corregir con feedback, respuesta correcta y explicación.
- Consultar precisión, temas débiles, historial y plan de ataque.
- Generar lotes de refuerzo desde el plan.
- Generar en streaming con progreso visible y cancelación.
- Exportar la evaluación a Markdown, JSON o PDF.
- Cuentas locales opcionales con aislamiento de datos por usuario.
- Funcionar **sin Ollama** gracias al generador offline de respaldo.
- Aislar el material frente a *prompt injection* y limitar el rate de la API.
- Auditar las operaciones de escritura y hacer backup/restore de SQLite.
- Migrar el esquema con Alembic y desplegar con Docker Compose (app + Ollama).

## Stack

| Capa | Tecnología |
| --- | --- |
| Backend | Python 3.13 · FastAPI · SQLAlchemy 2 · Pydantic v2 · SQLite |
| Frontend | React 19 · Vite 6 · TypeScript |
| LLM | Ollama local (`qwen2.5:7b` por defecto) u offline heurístico |
| Parsing | pypdf · python-docx · python-pptx · pandas · polars · OCR opcional |
| Tests | pytest · TestClient |

## Requisitos

- Python **3.13+** y [uv](https://docs.astral.sh/uv/).
- Node.js **20+** y npm.
- Opcional: [Ollama](https://ollama.com/) para generación y corrección con LLM.

## Puesta en marcha

Guía paso a paso: [`LEVANTAR.md`](LEVANTAR.md).

```bash
make install
cp .env.example .env
```

### 1. Backend

```bash
make backend
# http://localhost:8000/docs
```

La primera ejecución crea `backend/data/` y la base de datos SQLite.

### 2. Frontend

En otra terminal:

```bash
make frontend
# http://localhost:5173
```

Vite hace proxy de `/api` hacia `http://localhost:8000`.

### 3. Ollama (opcional)

```bash
ollama pull qwen2.5:7b
ollama serve
```

Si Ollama no está disponible, `EXAMFORGE_LLM_PROVIDER=auto` cae automáticamente al
generador offline. Para forzar un modo concreto:

```dotenv
EXAMFORGE_LLM_PROVIDER=auto     # Ollama si está disponible, si no offline
EXAMFORGE_LLM_PROVIDER=ollama   # exige Ollama
EXAMFORGE_LLM_PROVIDER=offline  # sin LLM
```

También puedes levantar Ollama con Docker:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b
```

### 4. Todo con Docker Compose

El compose completo levanta Ollama, la API y el frontend con Nginx y healthchecks:

```bash
make docker-up          # o: docker compose up --build -d
docker compose exec ollama ollama pull qwen2.5:7b
# App: http://localhost:5173 · API: http://localhost:8000/docs
```

Los datos persisten en el volumen `examforge_data` (`/data`): SQLite, subidas y backups.

## Configuración

Todas las variables usan el prefijo `EXAMFORGE_`. Consulta `.env.example` para la lista
completa. Las más relevantes:

| Variable | Por defecto | Descripción |
| --- | --- | --- |
| `EXAMFORGE_DATABASE_URL` | `sqlite:///./data/examforge.db` | Base de datos |
| `EXAMFORGE_UPLOAD_DIR` | `./data/uploads` | Archivos subidos |
| `EXAMFORGE_MAX_UPLOAD_MB` | `25` | Tamaño máximo por archivo |
| `EXAMFORGE_LLM_PROVIDER` | `auto` | `auto`, `ollama` u `offline` |
| `EXAMFORGE_OLLAMA_MODEL` | `qwen2.5:7b` | Modelo de Ollama |
| `EXAMFORGE_LLM_MAX_CONTEXT_CHARS` | `12000` | Contexto máximo enviado al LLM |
| `EXAMFORGE_LLM_MAX_PROMPT_TOKENS` | `6000` | Presupuesto de tokens de entrada |
| `EXAMFORGE_BACKGROUND_PROCESSING_ENABLED` | `true` | Procesar archivos grandes en segundo plano |
| `EXAMFORGE_BACKGROUND_PROCESSING_THRESHOLD_MB` | `2` | Umbral para usar la cola (0 = siempre) |
| `EXAMFORGE_BACKGROUND_WORKERS` | `2` | Workers de la cola in-process |
| `EXAMFORGE_TABULAR_SAMPLE_ROWS` | `500` | Filas de muestra de CSV/Parquet |
| `EXAMFORGE_WORKSPACE_MAX_MATERIALS` | `200` | Cuota de materiales por evaluación |
| `EXAMFORGE_WORKSPACE_MAX_STORAGE_MB` | `500` | Cuota de almacenamiento por evaluación |
| `EXAMFORGE_WORKSPACE_MAX_EXERCISES` | `5000` | Cuota de ejercicios por evaluación |
| `EXAMFORGE_MAX_FILES_PER_UPLOAD` | `20` | Archivos máximos por petición de subida |
| `EXAMFORGE_RATE_LIMIT_ENABLED` | `true` | Activar rate limiting de la API |
| `EXAMFORGE_RATE_LIMIT_REQUESTS` | `240` | Peticiones por ventana y clave |
| `EXAMFORGE_RATE_LIMIT_WINDOW_SECONDS` | `60` | Tamaño de la ventana deslizante |
| `EXAMFORGE_AUDIT_ENABLED` | `true` | Registrar escrituras en `audit_logs` |
| `EXAMFORGE_AUDIT_MAX_EVENTS` | `5000` | Eventos de auditoría conservados |
| `EXAMFORGE_BACKUP_DIR` | `./data/backups` | Directorio de copias de SQLite |
| `EXAMFORGE_BACKUP_MAX_FILES` | `20` | Copias conservadas (rota las antiguas) |
| `EXAMFORGE_GENERATION_CACHE_ENTRIES` | `64` | Entradas de caché de generaciones |
| `EXAMFORGE_GENERATION_CACHE_TTL_SECONDS` | `900` | TTL de la caché de generaciones |
| `EXAMFORGE_AUTH_REQUIRED` | `false` | Exigir cuenta para acceder a la API |
| `EXAMFORGE_AUTH_TOKEN_DAYS` | `30` | Duración de los tokens de sesión |
| `EXAMFORGE_IMPORT_TIMEOUT_SECONDS` | `30` | Timeout al importar una URL |
| `EXAMFORGE_IMPORT_ALLOW_PRIVATE_HOSTS` | `false` | Permitir URLs a redes privadas (solo pruebas) |
| `EXAMFORGE_OCR_ENABLED` | `true` | Activar OCR de imágenes |
| `EXAMFORGE_OCR_LANGUAGE` | `spa+eng` | Idiomas de Tesseract |
| `EXAMFORGE_STREAMING_ENABLED` | `true` | Activar generación SSE |

Las rutas relativas se resuelven desde `backend/` cuando se usa `make backend`.

## Uso

1. Crea una evaluación en la barra lateral.
2. Sube uno o varios archivos del temario, pega una URL o importa un vídeo de YouTube.
3. Ve a **Ejercicios** y genera un lote indicando cantidad, dificultades y foco.
4. Responde: la corrección muestra el fallo y su explicación.
5. Revisa **Progreso** para ver precisión, temas débiles y el plan de ataque.
6. Pulsa **Generar refuerzo** en un paso del plan para practicar ese tema.
7. Exporta la evaluación a Markdown, JSON o PDF desde la cabecera.

### Cuentas locales

Por defecto la app funciona sin registro con un perfil local implícito. Si quieres separar
datos por usuario, activa `EXAMFORGE_AUTH_REQUIRED=true` o crea una cuenta desde la barra
lateral. Al registrarte, los workspaces anónimos existentes pasan a tu cuenta.

### OCR opcional

El OCR de imágenes requiere el binario `tesseract` y las dependencias de Python
`pytesseract` y `Pillow`. Si no están instaladas, la subida devuelve un material en estado
`failed` con un mensaje claro, sin afectar al resto de formatos.

Hay un material de ejemplo en `backend/samples/ejemplo_material.txt`.

## Seguridad y mantenimiento

- **Prompt injection**: el material y las respuestas del alumno se neutralizan
  (`app/services/prompt_safety.py`) y se envían al LLM dentro de un bloque
  `<material_no_fiable>`; el sistema ignora cualquier orden incluida ahí.
- **Rate limiting**: ventana deslizante en memoria por token o IP. Devuelve `429` con
  `Retry-After` y el mismo sobre de error `{"error": {...}}`.
- **Auditoría**: cada `POST/PUT/PATCH/DELETE` bajo `/api` se guarda en `audit_logs`
  (usuario, ruta, estado, duración, IP y `request_id`). Consulta con `GET /api/audit`.
- **Límites**: `EXAMFORGE_MAX_FILES_PER_UPLOAD`, `EXAMFORGE_MAX_UPLOAD_MB` y las cuotas
  por workspace se validan antes de escribir en disco.

### Copias de seguridad

```bash
make backup                       # crea data/backups/examforge-<timestamp>.db
make backups                      # lista las copias
make restore FILE=examforge-....db
```

También están disponibles por API (`/api/maintenance/*`). Si restauras con la API
levantada, reiníciala después para descartar conexiones abiertas.

### Migraciones

El esquema se crea al arrancar, pero el proyecto incluye Alembic para evolucionarlo:

```bash
make migrate                                         # alembic upgrade head
cd backend && uv run alembic revision --autogenerate -m "cambio"  # nueva migración
```

## API

Base: `http://localhost:8000/api`

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/health` | Estado y proveedor LLM activo |
| `GET` | `/auth/status` | Estado de autenticación y usuario actual |
| `POST` | `/auth/register` | Crear cuenta local |
| `POST` | `/auth/login` | Iniciar sesión |
| `POST` | `/auth/logout` | Cerrar sesión |
| `GET` | `/auth/me` | Usuario autenticado |
| `GET` | `/audit` | Eventos de auditoría del usuario (paginado) |
| `GET/POST` | `/workspaces` | Listar / crear evaluaciones |
| `GET/PATCH/DELETE` | `/workspaces/{id}` | Detalle / editar / borrar |
| `GET/POST` | `/workspaces/{id}/materials` | Listar / subir material |
| `POST` | `/workspaces/{id}/materials/import` | Importar desde URL/YouTube |
| `GET/DELETE` | `/workspaces/{id}/materials/{material_id}` | Detalle / borrar |
| `POST` | `/workspaces/{id}/exercises/generate` | Generar ejercicios |
| `POST` | `/workspaces/{id}/exercises/generate/stream` | Generar con SSE |
| `POST` | `/workspaces/{id}/exercises/generate/{generation_id}/cancel` | Cancelar generación |
| `GET` | `/workspaces/{id}/exercises` | Listar banco (paginado) |
| `GET` | `/workspaces/{id}/exercises/{exercise_id}` | Detalle sin respuesta |
| `GET` | `/workspaces/{id}/exercises/{exercise_id}/guide` | Guía progresiva del ejercicio |
| `POST` | `/workspaces/{id}/exercises/{exercise_id}/attempts` | Responder |
| `GET` | `/workspaces/{id}/attempts` | Historial (paginado) |
| `GET` | `/workspaces/{id}/progress` | Métricas por dificultad y tema |
| `GET` | `/workspaces/{id}/study-plan` | Plan de ataque |
| `GET` | `/workspaces/{id}/mastery` | Dominio y repaso espaciado por tema |
| `GET` | `/workspaces/{id}/diagnostics` | Patrones de error recurrentes |
| `GET` | `/workspaces/{id}/generation-metrics` | Tokens, latencia y caché |
| `POST` | `/workspaces/{id}/exams` | Iniciar examen cronometrado |
| `GET` | `/workspaces/{id}/exams/{exam_id}` | Estado del examen |
| `POST` | `/workspaces/{id}/exams/{exam_id}/submit` | Entregar examen |
| `GET` | `/workspaces/{id}/export?format=markdown|json|pdf` | Exportar evaluación |
| `GET` | `/maintenance/backups` | Listar copias de seguridad |
| `POST` | `/maintenance/backup` | Crear copia de seguridad |
| `POST` | `/maintenance/restore` | Restaurar una copia (SQLite) |

Ejemplo con cuenta local:

```bash
BASE=http://localhost:8000/api
TOKEN=$(curl -s -X POST "$BASE/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"secreto123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

WS=$(curl -s -X POST "$BASE/workspaces" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Bases de datos"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')

curl -X POST "$BASE/workspaces/$WS/materials" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@backend/samples/ejemplo_material.txt;type=text/plain"

curl -N -X POST "$BASE/workspaces/$WS/exercises/generate/stream" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"count":8,"difficulties":["basic","intermediate","advanced"]}'

curl -o evaluacion.pdf "$BASE/workspaces/$WS/export?format=pdf" \
  -H "Authorization: Bearer $TOKEN"
```

La documentación interactiva está en `http://localhost:8000/docs`.

## Tests y calidad

```bash
make test       # pytest (integración, contrato, seguridad, backup, rendimiento)
make test-e2e   # Playwright (requiere: npx playwright install chromium)
make lint       # ruff + mypy + tsc --noEmit
make build      # build de producción del frontend
```

Estado verificado: **75 tests backend**, ruff y mypy limpios, typecheck y build de Vite
correctos. Los tests de rendimiento cuentan queries para evitar N+1. Los tests de contrato
fijan el contrato OpenAPI (`tests/test_contract.py`) y los E2E cubren el flujo completo en
navegador.

La Fase 6 añade aislamiento de prompt injection, rate limiting, auditoría, backup/restore,
Alembic, Docker Compose y CI (`.github/workflows/ci.yml`).

## Arquitectura

```text
backend/
  app/
    api/          Routers, dependencias, manejo de errores
    core/         Configuración, base de datos, logging
    models/       SQLAlchemy: User, Workspace, Material, Exercise, Attempt…
    repositories/ Consultas y agregaciones (sin N+1)
    schemas/      Contratos Pydantic
    services/     Casos de uso: auth, ingesta, importación, generación, exportación
      background.py  Cola in-process para archivos grandes
      backup.py      Copias y restauración de SQLite
      prompt_safety.py  Aislamiento de material no fiable
      rate_limit.py  Ventana deslizante en memoria
      audit.py       Registro de operaciones de escritura
      llm/        Ollama, offline, auto y base
      parsing/    Extractores, OCR y chunking
  migrations/     Alembic (línea base 0001)
  samples/        Material de ejemplo
  tests/          Integración, unidad, contrato, seguridad y rendimiento

frontend/
  src/
    components/   Sidebar, materiales, ejercicios, runner, progreso
    lib/          Cliente API, tipos y formateo
  e2e/            Pruebas Playwright

docker-compose.yml  Ollama + API + frontend con healthchecks
.github/workflows/ci.yml  ruff · mypy · pytest · build · E2E
```

Flujo de dependencias: `api → services → repositories → models`. El LLM queda detrás de
`LLMProvider`, por lo que se puede sustituir sin tocar la lógica de negocio.

## Decisiones clave

- **Monolito modular**: suficiente para una app local, sin coste operativo de microservicios.
- **Salidas estructuradas**: todo ejercicio del LLM se valida con Pydantic antes de persistir.
- **Modo offline**: la demo y los tests no dependen de red ni de Ollama.
- **Corrección determinista** para opción múltiple y verdadero/falso; el LLM solo corrige
  respuestas cortas, con fallback heurístico.
- **Sin N+1**: listados con `JOIN`/agregaciones y tests que cuentan queries.
- **Aislamiento por usuario**: cada workspace tiene `owner_id` y las consultas se filtran
  por la sesión autenticada.
- **Importación segura**: solo http/https, timeout, límite de tamaño y bloqueo de hosts
  privados/locales por defecto (protección SSRF).
- **Material no fiable**: el contenido del usuario nunca se interpola como instrucción; se
  sanea y se delimita para que el LLM lo trate solo como datos.
- **Defensa en profundidad**: límites de subida, cuotas, rate limiting, auditoría y backups
  locales; todo configurable y activo por defecto.
- **Migraciones reversibles**: Alembic como fuente de verdad del esquema, con creación
  idempotente para bases ya existentes.

## Limitaciones actuales

- La generación en streaming usa un hilo por petición; no hay cola persistente todavía.
- El OCR de PDFs escaneados no está incluido: solo imágenes. Para PDFs escaneados hay que
  convertirlos a imagen o añadir un renderizador.
- La cancelación es cooperativa: si el LLM ya está respondiendo, el trabajo termina en
  segundo plano pero no se persiste.
- Rate limiting y auditoría viven en memoria/SQLite del proceso: no hay coordinación entre
  réplicas (el despliegue objetivo es una sola instancia local).
- El restore de SQLite exige reiniciar la API si está levantada; no hay failover.
- El generador offline es heurístico y produce ejercicios más simples que Ollama.
- La accesibilidad cubre base WCAG 2.2 (foco, teclado, ARIA, contraste y movimiento
  reducido), pendiente de auditoría completa.

## Próximos pasos

Las seis fases de `PHASES.md` están completas. Mejoras opcionales: cola persistente para
streaming, OCR de PDFs escaneados, auditoría completa de accesibilidad y soporte multiusuario
remoto con rate limiting distribuido.

## Troubleshooting

- **`No se pudo conectar con el servidor`**: el backend no está en el puerto 8000.
- **`502` al generar con Ollama**: comprueba `ollama serve` y el modelo descargado, o usa
  `EXAMFORGE_LLM_PROVIDER=offline`.
- **PDF sin texto**: puede ser escaneado; convierte sus páginas a imagen y súbelas para OCR.
- **OCR no disponible**: instala `tesseract`, `pytesseract` y `Pillow`, o desactiva
  `EXAMFORGE_OCR_ENABLED`.
- **Importación bloqueada**: por defecto no se permiten hosts privados; usa una URL pública
  o activa `EXAMFORGE_IMPORT_ALLOW_PRIVATE_HOSTS` solo en pruebas.
- **Datos de prueba**: se guardan en `backend/data/`; puedes borrar esa carpeta para empezar
  de cero con la app parada.
