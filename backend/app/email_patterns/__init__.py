"""Email pattern discovery engine."""

from app.email_patterns.generator import EmailPatternGenerator
from app.email_patterns.service import EmailPatternService
from app.email_patterns.types import EmailPattern, EmailPatternReport

__all__ = [
    "EmailPattern",
    "EmailPatternGenerator",
    "EmailPatternReport",
    "EmailPatternService",
]
