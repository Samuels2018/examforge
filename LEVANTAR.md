# Cómo levantar ExamForge

Guía rápida para arrancar el proyecto en local o con Docker.

## Requisitos

- Python **3.13+** y [`uv`](https://docs.astral.sh/uv/)
- Node.js **20+** y npm
- Opcional: [Ollama](https://ollama.com/) para generación/corrección con LLM
- Opcional: Docker + Docker Compose

## Opción A — Local (desarrollo)

### 1. Instalar dependencias

Desde la raíz del proyecto:

```bash
make install
cp .env.example .env
```

### 2. Arrancar el backend

En una terminal:

```bash
make backend
```

- API: http://localhost:8000
- Documentación: http://localhost:8000/docs
- Healthcheck: http://localhost:8000/api/health

La primera ejecución crea `backend/data/` y la base SQLite.

### 3. Arrancar el frontend

En otra terminal:

```bash
make frontend
```

- App: http://localhost:5173

Vite hace proxy de `/api` hacia el backend en el puerto 8000.

### 4. Ollama (opcional)

Si Ollama está instalado:

```bash
ollama pull qwen2.5:7b
ollama serve
```

Con `EXAMFORGE_LLM_PROVIDER=auto` (valor por defecto) se usa Ollama si está disponible y,
si no, el generador offline. Para forzar un modo:

```dotenv
EXAMFORGE_LLM_PROVIDER=auto     # Ollama si está disponible, si no offline
EXAMFORGE_LLM_PROVIDER=ollama   # exige Ollama
EXAMFORGE_LLM_PROVIDER=offline  # sin LLM
```

También puedes levantar solo Ollama con Docker:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b
```

## Opción B — Todo con Docker Compose

```bash
make docker-up
# o: docker compose up --build -d
```

Luego descarga el modelo (solo la primera vez):

```bash
docker compose exec ollama ollama pull qwen2.5:7b
```

- App: http://localhost:5173
- API: http://localhost:8000/docs

Los datos persisten en el volumen `examforge_data` (SQLite, subidas y backups).
Para parar:

```bash
make docker-down
```

## Verificar que funciona

```bash
curl http://localhost:8000/api/health
```

Abre http://localhost:5173, crea una evaluación, sube `backend/samples/ejemplo_material.txt`
y genera ejercicios. Por defecto no hace falta crear cuenta (`EXAMFORGE_AUTH_REQUIRED=false`).

## Comandos útiles

```bash
make test       # tests backend (pytest)
make test-e2e   # E2E con Playwright (antes: cd frontend && npx playwright install chromium)
make lint       # ruff + mypy + typecheck
make build      # build de producción del frontend
make migrate    # aplica migraciones Alembic
make backup     # crea una copia de SQLite
make backups    # lista las copias
make restore FILE=examforge-....db
```

## Problemas habituales

- **El frontend no conecta**: comprueba que el backend está en el puerto 8000.
- **`502` al generar con Ollama**: ejecuta `ollama serve` y descarga el modelo, o usa
  `EXAMFORGE_LLM_PROVIDER=offline`.
- **PDF sin texto**: puede ser escaneado; súbelo como imagen para OCR o activa OCR.
- **OCR no disponible**: instala `tesseract`, `pytesseract` y `Pillow`, o desactiva
  `EXAMFORGE_OCR_ENABLED`.
- **Resetear datos**: con la app parada, borra `backend/data/` (local) o
  `docker compose down -v` (Docker, elimina también el volumen).
