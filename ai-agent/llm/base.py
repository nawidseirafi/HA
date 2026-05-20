from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        pass

    def generate_with_file(self, path: str, prompt: str, system: Optional[str] = None) -> LLMResponse:
        raise NotImplementedError(f"{self.__class__.__name__} unterstuetzt keine Datei-Analyse.")
