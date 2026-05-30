from google import genai
from google.genai import types
from .base import BaseLLMClient, LLMResponse
from typing import Optional
import mimetypes

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

    def generate_with_file(self, path: str, prompt: str, system: Optional[str] = None) -> LLMResponse:
        full_prompt = prompt if not system else f"{system}\n\n{prompt}"
        mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"

        with open(path, "rb") as file:
            document = types.Part.from_bytes(data=file.read(), mime_type=mime_type)

        response = self.client.models.generate_content(
            model=self.model,
            contents=[document, full_prompt],
        )

        return LLMResponse(
            text=response.text,
            provider=self.provider,
            model=self.model,
        )
