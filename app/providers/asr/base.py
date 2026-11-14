from pathlib import Path
from typing import Protocol


class ASRProvider(Protocol):
    def transcribe(self, path: Path) -> str: ...
