"""Pydantic models for hub-mcp config. Mirrors specs/002-skeleton-core/data-model.md."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from hub_mcp.exceptions import ConfigError

# Default paths (overridden by env vars)
DEFAULT_CONFIG_PATH = "~/.harness-hub/config.yaml"
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 46380
DEFAULT_HINDSIGHT_URL = "http://127.0.0.1:8888/v1"
DEFAULT_HINDSIGHT_BANK_ID = "default"
DEFAULT_UPSTREAM_TIMEOUT = 60.0
MIN_UPSTREAM_TIMEOUT = 1.0
MAX_UPSTREAM_NAME_LENGTH = 64
MAX_URL_LENGTH = 2048
MIN_PORT = 1
MAX_PORT = 65535

# Environment variable names (override config file)
ENV_CONFIG_PATH = "HUB_CONFIG_PATH"
ENV_LISTEN_HOST = "HUB_LISTEN_HOST"
ENV_LISTEN_PORT = "HUB_LISTEN_PORT"
ENV_HINDSIGHT_URL = "HUB_HINDSIGHT_URL"


class ListenConfig(BaseModel):
    """TCP listen address."""

    host: str = DEFAULT_LISTEN_HOST
    port: int = Field(default=DEFAULT_LISTEN_PORT, ge=MIN_PORT, le=MAX_PORT)


class HindsightConfig(BaseModel):
    """Hindsight audit endpoint."""

    url: str = DEFAULT_HINDSIGHT_URL
    bank_id: str = DEFAULT_HINDSIGHT_BANK_ID
    enabled: bool = True


class UpstreamConfig(BaseModel):
    """Single upstream MCP server (HTTP transport only in MVP)."""

    name: str = Field(min_length=1, max_length=MAX_UPSTREAM_NAME_LENGTH)
    url: str = Field(min_length=1, max_length=MAX_URL_LENGTH)
    enabled: bool = True
    timeout: float = Field(default=DEFAULT_UPSTREAM_TIMEOUT, ge=MIN_UPSTREAM_TIMEOUT)
    audit_level: Literal["full", "metadata_only"] = "full"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"upstream name must be alphanumeric with hyphens/underscores: {v!r}")
        return v


class HubConfig(BaseModel):
    """Top-level hub configuration."""

    listen: ListenConfig = Field(default_factory=ListenConfig)
    hindsight: HindsightConfig = Field(default_factory=HindsightConfig)
    upstream: list[UpstreamConfig] = Field(min_length=1)

    @field_validator("upstream")
    @classmethod
    def _validate_unique_upstream_names(cls, v: list[UpstreamConfig]) -> list[UpstreamConfig]:
        names = [u.name for u in v]
        if len(names) != len(set(names)):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"duplicate upstream names: {duplicates}")
        return v


def _default_config_path() -> Path:
    """Resolve default config path, respecting $HUB_CONFIG_PATH."""
    raw = os.environ.get(ENV_CONFIG_PATH)
    return Path(raw).expanduser() if raw else Path(DEFAULT_CONFIG_PATH).expanduser()


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    """Apply environment variable overrides to parsed YAML dict (shallow copy)."""
    raw = dict(raw)
    if ENV_LISTEN_HOST in os.environ:
        raw.setdefault("listen", {})["host"] = os.environ[ENV_LISTEN_HOST]
    if ENV_LISTEN_PORT in os.environ:
        raw.setdefault("listen", {})["port"] = int(os.environ[ENV_LISTEN_PORT])
    if ENV_HINDSIGHT_URL in os.environ:
        raw.setdefault("hindsight", {})["url"] = os.environ[ENV_HINDSIGHT_URL]
    return raw


def load_config(path: Path | None = None) -> HubConfig:
    """Load and validate hub config from YAML file.

    Args:
        path: config file path. Default: $HUB_CONFIG_PATH or ~/.harness-hub/config.yaml.

    Returns:
        Validated HubConfig.

    Raises:
        ConfigError: file not found, YAML invalid, schema mismatch, or YAML not a mapping.
    """
    config_path = (path or _default_config_path()).expanduser()
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {config_path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"config must be a YAML mapping, got {type(raw).__name__}")

    raw = _apply_env_overrides(cast("dict[str, Any]", raw))

    try:
        return HubConfig.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"config validation failed: {e}") from e
