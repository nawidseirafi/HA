from .gemini_client import GeminiLLMClient
from .openai_client import OpenAILLMClient
from .LlamaLLMClient import LlamaLLMClient
from dotenv import load_dotenv
import os
from typing import Any

from backend.config import load_global_config
from backend.paths import API_DIR

load_dotenv(API_DIR / ".env")

def create_llm_client(config: dict[str, Any] | None = None):
    if config is None:
        config = load_global_config()
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "")
    provider_config = llm_config.get(provider, {})
    api_key_name = provider_config.get("api_key")
    if api_key_name:
        api_key = os.getenv(str(api_key_name))
        if not api_key:
            raise RuntimeError(f"{api_key_name} ist nicht konfiguriert.")
    else:
        api_key = None
    model = provider_config.get("model")
    if provider == "gemini":
        return GeminiLLMClient(
            api_key=api_key,
            model=model,
        )
    if provider == "openai":
        return OpenAILLMClient(
            api_key=api_key,
            model=model,
        )
    if provider == "claude":
        return ClaudeLLMClient(
            api_key=api_key,
            model=model,
        )
    if provider == "llama":
        return LlamaLLMClient(
            base_url=provider_config["base_url"],
            model=model,
        )
    raise ValueError(f"Unbekannter LLM Provider: {provider}")
