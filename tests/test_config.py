"""Tests for HubConfig Pydantic model (spec-002 Task 2.1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hub_mcp.config import HindsightConfig, HubConfig, ListenConfig, UpstreamConfig, load_config
from hub_mcp.exceptions import ConfigError


def test_config_minimal_valid() -> None:
    """Minimal config with single upstream uses defaults for the rest."""
    cfg = HubConfig(
        upstream=[
            UpstreamConfig(name="fetch", url="http://localhost:46381/mcp"),
        ],
    )
    assert len(cfg.upstream) == 1
    assert cfg.listen.host == "127.0.0.1"  # default
    assert cfg.listen.port == 46380  # default
    assert cfg.hindsight.bank_id == "default"  # default
    assert cfg.hindsight.enabled is True  # default


def test_upstream_name_alphanumeric() -> None:
    """Upstream name must be alphanumeric with hyphens/underscores."""
    with pytest.raises(ValidationError):
        UpstreamConfig(name="bad name", url="http://x/")
    with pytest.raises(ValidationError):
        UpstreamConfig(name="bad/name", url="http://x/")


def test_upstream_timeout_minimum() -> None:
    """Upstream timeout >= 1 second."""
    with pytest.raises(ValidationError):
        UpstreamConfig(name="x", url="http://x/", timeout=0.5)


def test_listen_port_range() -> None:
    """Listen port must be 1-65535."""
    with pytest.raises(ValidationError):
        ListenConfig(port=70000)
    with pytest.raises(ValidationError):
        ListenConfig(port=0)


def test_hindsight_audit_default_enabled() -> None:
    """Hindsight audit enabled by default."""
    cfg = HindsightConfig()
    assert cfg.enabled is True


def test_upstream_audit_level_literal() -> None:
    """audit_level accepts only 'full' or 'metadata_only'."""
    UpstreamConfig(name="x", url="http://x/", audit_level="full")
    UpstreamConfig(name="x", url="http://x/", audit_level="metadata_only")
    with pytest.raises(ValidationError):
        UpstreamConfig(name="x", url="http://x/", audit_level="verbose")  # type: ignore[arg-type]


def test_duplicate_upstream_names_rejected() -> None:
    """Duplicate upstream names raise ValidationError."""
    with pytest.raises(ValidationError, match="duplicate upstream names"):
        HubConfig(
            upstream=[
                UpstreamConfig(name="fetch", url="http://a/"),
                UpstreamConfig(name="fetch", url="http://b/"),
            ],
        )


def test_upstream_can_be_disabled() -> None:
    """Upstream with enabled=false is valid."""
    u = UpstreamConfig(name="repomix", url="http://x/", enabled=False)
    assert u.enabled is False


def test_empty_upstream_list_rejected() -> None:
    """HubConfig requires at least 1 upstream."""
    with pytest.raises(ValidationError):
        HubConfig(upstream=[])


def test_load_config_from_yaml(tmp_path: Path) -> None:
    """Load valid YAML config from disk."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("upstream:\n  - name: fetch\n    url: http://localhost:46381/mcp\n")
    cfg = load_config(config_path)
    assert cfg.upstream[0].name == "fetch"


def test_load_config_missing_file(tmp_path: Path) -> None:
    """Missing config file raises ConfigError."""
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.yaml")


def test_load_config_invalid_yaml(tmp_path: Path) -> None:
    """Garbage YAML raises ConfigError."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("[invalid: yaml:")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(config_path)


def test_load_config_not_a_mapping(tmp_path: Path) -> None:
    """YAML that's a list (not mapping) raises ConfigError."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError, match="must be a YAML mapping"):
        load_config(config_path)


def test_load_config_pydantic_validation_failure(tmp_path: Path) -> None:
    """Valid YAML but invalid schema raises ConfigError."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "upstream:\n"
        "  - name: x\n"
        "    url: http://x/\n"
        "  - name: x\n"  # duplicate
        "    url: http://y/\n"
    )
    with pytest.raises(ConfigError, match="validation failed"):
        load_config(config_path)


def test_load_config_env_override_listen_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HUB_LISTEN_PORT env var overrides config listen.port."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text("listen:\n  port: 46380\nupstream:\n  - name: x\n    url: http://x/\n")
    monkeypatch.setenv("HUB_LISTEN_PORT", "50000")
    cfg = load_config(config_path)
    assert cfg.listen.port == 50000


def test_load_config_env_override_listen_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HUB_LISTEN_HOST env var overrides config listen.host."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "listen:\n  host: 127.0.0.1\nupstream:\n  - name: x\n    url: http://x/\n"
    )
    monkeypatch.setenv("HUB_LISTEN_HOST", "0.0.0.0")
    cfg = load_config(config_path)
    assert cfg.listen.host == "0.0.0.0"


def test_load_config_env_override_hindsight_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HUB_HINDSIGHT_URL env var overrides config hindsight.url."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "hindsight:\n  url: http://default:8888/v1\nupstream:\n  - name: x\n    url: http://x/\n"
    )
    monkeypatch.setenv("HUB_HINDSIGHT_URL", "http://custom:9999/v1")
    cfg = load_config(config_path)
    assert cfg.hindsight.url == "http://custom:9999/v1"
