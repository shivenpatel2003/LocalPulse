"""Integration test configuration with VCR.py for HTTP replay.

VCR records HTTP interactions to cassettes (YAML files) on first run,
then replays them on subsequent runs for deterministic tests.
"""

import os

import pytest
import vcr

# VCR configuration
VCR_CASSETTE_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "fixtures",
    "cassettes",
)

# Custom VCR instance with project-specific settings
my_vcr = vcr.VCR(
    cassette_library_dir=VCR_CASSETTE_DIR,
    record_mode="once",  # Record once, replay forever
    match_on=["uri", "method", "body"],
    filter_headers=[
        "authorization",
        "x-api-key",
        "api-key",
        "Authorization",
    ],
    filter_post_data_parameters=[
        "api_key",
        "key",
    ],
    decode_compressed_response=True,
    # Ignore localhost for database connections
    ignore_hosts=["localhost", "127.0.0.1"],
)


@pytest.fixture(scope="module")
def vcr_config():
    """VCR configuration for pytest-vcr."""
    return {
        "cassette_library_dir": VCR_CASSETTE_DIR,
        "record_mode": "once",
        "match_on": ["uri", "method"],
        "filter_headers": ["authorization", "x-api-key"],
    }


@pytest.fixture
def vcr_cassette(request):
    """Context manager for VCR cassette in tests."""
    cassette_name = f"{request.node.name}.yaml"
    with my_vcr.use_cassette(cassette_name):
        yield


@pytest.fixture
async def integration_container(mock_settings):
    """Container configured for integration tests with real connections mocked."""
    from unittest.mock import AsyncMock, MagicMock

    from src.core.container import DependencyContainer

    # Use real container but with mocked external services
    container = DependencyContainer(settings=mock_settings)

    # Mock the actual client creation
    container._neo4j = MagicMock()
    container._neo4j.connect = AsyncMock()
    container._neo4j.close = AsyncMock()
    container._neo4j.query = AsyncMock(return_value=[])

    container._pinecone = MagicMock()
    container._pinecone.connect = MagicMock()
    container._pinecone.ensure_index = MagicMock()
    container._pinecone.query = MagicMock(return_value=[])

    container._initialized = True

    yield container

    # Cleanup
    container._initialized = False
