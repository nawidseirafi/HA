import base64
import mimetypes
from pathlib import Path
from typing import Optional

from openai import OpenAI
from .base import BaseLLMClient, LLMResponse

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

    def generate_with_file(self, path: str, prompt: str, system: Optional[str] = None) -> LLMResponse:
        document_path = Path(path)
        mime_type = mimetypes.guess_type(document_path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(document_path.read_bytes()).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"

        if mime_type.startswith("image/"):
            file_part = {
                "type": "input_image",
                "image_url": data_url,
                "detail": "high",
            }
        else:
            file_part = {
                "type": "input_file",
                "filename": document_path.name,
                "file_data": data_url,
                "detail": "high",
            }

        response = self.client.responses.create(
            model=self.model,
            instructions=system,
            input=[
                {
                    "role": "user",
                    "content": [
                        file_part,
                        {
                            "type": "input_text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        return LLMResponse(
            text=response.output_text,
            provider=self.provider,
            model=self.model,
        )
