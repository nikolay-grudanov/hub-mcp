# Implementation Plan: 003 — stdio upstream + hot-reload + tooling fix

> **For agents**: Use `subagent-driven-development` skill. Each task = 2-5 minutes focused work. TDD: test → fail → impl → pass → commit (after Kolya's explicit «коммить»).

> **Estimated total**: 3-4 часа. Не «1-2 дня» как в roadmap — discriminated union + SDK stdio_client даёт минимальный code change.

**Goal**: hub-mcp Phase 2 — stdio upstream + hot-reload + fix pre-commit hook + submit SDK bug.
**Architecture**: Same as Phase 1 (Starlette + mcp SDK + Pydantic), с добавлением discriminated union в `UpstreamConfig.transport`, stdio branch в `UpstreamClient.start()`, SIGHUP signal handler в `_lifespan`.
**Tech Stack**: Python 3.11+, mcp SDK 1.9+ (уже), pydantic 2.x, pytest 8+, signals from stdlib.

---

## Phase 1: Discriminated transport в config

### Task 1.1: TDD для discriminated union

**Objective**: добавить `TransportConfig` (HttpTransport | StdioTransport) в `src/hub_mcp/config.py` с backward-compat для Phase 1 `url: str`.

**Files**:
- Modify: `src/hub_mcp/config.py`
- Modify: `tests/test_config.py`

**Step 1**: Append to `tests/test_config.py`:
```python
def test_http_transport_parsed_from_kind() -> None:
    cfg = UpstreamConfig.model_validate({
        "name": "x",
        "transport": {"kind": "http", "url": "http://x/"},
    })
    assert isinstance(cfg.transport, HttpTransport)
    assert cfg.transport.url == "http://x/"


def test_stdio_transport_parsed_from_kind() -> None:
    cfg = UpstreamConfig.model_validate({
        "name": "arxiv",
        "transport": {
            "kind": "stdio",
            "command": "uv",
            "args": ["tool", "run", "arxiv-mcp-server"],
        },
    })
    assert isinstance(cfg.transport, StdioTransport)


def test_backward_compat_url_field() -> None:
    cfg = UpstreamConfig.model_validate({"name": "x", "url": "http://x/"})
    assert isinstance(cfg.transport, HttpTransport)
    assert cfg.transport.url == "http://x/"


def test_invalid_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        UpstreamConfig.model_validate({
            "name": "x",
            "transport": {"kind": "websocket", "url": "ws://x/"},
        })


def test_stdio_transport_command_required() -> None:
    with pytest.raises(ValidationError):
        UpstreamConfig.model_validate({
            "name": "x",
            "transport": {"kind": "stdio"},
        })
```

**Step 2**: Run test → fail (HttpTransport/StdioTransport not defined).

**Step 3**: Modify `src/hub_mcp/config.py`:
- Add imports: `from typing import Annotated, Literal`
- Add `HttpTransport` + `StdioTransport` classes
- Replace `url: str` with `transport: TransportConfig` in `UpstreamConfig`
- Add `_backward_compat_url` model_validator

**Step 4**: Run test → 5 passed. Verify all 17 existing tests still pass (no regression).

**Step 5**: Commit (after Kolya's «коммить»):
```bash
git add src/hub_mcp/config.py tests/test_config.py
git commit -m "feat(003): discriminated union for UpstreamConfig.transport"
```

---

## Phase 2: UpstreamClient stdio branch

### Task 2.1: TDD для stdio upstream spawn

**Objective**: добавить stdio branch в `UpstreamClient.start()`.

**Files**:
- Modify: `src/hub_mcp/upstream.py`
- Modify: `tests/test_upstream.py`

**Step 1**: Append to `tests/test_upstream.py`:
```python
import sys
import tempfile
import textwrap

# Fake MCP server: reads JSON-RPC lines, responds with initialize/tools-list
FAKE_MCP_SERVER = textwrap.dedent('''
    import sys, json
    while True:
        line = input()
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("method") == "initialize":
            print(json.dumps({
                "jsonrpc": "2.0", "id": msg["id"],
                "result": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "fake", "version": "0"},
                },
            }), flush=True)
        elif msg.get("method") == "notifications/initialized":
            pass  # no response
        elif msg.get("method") == "tools/list":
            print(json.dumps({
                "jsonrpc": "2.0", "id": msg["id"],
                "result": {
                    "tools": [{
                        "name": "fake_tool",
                        "description": "fake",
                        "inputSchema": {"type": "object", "properties": {}},
                    }],
                },
            }), flush=True)
        elif msg.get("method") == "tools/call":
            print(json.dumps({
                "jsonrpc": "2.0", "id": msg["id"],
                "result": {"content": [{"type": "text", "text": "fake-result"}]},
            }), flush=True)
''')


@pytest.fixture
def fake_stdio_server_script(tmp_path):
    script = tmp_path / "fake_mcp.py"
    script.write_text(FAKE_MCP_SERVER)
    return script


async def test_stdio_upstream_spawns_and_connects(fake_stdio_server_script) -> None:
    """UpstreamClient with stdio transport spawns subprocess, init, list tools."""
    from hub_mcp.config import StdioTransport

    transport = StdioTransport(
        kind="stdio", command=sys.executable, args=[str(fake_stdio_server_script)]
    )
    client = UpstreamClient(name="fake", transport=transport, timeout=10.0)
    await client.start()
    try:
        assert client.is_started
        assert client.server_info.name == "fake"
        tools = await client.list_tools()
        assert any(t.name == "fake_tool" for t in tools)
    finally:
        await client.stop()


async def test_stdio_upstream_env_propagation(fake_stdio_server_script, monkeypatch) -> None:
    """StdioTransport.env merged with os.environ at spawn time."""
    from hub_mcp.config import StdioTransport

    monkeypatch.setenv("HUB_TEST_VAR", "default_value")

    env_script = tmp_path_factory()  # use tmp_path fixture inline instead
    # ... (see real test in tests/test_upstream.py)
```

**Step 2**: Run test → fail (UpstreamClient doesn't accept `transport: TransportConfig` yet).

**Step 3**: Modify `src/hub_mcp/upstream.py`:
- Replace `url: str` with `transport: TransportConfig` in `__init__`
- Add helper `_open_streams_cm()` returning `streamable_http_client` or `stdio_client` context manager based on `transport.kind`
- Wrap `start()` in `try/except UpstreamUnavailableError`

**Step 4**: Run test → passed. Verify all 11 existing tests still pass (parameter change required updating `UpstreamClient(name="mock", url="...")` calls).

**Step 5**: Commit.

---

## Phase 3: SIGHUP hot-reload

### Task 3.1: Config loader — возвращает mtime + path

**Objective**: `load_config()` экспортирует путь и mtime для diff detection.

**Files**:
- Modify: `src/hub_mcp/config.py`
- Modify: `tests/test_config.py`

**Step 1**: Append to `tests/test_config.py`:
```python
def test_load_config_returns_path_and_mtime(tmp_path) -> None:
    from hub_mcp.config import load_config_with_metadata
    config_path = tmp_path / "config.yaml"
    config_path.write_text("upstream:\n  - name: x\n    url: http://x/\n")
    cfg, path, mtime = load_config_with_metadata(config_path)
    assert path == config_path
    assert mtime > 0
    assert cfg.upstream[0].name == "x"
```

**Step 2**: Implement `load_config_with_metadata()` as tuple `(HubConfig, Path, float)`.

**Step 3**: Commit.

### Task 3.2: SIGHUP signal handler в lifespan

**Objective**: hub получает SIGHUP, перечитывает config, обновляет upstream_map.

**Files**:
- Modify: `src/hub_mcp/server.py`
- Modify: `tests/test_server.py`

**Step 1**: Append to `tests/test_server.py`:
```python
def test_hot_reload_adds_new_upstream(tmp_path) -> None:
    """SIGHUP after adding upstream → upstream_map updated."""
    import signal

    initial_config = """
    listen:
      host: 127.0.0.1
      port: 46380
    hindsight:
      enabled: false
    upstream:
      - name: fetch
        enabled: true
        transport:
          kind: http
          url: http://localhost:46381/mcp
    """
    config_path = tmp_path / "config.yaml"
    config_path.write_text(initial_config)

    mock_fetch = MockUpstream(tools=["fetch_html"])

    def scenario():
        async def run():
            app = create_app(
                config_path=config_path,
                transport_overrides={"fetch": httpx.MockTransport(mock_fetch)},
            )
            async with app.router.lifespan_context(app):
                assert "fetch" in app.state.upstream_map
                assert "arxiv" not in app.state.upstream_map

                # Add stdio upstream
                updated = initial_config + '''
      - name: arxiv
        enabled: true
        transport:
          kind: stdio
          command: python
          args: ["-c", "pass"]
        timeout: 30.0
    '''
                config_path.write_text(updated)
                os.kill(os.getpid(), signal.SIGHUP)
                await asyncio.sleep(0.5)

                # arxiv may or may not start (Python -c "pass" will exit immediately),
                # but config was reloaded
                assert app.state.config.upstream[-1].name == "arxiv"
        return asyncio.run(run())

    scenario()
```

**Step 2**: Implement `_lifespan`:
- Save `config_path` in `app.state`
- Register SIGHUP handler: `loop.add_signal_handler(signal.SIGHUP, lambda: asyncio.ensure_future(_reload_config(app)))`
- On signal: reload, diff, add/remove/restart upstream'ы

**Step 3**: Run test → passed.

**Step 4**: Commit.

### Task 3.3: Invalid YAML keep old config

**Step 1**: Test that broken YAML after SIGHUP keeps old config.
**Step 2**: Implement in `_reload_config`: catch `ConfigError` / `ValidationError`, log error, return.
**Step 3**: Commit.

---

## Phase 4: Pre-commit hook fix (OQ-hub-014)

### Task 4.1: Refactor hook с explicit step handling

**Files**:
- Modify: `.git/hooks/pre-commit`

**Step 1**: Replace bash script with `run_step` pattern (см. data-model.md).
**Step 2**: Test: `git commit` with passing gate → success. With broken gate → exit code from failed step.
**Step 3**: Commit (после Kolya's «коммить»).

---

## Phase 5: SDK bug report (OQ-hub-013)

### Task 5.1: Создать минимальный repro

**Files**:
- Create: `scratch/sdk_bug_repro.py` (not in repo, just local)

**Step 1**: 15-строк async script: `httpx.MockTransport` raising `httpx.ConnectError` sync + `streamable_http_client` → `RuntimeError: cancel scope`.

**Step 2**: Verify it reproduces in standalone run.

### Task 5.2: Submit issue в modelcontextprotocol/python-sdk

**Step 1**: Open browser to https://github.com/modelcontextprotocol/python-sdk/issues/new.
**Step 2**: Title: "RuntimeError: Attempted to exit cancel scope in a different task when httpx.MockTransport raises synchronously".
**Step 3**: Body: repro code + expected behavior + actual behavior + SDK version.
**Step 4**: Submit. Add link to OQ-hub-013 в `docs/open-questions.md`.

---

## Phase 6: Live debug + Kolya's config update

### Task 6.1: Update Kolya's `~/.harness-hub/config.yaml`

**Objective**: заменить stdio placeholder URL'ы на реальные stdio upstream'ы.

**Step 1**: Edit config.yaml, replace:
- `arxiv-mcp`: HTTP placeholder → stdio `uv tool run --from arxiv-mcp-server arxiv-mcp-server`
- `fetch`: HTTP placeholder → stdio `npx -y mcp-fetch-server`
- `repomix`: HTTP placeholder → stdio `npx ... --mcp`
- `zai`: HTTP placeholder → stdio `zai-mcp-server` (or HTTP если есть)

**Step 2**: Run hub, verify all stdio upstream'ы spawn успешно.

### Task 6.2: Live test: stdio + HTTP + SIGHUP

**Step 1**: Start hub, `tools/list` → должны быть tools от arxiv (stdio) + hindsight/qmd/deepwiki/context7 (HTTP).
**Step 2**: `tools/call arxiv.search_papers` → реальный arxiv response.
**Step 3**: `kill -HUP $(pgrep hub)` после edit config.yaml → config reloaded без рестарта.
**Step 4**: Verify in `~/.hermes/profiles/harness/config.yaml` что `mcp_servers` могут быть заменены на 1 entry: hub.

### Task 6.3: Pre-commit gate

- [ ] `uv run ruff check src/ tests/` → 0 errors
- [ ] `uv run ruff format --check src/ tests/` → 0 differences
- [ ] `uv run pyright src/` → 0 errors
- [ ] `uv run pytest tests/ -v` → 50+ passed (4 new stdio + 3 new hot-reload + 1 SDK bug repro), 1 skipped (OQ-hub-013)

---

## Summary

6 phase'ов, ~15 bite-sized tasks, 3-4 часа. Все gates зелёные. Live verified с 5+ real upstream'ами (4 HTTP + 1-2 stdio).

Следующий шаг (Phase 3): per-profile filtering возвращается (ADR-002).