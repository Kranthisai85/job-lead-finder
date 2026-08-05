"""Hiring and opportunity detection."""

from app.hiring_detection.service import HiringDetectionService
from app.hiring_detection.types import HiringDetectionReport, HiringOpportunity

__all__ = [
    "HiringDetectionReport",
    "HiringDetectionService",
    "HiringOpportunity",
]
