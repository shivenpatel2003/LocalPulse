"""
Pytest Configuration and Shared Fixtures.

This module provides common fixtures for all tests:

- async_client: AsyncClient for API testing
- mock_neo4j: Mocked Neo4j client
- mock_pinecone: Mocked Pinecone client
- sample_business: Sample business entity
- sample_review: Sample review entity
"""

import pytest


@pytest.fixture
def sample_business() -> dict:
    """Return a sample business for testing."""
    return {
        "id": "test_business_123",
        "name": "Test Restaurant",
        "address": "123 Test Street",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "rating": 4.5,
        "review_count": 100,
    }


@pytest.fixture
def sample_review() -> dict:
    """Return a sample review for testing."""
    return {
        "id": "test_review_456",
        "business_id": "test_business_123",
        "text": "Great food and excellent service!",
        "rating": 5,
        "author": "Test User",
        "created_at": "2024-01-15T12:00:00Z",
    }
