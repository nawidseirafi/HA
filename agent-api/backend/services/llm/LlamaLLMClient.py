import requests

from .base import BaseLLMClient, LLMResponse


class LlamaLLMClient(BaseLLMClient):
    def __init__(self, base_url: str, model: str):
        self.provider = "llama"
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, system=None) -> LLMResponse:
        full_prompt = prompt if not system else f"{system}\n\n{prompt}"

        response = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
            },
            timeout=120,
        )

        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            text=data.get("response", ""),
            provider=self.provider,
            model=self.model,
        )