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