from llm.gemini_client import GeminiLLMClient
from llm.openai_client import OpenAILLMClient
from llm.LlamaLLMClient import LlamaLLMClient
from pathlib import Path
from dotenv import load_dotenv
import os


BASE_DIR = Path(__file__).resolve().parent.parent
print("BASE_DIR:", BASE_DIR)
load_dotenv(BASE_DIR / ".env")

def create_llm_client(config):
    llm_config = config["llm"]

    provider = llm_config["provider"]
    if provider == "gemini":
        return GeminiLLMClient(
            api_key=os.getenv(llm_config["gemini"]["api_key"]),
            model=llm_config["gemini"]["model"],
        )

    if provider == "openai":
        return OpenAILLMClient(
            api_key=os.getenv(llm_config["openai"]["api_key"]),
            model=llm_config["openai"]["model"],
        )
    
    if provider == "claude":
        return OpenAILLMClient(
            api_key=os.getenv(llm_config["claude"]["api_key"]),
            model=llm_config["claude"]["model"],
        )


    if provider == "llama":
        return LlamaLLMClient(
            base_url=llm_config["llama"]["base_url"],
            model=llm_config["llama"]["model"],
        )

    raise ValueError(f"Unbekannter LLM Provider: {provider}")