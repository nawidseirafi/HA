from openai import OpenAI
from llm.base import BaseLLMClient, LLMResponse
from typing import Optional

class OpenAILLMClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str):
        self.provider = "openai"
        self.model = model
        self.client = OpenAI(api_key=api_key)

    def generate(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        response = self.client.responses.create(
            model=self.model,
            instructions=system,
            input=prompt,
        )

        return LLMResponse(
            text=response.output_text,
            provider=self.provider,
            model=self.model,
        )