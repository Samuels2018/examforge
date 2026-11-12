from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.config import Settings

logger = logging.getLogger(__name__)

Job = Callable[[], None]


class BackgroundQueue:
    """Cola in-process para tareas lentas.

    Es deliberadamente simple: la app es local-first y no queremos exigir Redis
    ni Celery. Los jobs abren su propia sesión y nunca comparten la del request.
    """

    def __init__(self, *, workers: int, name: str = "examforge") -> None:
        if workers < 1:
            raise ValueError("workers debe ser >= 1")
        self.workers = workers
        self.name = name
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._started = False
        self._lock = threading.Lock()

    @property
    def started(self) -> bool:
        return self._started

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            for index in range(self.workers):
                thread = threading.Thread(
                    target=self._run,
                    name=f"{self.name}-worker-{index + 1}",
                    daemon=True,
                )
                thread.start()
                self._threads.append(thread)
            logger.info("Cola de procesamiento arrancada con %s workers", self.workers)

    def submit(self, job: Job) -> None:
        if not self._started:
            raise RuntimeError("La cola de procesamiento no está arrancada")
        self._queue.put(job)

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._lock:
            if not self._started:
                return
            self._started = False
            for _ in self._threads:
                self._queue.put(None)
            threads, self._threads = self._threads, []
        for thread in threads:
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning("Worker %s no terminó en %.1fs", thread.name, timeout)
        logger.info("Cola de procesamiento detenida")

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                try:
                    job()
                except Exception:
                    logger.exception("Job en background falló")
            finally:
                self._queue.task_done()


def process_material_job(
    session_factory: Callable[[], Session],
    settings: Settings,
    material_id: str,
) -> None:
    """Job de extracción/chunking. Tolera que el material se haya borrado."""
    from app.models import Material
    from app.services.ingestion import MaterialService

    with session_factory() as session:
        material = session.get(Material, material_id)
        if material is None:
            logger.info("Material %s ya no existe; job omitido", material_id)
            return
        MaterialService(session, settings).process_material(material)
