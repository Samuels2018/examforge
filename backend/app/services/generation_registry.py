import threading
from dataclasses import dataclass
from uuid import uuid4


@dataclass
class GenerationHandle:
    id: str
    workspace_id: str
    cancel_event: threading.Event


class GenerationRegistry:
    """Registro en memoria de generaciones en curso para poder cancelarlas."""

    def __init__(self) -> None:
        self._handles: dict[str, GenerationHandle] = {}
        self._lock = threading.Lock()

    def create(self, workspace_id: str) -> GenerationHandle:
        handle = GenerationHandle(
            id=uuid4().hex,
            workspace_id=workspace_id,
            cancel_event=threading.Event(),
        )
        with self._lock:
            self._handles[handle.id] = handle
        return handle

    def cancel(self, workspace_id: str, generation_id: str) -> bool:
        with self._lock:
            handle = self._handles.get(generation_id)
        if handle is None or handle.workspace_id != workspace_id:
            return False
        handle.cancel_event.set()
        return True

    def finish(self, generation_id: str) -> None:
        with self._lock:
            self._handles.pop(generation_id, None)

    def active(self) -> int:
        with self._lock:
            return len(self._handles)
