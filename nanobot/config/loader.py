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

    # Map standard environment variable names to config attributes
    provider_env_map = {
        "GROQ_API_KEY": ("providers", "groq", "api_key"),
        "GEMINI_API_KEY": ("providers", "gemini", "api_key"),
        "OPENAI_API_KEY": ("providers", "openai", "api_key"),
        "ANTHROPIC_API_KEY": ("providers", "anthropic", "api_key"),
        "OPENROUTER_API_KEY": ("providers", "openrouter", "api_key"),
        "DEEPSEEK_API_KEY": ("providers", "deepseek", "api_key"),
    }

    for env_var, path in provider_env_map.items():
        val = os.environ.get(env_var)
        if val:
            # Only override if not already set (or if it's the empty default)
            target = config
            for step in path[:-1]:
                target = getattr(target, step)
            
            current_val = getattr(target, path[-1])
            if not current_val:
                setattr(target, path[-1], val)

    # Agent defaults
    if os.environ.get("LLM_PROVIDER") and config.agents.defaults.provider == "auto":
        config.agents.defaults.provider = os.environ.get("LLM_PROVIDER")
    
    # Model can be overridden always if provided via ENV
    env_model = os.environ.get("MODEL") or os.environ.get("LLM_MODEL")
    if env_model:
        config.agents.defaults.model = env_model



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
