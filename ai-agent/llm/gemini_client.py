from google import genai
from llm.base import BaseLLMClient, LLMResponse
from typing import Optional

class GeminiLLMClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str):
        self.provider = "gemini"
        self.model = model
        self.client = genai.Client(api_key=api_key)

    def generate(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        full_prompt = prompt if not system else f"{system}\n\n{prompt}"

        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
        )

        return LLMResponse(
            text=response.text,
            provider=self.provider,
            model=self.model,
        )