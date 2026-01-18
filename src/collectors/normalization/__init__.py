"""Normalization infrastructure for collected data.

Provides unified schema and transformation pipeline for normalizing
platform-specific data to a common format.
"""

from src.collectors.normalization.schema import CollectedContent, ContentType
from src.collectors.normalization.pipeline import NormalizationPipeline

__all__ = [
    "CollectedContent",
    "ContentType",
    "NormalizationPipeline",
]
