"""Configuration loading utilities."""

import json
from pathlib import Path

from nanobot.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".nanobot" / "config.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()
    config = None

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            config = Config.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    if config is None:
        config = Config()

    # Apply environment variable overrides for easier Docker/Cloud deployment
    _apply_env_overrides(config)

    return config


def _apply_env_overrides(config: Config) -> None:
    """Apply standard environment variables as fallbacks if not set in config."""
    import os

    def _is_true(env_name: str) -> bool:
        val = os.environ.get(env_name, "").lower()
        return val in ("true", "1", "yes", "on")

    # Map standard environment variable names to config attributes (mostly for remaining services)
    provider_env_map = {
        # Custom / Local providers don't need fixed env mapping here
    }

    for env_var, path in provider_env_map.items():
        val = os.environ.get(env_var)
        if val:
            target = config
            for step in path[:-1]:
                target = getattr(target, step)
            setattr(target, path[-1], val)

    # Channels overrides
    if _is_true("TELEGRAM_ENABLED"):
        config.channels.telegram.enabled = True
        if os.environ.get("TELEGRAM_TOKEN"):
            config.channels.telegram.token = os.environ.get("TELEGRAM_TOKEN")
        
        # Security: Nanobot fails if allow_from is empty. Default to ["*"] if not set.
        allow_from = os.environ.get("TELEGRAM_ALLOW_FROM")
        if allow_from:
            config.channels.telegram.allow_from = [x.strip() for x in allow_from.split(",")]
        elif not config.channels.telegram.allow_from:
            config.channels.telegram.allow_from = ["*"]

    if _is_true("WHATSAPP_ENABLED"):
        config.channels.whatsapp.enabled = True
        allow_from = os.environ.get("WHATSAPP_ALLOW_FROM")
        if allow_from:
            config.channels.whatsapp.allow_from = [x.strip() for x in allow_from.split(",")]
        elif not config.channels.whatsapp.allow_from:
            config.channels.whatsapp.allow_from = ["*"]

        if _is_true("WHATSAPP_SECRETARY_MODE"):
            config.channels.whatsapp.secretary_mode = True
        if os.environ.get("WHATSAPP_SECRETARY_TARGET"):
            config.channels.whatsapp.secretary_target = os.environ.get("WHATSAPP_SECRETARY_TARGET")

    # Note: LLM_PROVIDER and MODEL overrides are now handled by Pydantic 
    # via NANOBOT_AGENTS__DEFAULTS__PROVIDER and NANOBOT_AGENTS__DEFAULTS__MODEL
    # to avoid conflicts with generic environment variables.
    pass




def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
