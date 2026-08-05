"""Local LLM email generation via Ollama."""

from app.ai.client import OllamaClient, OllamaModelNotFoundError
from app.ai.generator import AIEmailGenerator
from app.ai.service import AIEmailService
from app.ai.types import GeneratedEmail, OllamaGenerateResponse

__all__ = [
    "AIEmailGenerator",
    "AIEmailService",
    "GeneratedEmail",
    "OllamaClient",
    "OllamaGenerateResponse",
    "OllamaModelNotFoundError",
]
