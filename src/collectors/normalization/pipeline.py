"""Normalization pipeline for transforming collected data.

Provides transformer registration and execution for converting
platform-specific data to the unified CollectedContent schema.
"""

from typing import Callable

from src.collectors.normalization.schema import CollectedContent

Transformer = Callable[[dict], CollectedContent]


class NormalizationPipeline:
    """Pipeline for normalizing collected data from various sources.

    Registers transformers by source name and applies them to raw data
    to produce unified CollectedContent instances.
    """

    def __init__(self):
        """Initialize the normalization pipeline."""
        self._transformers: dict[str, Transformer] = {}

    def register_transformer(self, source: str, transformer: Transformer) -> None:
        """Register a transformer for a source.

        Args:
            source: Source identifier (e.g., "twitter", "instagram").
            transformer: Callable that transforms raw dict to CollectedContent.
        """
        self._transformers[source] = transformer

    def normalize(self, source: str, raw_data: dict) -> CollectedContent:
        """Normalize raw data to unified schema.

        Args:
            source: Source identifier for the data.
            raw_data: Raw data dictionary from the source.

        Returns:
            Normalized CollectedContent instance.

        Raises:
            ValueError: If no transformer is registered for the source.
        """
        if source not in self._transformers:
            raise ValueError(f"No transformer registered for source: {source}")
        return self._transformers[source](raw_data)

    def has_transformer(self, source: str) -> bool:
        """Check if a transformer is registered for a source.

        Args:
            source: Source identifier to check.

        Returns:
            True if a transformer is registered.
        """
        return source in self._transformers

    def list_sources(self) -> list[str]:
        """List all sources with registered transformers.

        Returns:
            List of source identifiers.
        """
        return list(self._transformers.keys())
