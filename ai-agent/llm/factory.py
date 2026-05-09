from llm.gemini_client import GeminiLLMClient
from llm.openai_client import OpenAILLMClient


def create_llm_client(config):
    llm_config = config["llm"]

    provider = llm_config["provider"]

    if provider == "gemini":
        return GeminiLLMClient(
            api_key=llm_config["gemini"]["api_key"],
            model=llm_config["gemini"]["model"],
        )

    if provider == "openai":
        return OpenAILLMClient(
            api_key=llm_config["openai"]["api_key"],
            model=llm_config["openai"]["model"],
        )

    raise ValueError(f"Unbekannter LLM Provider: {provider}")