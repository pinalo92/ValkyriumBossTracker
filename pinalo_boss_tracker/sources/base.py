from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import BossObservation


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> list[BossObservation]:
        raise NotImplementedError
