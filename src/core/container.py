"""
Dependency Injection Container for LocalPulse.

Provides centralized management of service dependencies with lazy initialization
and proper lifecycle management. Replaces service locator pattern.

Usage:
    # At application startup
    container = DependencyContainer()
    await container.initialize()

    # Pass to components that need dependencies
    research_agent = ResearchAgent(container)

    # At shutdown
    await container.shutdown()
"""

from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

from src.config.settings import Settings, get_settings
from src.core.exceptions import InitializationError

if TYPE_CHECKING:
    from src.knowledge.neo4j_client import Neo4jClient
    from src.knowledge.pinecone_client import PineconeClient
    from src.knowledge.cohere_embeddings import CohereEmbeddingsService

logger = structlog.get_logger(__name__)


class DependencyContainer:
    """
    Central container for all service dependencies.

    Provides lazy initialization of services with proper error handling.
    Services are initialized on first access and cached.

    Example:
        container = DependencyContainer()
        await container.initialize()  # Initialize core services

        # Access services (lazy init if not done in initialize())
        neo4j = container.neo4j
        pinecone = container.pinecone

        # Cleanup
        await container.shutdown()
    """

    def __init__(self, settings: Settings | None = None):
        """
        Initialize the container.

        Args:
            settings: Application settings. Defaults to get_settings().
        """
        self._settings = settings or get_settings()
        self._neo4j: Neo4jClient | None = None
        self._pinecone: PineconeClient | None = None
        self._embeddings: CohereEmbeddingsService | None = None
        self._initialized = False

        logger.info("dependency_container_created")

    @property
    def settings(self) -> Settings:
        """Get application settings."""
        return self._settings

    @property
    def neo4j(self) -> "Neo4jClient":
        """
        Get Neo4j client (lazy initialization).

        Raises:
            InitializationError: If Neo4j client cannot be created.
            RuntimeError: If accessed before initialization.
        """
        if self._neo4j is None:
            try:
                from src.knowledge.neo4j_client import Neo4jClient

                self._neo4j = Neo4jClient(
                    uri=self._settings.neo4j_uri,
                    user=self._settings.neo4j_user,
                    password=self._settings.neo4j_password.get_secret_value(),
                )
                logger.info("neo4j_client_created")
            except Exception as e:
                logger.error("neo4j_client_creation_failed", error=str(e))
                raise InitializationError(
                    "Neo4jClient",
                    f"Failed to create Neo4j client: {e}",
                    {"uri": self._settings.neo4j_uri},
                )
        return self._neo4j

    @property
    def pinecone(self) -> "PineconeClient":
        """
        Get Pinecone client (lazy initialization).

        Raises:
            InitializationError: If Pinecone client cannot be created.
        """
        if self._pinecone is None:
            try:
                from src.knowledge.pinecone_client import PineconeClient

                self._pinecone = PineconeClient(
                    api_key=self._settings.pinecone_api_key.get_secret_value(),
                    index_name=self._settings.pinecone_index_name,
                )
                logger.info("pinecone_client_created")
            except Exception as e:
                logger.error("pinecone_client_creation_failed", error=str(e))
                raise InitializationError(
                    "PineconeClient",
                    f"Failed to create Pinecone client: {e}",
                    {"index": self._settings.pinecone_index_name},
                )
        return self._pinecone

    @property
    def embeddings(self) -> "CohereEmbeddingsService":
        """
        Get embeddings service (lazy initialization).

        Raises:
            InitializationError: If embeddings service cannot be created.
        """
        if self._embeddings is None:
            try:
                from src.knowledge.cohere_embeddings import CohereEmbeddingsService

                self._embeddings = CohereEmbeddingsService(
                    api_key=self._settings.cohere_api_key.get_secret_value(),
                )
                logger.info("embeddings_service_created")
            except Exception as e:
                logger.error("embeddings_service_creation_failed", error=str(e))
                raise InitializationError(
                    "CohereEmbeddingsService",
                    f"Failed to create embeddings service: {e}",
                )
        return self._embeddings

    async def initialize(self) -> None:
        """
        Initialize all core services.

        This connects to databases and verifies connectivity.
        Call this at application startup.

        Raises:
            InitializationError: If any core service fails to initialize.
        """
        if self._initialized:
            logger.warning("container_already_initialized")
            return

        logger.info("container_initializing")

        try:
            # Initialize Neo4j
            await self.neo4j.connect()
            logger.info("neo4j_connected")

            # Initialize Pinecone
            self.pinecone.connect()
            self.pinecone.ensure_index()
            logger.info("pinecone_connected")

            # Embeddings service doesn't need explicit init

            self._initialized = True
            logger.info("container_initialized")

        except InitializationError:
            # Re-raise our own errors
            raise
        except Exception as e:
            logger.error(
                "container_initialization_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            raise InitializationError(
                "DependencyContainer",
                f"Failed to initialize dependencies: {e}",
            )

    async def shutdown(self) -> None:
        """
        Shutdown all services gracefully.

        Call this at application shutdown.
        """
        logger.info("container_shutting_down")

        # Close Neo4j
        if self._neo4j is not None:
            try:
                await self._neo4j.close()
                logger.info("neo4j_closed")
            except Exception as e:
                logger.error("neo4j_close_error", error=str(e))

        # Pinecone doesn't need explicit close

        self._initialized = False
        logger.info("container_shutdown_complete")

    @property
    def is_initialized(self) -> bool:
        """Check if container has been initialized."""
        return self._initialized


# Global container instance for convenience
# Prefer passing container explicitly via dependency injection
_container: DependencyContainer | None = None


def get_container() -> DependencyContainer:
    """
    Get the global container instance.

    Creates one if it doesn't exist. Prefer passing container
    explicitly for better testability.

    Returns:
        Global DependencyContainer instance.
    """
    global _container
    if _container is None:
        _container = DependencyContainer()
    return _container


async def initialize_container() -> DependencyContainer:
    """
    Initialize and return the global container.

    Convenience function for application startup.
    """
    container = get_container()
    await container.initialize()
    return container


async def shutdown_container() -> None:
    """
    Shutdown the global container.

    Convenience function for application shutdown.
    """
    global _container
    if _container is not None:
        await _container.shutdown()
        _container = None
