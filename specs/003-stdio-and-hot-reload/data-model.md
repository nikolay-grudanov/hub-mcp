# Data Model: 003 — stdio upstream + hot-reload + tooling fix

Pydantic v2 схемы для Phase 2. Backward-compatible с Phase 1 (HTTP upstream'ы через `url: str` продолжают работать).

## Core change: `UpstreamConfig.transport` discriminated union

**Phase 1 (текущая)**:
```python
class UpstreamConfig(BaseModel):
    name: str
    url: str
    enabled: bool = True
    timeout: float = 60.0
    audit_level: Literal["off","metadata","full"] = "full"
```

**Phase 2 (новая)**:
```python
class HttpTransport(BaseModel):
    kind: Literal["http"] = "http"
    url: str = Field(..., min_length=1, max_length=2048)


class StdioTransport(BaseModel):
    kind: Literal["stdio"] = "stdio"
    command: str = Field(..., min_length=1)
    args: list[str] = Field(default_factory=list, max_length=64)
    env: dict[str, str] | None = None
    cwd: str | Path | None = None
    encoding: str = "utf-8"
    encoding_error_handler: Literal["strict","ignore","replace"] = "strict"


TransportConfig = Annotated[
    HttpTransport | StdioTransport,
    Field(discriminator="kind"),
]


class UpstreamConfig(BaseModel):
    name: str = Field(..., pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    enabled: bool = True
    timeout: float = Field(default=60.0, ge=1.0, le=300.0)
    audit_level: Literal["off","metadata","full"] = "full"
    transport: TransportConfig  # discriminated union

    # Backward-compat: accept `url: str` as shortcut for HttpTransport.
    # Phase 1 config format `url: http://...` auto-mapped to transport: {kind: http, url: ...}.
    @model_validator(mode="before")
    @classmethod
    def _backward_compat_url(cls, data: Any) -> Any:
        if isinstance(data, dict) and "transport" not in data and "url" in data:
            return {**data, "transport": {"kind": "http", "url": data["url"]}}
        return data
```

### Why discriminated union по `kind`

- **Type safety**: Pydantic выбирает правильный subclass на load. `transport: {kind: stdio, command: ...}` не примет поле `url` (HttpTransport-only).
- **Clearer errors**: при невалидной комбинации (e.g. `kind: stdio, url: ...`) — ValidationError сразу, не runtime crash.
- **Extensibility**: Phase 3+ может добавить `WebsocketTransport(kind: "websocket", url: ..., headers: ...)` без breaking change.

### Backward compat в YAML

Phase 1 config:
```yaml
upstream:
  - name: hindsight
    url: http://127.0.0.1:8888/mcp/harness/
    enabled: true
```

Phase 2 config (тот же эффект, новый стиль):
```yaml
upstream:
  - name: hindsight
    enabled: true
    transport:
      kind: http
      url: http://127.0.0.1:8888/mcp/harness/
```

Оба работают благодаря `_backward_compat_url` валидатору. Phase 1 конфиги Kolya не требуют изменений.

## StdioTransport подробно

Поля один-к-одному с `mcp.client.stdio.StdioServerParameters`:

| Поле | SDK поле | Описание |
|---|---|---|
| `command` | `command` | Executable (required). `"uv"`, `"npx"`, etc. |
| `args` | `args` | CLI args. `["tool","run","--from","arxiv-mcp-server","arxiv-mcp-server"]` |
| `env` | `env` | Extra env vars, merged over `os.environ` (auto-merging by SDK) |
| `cwd` | `cwd` | Working directory. None = inherit. `str \| Path`. |
| `encoding` | `encoding` | `"utf-8"` default |
| `encoding_error_handler` | `encoding_error_handler` | `"strict"`, `"ignore"`, `"replace"` |

### Example: arxiv stdio (from Kolya's real config)

```yaml
upstream:
  - name: arxiv
    enabled: true
    timeout: 60.0
    audit_level: full
    transport:
      kind: stdio
      command: uv
      args:
        - tool
        - run
        - --from
        - arxiv-mcp-server
        - arxiv-mcp-server
```

### Example: fetch stdio (через npx)

```yaml
upstream:
  - name: fetch
    enabled: true
    timeout: 30.0
    transport:
      kind: stdio
      command: npx
      args:
        - -y
        - mcp-fetch-server
```

### Example: stdio с env (auth tokens)

```yaml
upstream:
  - name: my-paid-api
    enabled: true
    timeout: 60.0
    transport:
      kind: stdio
      command: /opt/bin/my-mcp-server
      env:
        MY_API_KEY: "sk-..."  # Or reference env var: env: {MY_API_KEY: "${MY_API_KEY}"}
        DEBUG: "1"
```

**Note**: Pydantic не раскрывает shell-стиль `${VAR}` substitutions. Если нужна env-var interpolation, делаем в `load_config()` (Phase 2 mini-feature: replace `${VAR}` patterns in env dict).

## SIGHUP signal handler state

Hub устанавливает signal handler в lifespan startup. State хранится в `app.state`:

```python
# In _lifespan
app.state.config_path = config_path
app.state.config_mtime = config_path.stat().st_mtime
app.state.config_loaded_at = time.time()
loop = asyncio.get_event_loop()
loop.add_signal_handler(
    signal.SIGHUP,
    lambda: asyncio.ensure_future(self._reload_config(app)),
)
```

### Config diff algorithm

```python
async def _reload_config(app: Starlette) -> None:
    config_path = app.state.config_path
    try:
        new_config = load_config(config_path)
    except (ConfigError, ValidationError) as e:
        logger.error("config reload failed (keeping old): %s", e)
        return

    old = app.state.config
    old_by_name = {u.name: u for u in old.upstream}
    new_by_name = {u.name: u for u in new_config.upstream}

    added = [n for n in new_by_name if n not in old_by_name]
    removed = [n for n in old_by_name if n not in new_by_name]
    changed = [
        n for n in new_by_name
        if n in old_by_name and _upstream_changed(old_by_name[n], new_by_name[n])
    ]

    # Add new
    for name in added:
        if new_by_name[name].enabled:
            client = UpstreamClient(transport=new_by_name[name].transport, ...)
            try:
                await client.start()
                app.state.upstream_map[name] = client
            except UpstreamUnavailableError as e:
                logger.warning("reload: upstream %s start failed: %s", name, e)

    # Remove
    for name in removed:
        if name in app.state.upstream_map:
            await app.state.upstream_map[name].stop()
            del app.state.upstream_map[name]

    # Replace changed
    for name in changed:
        if name in app.state.upstream_map:
            await app.state.upstream_map[name].stop()
        if new_by_name[name].enabled:
            client = UpstreamClient(transport=new_by_name[name].transport, ...)
            try:
                await client.start()
                app.state.upstream_map[name] = client
            except UpstreamUnavailableError as e:
                logger.warning("reload: upstream %s restart failed: %s", name, e)

    app.state.config = new_config
    app.state.config_mtime = config_path.stat().st_mtime
    logger.info("config reloaded: +%s -%s ~%s", added, removed, changed)
```

### `_upstream_changed` check

```python
def _upstream_changed(old: UpstreamConfig, new: UpstreamConfig) -> bool:
    if old.enabled != new.enabled:
        return True
    if old.timeout != new.timeout:
        return True
    if old.audit_level != new.audit_level:
        return True
    if old.transport != new.transport:  # Pydantic equality deep
        return True
    return False
```

## Pre-commit hook fix (OQ-hub-014)

**Current broken hook**:
```bash
#!/bin/bash
set -e
cd /home/gna/workspase/projects/hub-mcp
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pyright src/
uv run pytest tests/ -v --tb=short
echo "=== all green ==="
```

**Hypotheses для exit 250 после pyright**:
1. Sandbox signal-kills `uv run` child при достижении output/time limit (наш environment).
2. `set -e` + `set -o pipefail` без trap'а — first failing command exits without `echo "=== all green ==="`.

**Phase 2 fixed hook**:
```bash
#!/bin/bash
# Disable trap on ERR (we want to print "=== all green ===" only if ALL pass)
set +e

cd /home/gna/workspase/projects/hub-mcp

run_step() {
    local name="$1"
    shift
    echo "=== $name ==="
    if "$@"; then
        echo "=== $name OK ==="
    else
        local rc=$?
        echo "=== $name FAILED (exit $rc) ===" >&2
        exit $rc
    fi
}

run_step "ruff check" uv run ruff check src/ tests/
run_step "ruff format" uv run ruff format --check src/ tests/
run_step "pyright" uv run pyright src/
run_step "pytest" uv run pytest tests/ -v --tb=short
echo "=== all green ==="
```

**Why this fixes exit 250**:
- `set +e` убирает auto-exit on error, давая каждой `run_step` отработать.
- Each step имеет `if/else` с явной проверкой exit code — если pyright крашится с signal, мы увидим `exit 139` (SIGSEGV) или `exit 143` (SIGTERM) в логе, а не молчаливый exit 250.
- `echo "=== all green ==="` выводится только если все 4 step'а прошли.

**Альтернатива** (если sandbox продолжает ломать hook): перенести в `pre-push` hook (где другая sandbox-конфигурация):
```bash
# Rename .git/hooks/pre-commit → .git/hooks/pre-push
```

## Tests

### Config: discriminated union

```python
def test_http_transport_parsed_from_kind():
    cfg = UpstreamConfig.model_validate({
        "name": "x",
        "transport": {"kind": "http", "url": "http://x/"},
    })
    assert isinstance(cfg.transport, HttpTransport)
    assert cfg.transport.url == "http://x/"


def test_stdio_transport_parsed_from_kind():
    cfg = UpstreamConfig.model_validate({
        "name": "arxiv",
        "transport": {
            "kind": "stdio",
            "command": "uv",
            "args": ["tool", "run", "arxiv-mcp-server"],
        },
    })
    assert isinstance(cfg.transport, StdioTransport)
    assert cfg.transport.command == "uv"
    assert cfg.transport.args == ["tool", "run", "arxiv-mcp-server"]


def test_backward_compat_url_field():
    """Phase 1 config format `url: ...` still works."""
    cfg = UpstreamConfig.model_validate({"name": "x", "url": "http://x/"})
    assert isinstance(cfg.transport, HttpTransport)
    assert cfg.transport.url == "http://x/"


def test_invalid_kind_rejected():
    with pytest.raises(ValidationError):
        UpstreamConfig.model_validate({
            "name": "x",
            "transport": {"kind": "websocket", "url": "ws://x/"},  # not supported yet
        })


def test_stdio_transport_command_required():
    with pytest.raises(ValidationError):
        UpstreamConfig.model_validate({
            "name": "x",
            "transport": {"kind": "stdio"},  # command missing
        })
```

### Upstream: stdio branch

```python
async def test_stdio_upstream_spawn_and_initialize():
    """UpstreamClient with stdio transport spawns subprocess and connects."""
    # Use a tiny in-process fake MCP server for determinism
    fake_server = """
    import sys, json
    while True:
        line = input()
        msg = json.loads(line)
        if msg["method"] == "initialize":
            print(json.dumps({
                "jsonrpc": "2.0", "id": msg["id"],
                "result": {"protocolVersion": "2025-11-25", "capabilities": {}, "serverInfo": {"name": "fake", "version": "0"}},
            }))
            sys.stdout.flush()
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {}}))
            sys.stdout.flush()
    """
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(fake_server)
        script_path = f.name
    try:
        transport = StdioTransport(kind="stdio", command=sys.executable, args=[script_path])
        client = UpstreamClient(name="fake", transport=transport, timeout=5.0)
        await client.start()
        try:
            tools = await client.list_tools()  # fake server returns empty list
            assert isinstance(tools, list)
        finally:
            await client.stop()
    finally:
        os.unlink(script_path)


async def test_stdio_upstream_env_propagation():
    """Subprocess inherits shell env + StdioTransport.env merge."""
    # Fake server reads MY_TEST_VAR and returns it as a tool description
    fake_server = '''
    import sys, os, json
    while True:
        line = input()
        msg = json.loads(line)
        if msg["method"] == "initialize":
            val = os.environ.get("MY_TEST_VAR", "")
            print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{
                "protocolVersion":"2025-11-25","capabilities":{},
                "serverInfo":{"name":"env-test","version":"0","description":val}
            }}))
            sys.stdout.flush()
    '''
    ...


async def test_stdio_upstream_spawn_timeout():
    """Subprocess hanging on startup → UpstreamUnavailableError within 10s."""
    # Use `sleep 60` as command
    ...


async def test_stdio_upstream_stderr_captured():
    """Subprocess stderr logged via hub_mcp.upstream.{name}.stderr logger."""
    ...
```

### Server: hot-reload

```python
def test_hot_reload_adds_new_upstream(tmp_path):
    """SIGHUP after adding upstream → upstream_map updated."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(INITIAL_CONFIG)

    async def scenario():
        app = create_app(config_path=config_path)
        async with app.router.lifespan_context(app):
            assert "fetch" in app.state.upstream_map
            assert "arxiv" not in app.state.upstream_map

            # Edit config to add arxiv stdio upstream
            config_path.write_text(UPDATED_CONFIG_WITH_ARXIV)

            # Send SIGHUP
            os.kill(os.getpid(), signal.SIGHUP)
            await asyncio.sleep(0.5)  # let signal handler run

            assert "arxiv" in app.state.upstream_map
            assert "fetch" in app.state.upstream_map

    asyncio.run(scenario())


def test_hot_reload_invalid_yaml_keeps_old_config(tmp_path):
    """SIGHUP with broken YAML → old config preserved, error logged."""
    ...


def test_hot_reload_removes_deleted_upstream(tmp_path):
    ...
```