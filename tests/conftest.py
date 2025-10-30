"""Pytest configuration and fixtures for DisTask tests."""

import pytest
import os
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
import sys
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture
def test_db_url():
    """Get test database URL from environment or use default."""
    return os.getenv("TEST_DATABASE_URL") or "postgresql://distask:distaskpass@localhost:5432/distask_test"


@pytest.fixture
def sample_guild_id():
    """Sample guild ID for testing."""
    return 123456789012345678


@pytest.fixture
def sample_user_id():
    """Sample user ID for testing."""
    return 987654321098765432

