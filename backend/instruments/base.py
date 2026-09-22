from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Tuple


class InstrumentValidator(ABC):
    name = "GENERIC"

    @abstractmethod
    def matches(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def validate(self, path: Path, metadata: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError
