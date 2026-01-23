"""Hot-reload configuration manager using watchfiles.

Watches configuration files and triggers reloads when changes detected.
Useful for development and operational configuration updates.

Usage:
    from src.config.hot_reload import ConfigWatcher, start_config_watcher

    # Start watching (typically in app startup)
    watcher = await start_config_watcher(
        on_reload=lambda: print("Config reloaded!")
    )

    # Stop watching (in app shutdown)
    await watcher.stop()

Note: Only enabled in development mode by default.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import structlog
from watchfiles import Change, awatch

logger = structlog.get_logger(__name__)


@dataclass
class ConfigWatcher:
    """
    Watches configuration files and triggers reloads on changes.

    Monitors:
    - .env file (primary configuration)
    - .env.local (local overrides)
    - Any additional paths specified

    On change:
    1. Validates new configuration
    2. Clears settings cache
    3. Calls registered callbacks
    """

    watch_paths: list[Path] = field(default_factory=list)
    callbacks: list[Callable[[], None]] = field(default_factory=list)
    _task: Optional[asyncio.Task] = field(default=None, init=False)
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _running: bool = field(default=False, init=False)

    def __post_init__(self):
        """Initialize with default paths if none provided."""
        if not self.watch_paths:
            # Default to watching .env files in project root
            project_root = Path(__file__).parent.parent.parent
            self.watch_paths = [
                project_root / ".env",
                project_root / ".env.local",
            ]
            # Filter to only existing files
            self.watch_paths = [p for p in self.watch_paths if p.exists()]

    def add_callback(self, callback: Callable[[], None]) -> None:
        """
        Register a callback to be called on config reload.

        Args:
            callback: Function to call when config changes
        """
        self.callbacks.append(callback)
        callback_name = getattr(callback, "__name__", repr(callback))
        logger.debug("config_watcher_callback_added", callback=callback_name)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove a previously registered callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    async def _reload_settings(self) -> bool:
        """
        Reload settings and validate.

        Returns:
            True if reload successful, False if validation failed
        """
        try:
            # Clear the settings cache
            from src.config.settings import get_settings

            get_settings.cache_clear()

            # Try to load new settings (validates automatically)
            new_settings = get_settings()

            logger.info(
                "config_reloaded",
                app_env=new_settings.app_env,
                debug=new_settings.debug,
            )

            # Call all registered callbacks
            for callback in self.callbacks:
                try:
                    callback()
                except Exception as e:
                    callback_name = getattr(callback, "__name__", repr(callback))
                    logger.error(
                        "config_reload_callback_error",
                        callback=callback_name,
                        error=str(e),
                    )

            return True

        except Exception as e:
            logger.error(
                "config_reload_failed",
                error=str(e),
                message="Configuration invalid - keeping previous settings",
            )
            return False

    async def _watch_loop(self) -> None:
        """Main watch loop - monitors files and triggers reloads."""
        logger.info(
            "config_watcher_started",
            paths=[str(p) for p in self.watch_paths],
        )

        try:
            async for changes in awatch(
                *self.watch_paths,
                stop_event=self._stop_event,
                debounce=500,  # 500ms debounce to batch rapid changes
            ):
                if self._stop_event.is_set():
                    break

                # Log what changed
                for change_type, path in changes:
                    change_name = {
                        Change.added: "added",
                        Change.modified: "modified",
                        Change.deleted: "deleted",
                    }.get(change_type, "unknown")

                    logger.info(
                        "config_file_changed",
                        path=str(path),
                        change=change_name,
                    )

                # Reload settings
                await self._reload_settings()

        except asyncio.CancelledError:
            logger.debug("config_watcher_cancelled")
        except Exception as e:
            logger.error("config_watcher_error", error=str(e))
        finally:
            self._running = False
            logger.info("config_watcher_stopped")

    async def start(self) -> None:
        """Start watching for configuration changes."""
        if self._running:
            logger.warning("config_watcher_already_running")
            return

        if not self.watch_paths:
            logger.warning("config_watcher_no_paths", message="No config files to watch")
            return

        self._stop_event.clear()
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("config_watcher_task_created")

    async def stop(self) -> None:
        """Stop watching for configuration changes."""
        if not self._running:
            return

        logger.info("config_watcher_stopping")
        self._stop_event.set()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if watcher is currently running."""
        return self._running


# Global watcher instance
_config_watcher: Optional[ConfigWatcher] = None


async def start_config_watcher(
    on_reload: Optional[Callable[[], None]] = None,
    watch_paths: Optional[list[Path]] = None,
    enabled: Optional[bool] = None,
) -> Optional[ConfigWatcher]:
    """
    Start the global config watcher.

    Args:
        on_reload: Callback to run on config reload
        watch_paths: Paths to watch (defaults to .env files)
        enabled: Force enable/disable (defaults to development mode only)

    Returns:
        ConfigWatcher instance if started, None if disabled
    """
    global _config_watcher

    # Determine if should be enabled
    if enabled is None:
        from src.config.settings import get_settings

        settings = get_settings()
        enabled = settings.is_development

    if not enabled:
        logger.info("config_watcher_disabled", reason="Not in development mode")
        return None

    # Create watcher if needed
    if _config_watcher is None:
        _config_watcher = ConfigWatcher(
            watch_paths=watch_paths or [],
        )

    # Add callback if provided
    if on_reload:
        _config_watcher.add_callback(on_reload)

    # Start watching
    await _config_watcher.start()

    return _config_watcher


async def stop_config_watcher() -> None:
    """Stop the global config watcher."""
    global _config_watcher

    if _config_watcher:
        await _config_watcher.stop()
        _config_watcher = None


def get_config_watcher() -> Optional[ConfigWatcher]:
    """Get the current config watcher instance."""
    return _config_watcher
