"""Base collector interface for all data collectors.

All collectors should extend BaseCollector and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseCollector(ABC):
    """Abstract base class for all data collectors.

    Provides common interface for initialization and health checking.
    Concrete collectors should implement platform-specific collection methods.
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize collector with configuration.

        Args:
            config: Configuration dictionary with collector-specific settings.
        """
        self.config = config

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the collector is operational.

        Returns:
            True if the collector can connect and operate successfully.
        """
        ...
