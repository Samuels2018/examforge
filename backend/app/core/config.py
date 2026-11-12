from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación, sobreescribible por variables EXAMFORGE_*."""

    model_config = SettingsConfigDict(
        env_prefix="EXAMFORGE_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ExamForge"
    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = "sqlite:///./data/examforge.db"
    upload_dir: Path = Path("./data/uploads")
    max_upload_mb: int = Field(default=25, ge=1, le=500)

    llm_provider: Literal["auto", "ollama", "offline"] = "auto"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_timeout_seconds: float = Field(default=120, gt=0)
    llm_max_context_chars: int = Field(default=12_000, ge=1_000, le=120_000)
    # Presupuesto de tokens de entrada para controlar coste/tiempo del LLM local.
    llm_max_prompt_tokens: int = Field(default=6_000, ge=100, le=64_000)

    embedding_provider: Literal["auto", "ollama", "offline"] = "auto"
    ollama_embedding_model: str = "nomic-embed-text"
    offline_embedding_dimensions: int = Field(default=384, ge=64, le=2_048)
    semantic_retrieval_enabled: bool = True
    semantic_candidate_chunks: int = Field(default=120, ge=8, le=500)
    semantic_context_chunks: int = Field(default=20, ge=1, le=100)
    semantic_mmr_lambda: float = Field(default=0.72, ge=0.0, le=1.0)

    exam_default_minutes: int = Field(default=30, ge=5, le=240)
    exam_max_questions: int = Field(default=20, ge=1, le=50)

    # Autenticación local. En modo false se usa un usuario local implícito para
    # conservar la experiencia "local-first"; si hay token, se respeta su usuario.
    auth_required: bool = False
    auth_token_days: int = Field(default=30, ge=1, le=365)
    auth_default_username: str = "__local__"
    auth_pbkdf2_iterations: int = Field(default=600_000, ge=100_000, le=2_000_000)

    # Importación de contenido externo.
    import_timeout_seconds: float = Field(default=30, gt=0, le=120)
    import_max_chars: int = Field(default=1_000_000, ge=10_000)
    import_allow_private_hosts: bool = False
    youtube_languages: list[str] = ["es", "en"]

    # OCR opcional (requiere tesseract + pytesseract instalados).
    ocr_enabled: bool = True
    ocr_language: str = "spa+eng"

    # Streaming SSE de generación.
    streaming_enabled: bool = True

    # Límites de subida y protección de la API.
    max_files_per_upload: int = Field(default=20, ge=1, le=100)
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=240, ge=1, le=100_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    rate_limit_exempt_paths: list[str] = ["/api/health"]

    # Auditoría local de operaciones de escritura.
    audit_enabled: bool = True
    audit_max_events: int = Field(default=5_000, ge=100, le=1_000_000)

    # Copias de seguridad de SQLite.
    backup_dir: Path = Path("./data/backups")
    backup_max_files: int = Field(default=20, ge=1, le=1_000)

    # Procesamiento de archivos grandes en segundo plano (in-process).
    background_processing_enabled: bool = True
    background_processing_threshold_mb: int = Field(default=2, ge=0, le=100)
    background_workers: int = Field(default=2, ge=1, le=8)
    background_shutdown_timeout_seconds: float = Field(default=5.0, gt=0, le=60)

    # Resumen de archivos tabulares: filas de muestra que se envían al LLM.
    tabular_sample_rows: int = Field(default=500, ge=20, le=5_000)

    # Cuotas por workspace (protegen la BD y el almacenamiento local).
    workspace_max_materials: int = Field(default=200, ge=1, le=10_000)
    workspace_max_storage_mb: int = Field(default=500, ge=1, le=100_000)
    workspace_max_exercises: int = Field(default=5_000, ge=1, le=100_000)

    # Caché en memoria de generaciones (resultados inmutables por prompt/contexto).
    generation_cache_entries: int = Field(default=64, ge=0, le=1_024)
    generation_cache_ttl_seconds: int = Field(default=900, ge=0, le=86_400)

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    chunk_max_chars: int = Field(default=1_200, ge=200, le=8_000)
    chunk_overlap_chars: int = Field(default=180, ge=0, le=2_000)
    max_extracted_chars: int = Field(default=2_000_000, ge=10_000)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def workspace_max_storage_bytes(self) -> int:
        return self.workspace_max_storage_mb * 1024 * 1024

    @property
    def background_processing_threshold_bytes(self) -> int:
        return self.background_processing_threshold_mb * 1024 * 1024
