from __future__ import annotations
"""Realtime object-region recognition backends."""

from multiwebcam.recognition.async_detector import AsyncObjectDetector
from multiwebcam.recognition.backends import create_detector
from multiwebcam.recognition.types import DetectionResult, InferenceStatus, ObjectDetector

__all__ = [
    "AsyncObjectDetector",
    "DetectionResult",
    "InferenceStatus",
    "ObjectDetector",
    "create_detector",
]
