"""Unit tests for hot-reload configuration."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config.hot_reload import (
    ConfigWatcher,
    get_config_watcher,
    start_config_watcher,
    stop_config_watcher,
)


class TestConfigWatcher:
    """Test ConfigWatcher functionality."""

    @pytest.fixture
    def temp_env_file(self):
        """Create a temporary .env file for testing."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".env",
            delete=False,
        ) as f:
            f.write("TEST_VAR=initial\n")
            f.flush()
            yield Path(f.name)
        # Cleanup
        Path(f.name).unlink(missing_ok=True)

    @pytest.fixture
    def watcher(self, temp_env_file):
        """Create a ConfigWatcher for testing."""
        return ConfigWatcher(watch_paths=[temp_env_file])

    def test_watcher_initializes_with_paths(self, watcher, temp_env_file):
        """Watcher initializes with provided paths."""
        assert temp_env_file in watcher.watch_paths

    def test_add_callback(self, watcher):
        """Callbacks can be added."""
        callback = MagicMock()
        watcher.add_callback(callback)

        assert callback in watcher.callbacks

    def test_remove_callback(self, watcher):
        """Callbacks can be removed."""
        callback = MagicMock()
        watcher.add_callback(callback)
        watcher.remove_callback(callback)

        assert callback not in watcher.callbacks

    @pytest.mark.asyncio
    async def test_watcher_starts_and_stops(self, watcher):
        """Watcher can start and stop."""
        await watcher.start()
        assert watcher.is_running

        await watcher.stop()
        assert not watcher.is_running

    @pytest.mark.asyncio
    async def test_watcher_only_starts_once(self, watcher):
        """Starting twice doesn't create multiple tasks."""
        await watcher.start()
        task1 = watcher._task

        await watcher.start()  # Second start
        task2 = watcher._task

        assert task1 is task2

        await watcher.stop()

    @pytest.mark.asyncio
    async def test_reload_clears_settings_cache(self, watcher):
        """Reload clears the settings cache."""
        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.app_env = "development"
            mock_settings.debug = True
            mock_get.return_value = mock_settings

            result = await watcher._reload_settings()

            assert result is True
            mock_get.cache_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_calls_callbacks(self, watcher):
        """Reload triggers all registered callbacks."""
        callback1 = MagicMock()
        callback2 = MagicMock()
        watcher.add_callback(callback1)
        watcher.add_callback(callback2)

        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.app_env = "development"
            mock_settings.debug = True
            mock_get.return_value = mock_settings

            await watcher._reload_settings()

            callback1.assert_called_once()
            callback2.assert_called_once()

    @pytest.mark.asyncio
    async def test_reload_handles_invalid_config(self, watcher):
        """Reload handles invalid config gracefully."""
        with patch("src.config.settings.get_settings") as mock_get:
            mock_get.cache_clear = MagicMock()
            mock_get.side_effect = ValueError("Invalid config")

            result = await watcher._reload_settings()

            assert result is False

    @pytest.mark.asyncio
    async def test_reload_continues_on_callback_error(self, watcher):
        """Reload continues if a callback raises."""
        callback1 = MagicMock(side_effect=Exception("Callback error"))
        callback2 = MagicMock()
        watcher.add_callback(callback1)
        watcher.add_callback(callback2)

        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.app_env = "development"
            mock_settings.debug = True
            mock_get.return_value = mock_settings

            result = await watcher._reload_settings()

            # Should still succeed and call both callbacks
            assert result is True
            callback1.assert_called_once()
            callback2.assert_called_once()


class TestGlobalWatcher:
    """Test global watcher functions."""

    @pytest.fixture(autouse=True)
    async def cleanup(self):
        """Cleanup global watcher after each test."""
        yield
        await stop_config_watcher()

    @pytest.mark.asyncio
    async def test_start_watcher_in_dev_mode(self):
        """Watcher starts in development mode."""
        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.is_development = True
            mock_get.return_value = mock_settings

            watcher = await start_config_watcher()

            assert watcher is not None
            assert watcher.is_running

            await watcher.stop()

    @pytest.mark.asyncio
    async def test_watcher_disabled_in_production(self):
        """Watcher doesn't start in production mode."""
        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.is_development = False
            mock_get.return_value = mock_settings

            watcher = await start_config_watcher()

            assert watcher is None

    @pytest.mark.asyncio
    async def test_force_enable_watcher(self):
        """Watcher can be force-enabled."""
        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.is_development = False
            mock_get.return_value = mock_settings

            watcher = await start_config_watcher(enabled=True)

            assert watcher is not None
            await watcher.stop()

    @pytest.mark.asyncio
    async def test_get_config_watcher(self):
        """get_config_watcher returns current instance."""
        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.is_development = True
            mock_get.return_value = mock_settings

            watcher = await start_config_watcher()
            retrieved = get_config_watcher()

            assert retrieved is watcher

            await watcher.stop()

    @pytest.mark.asyncio
    async def test_callback_registered_on_start(self):
        """Callback passed to start is registered."""
        callback = MagicMock()

        with patch("src.config.settings.get_settings") as mock_get:
            mock_settings = MagicMock()
            mock_settings.is_development = True
            mock_get.return_value = mock_settings

            watcher = await start_config_watcher(on_reload=callback)

            assert callback in watcher.callbacks

            await watcher.stop()
