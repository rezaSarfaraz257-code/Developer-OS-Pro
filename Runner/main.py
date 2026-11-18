import hmac, os, re, subprocess, time, shutil, signal, threading, weakref, tempfile
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Developer OS Secure Workspace Runner")
ROOT = Path("/workspaces")
TOKEN = os.environ.get("IDE_RUNNER_TOKEN", "")
MAX_FILE = 1_000_000
MAX_FILES = 2_000
MAX_WORKSPACE_BYTES = 50_000_000
MAX_OUTPUT = 50_000
TIMEOUT = 120

# Serialize operations per workspace. A sync must never replace files while a
# command is executing against the same working directory.
_WORKSPACE_LOCKS = weakref.WeakValueDictionary()
_WORKSPACE_LOCKS_GUARD = threading.Lock()
MAX_CONCURRENT_EXECUTIONS = 4
EXECUTION_SLOT_WAIT_SECONDS = 5
EXECUTION_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_EXECUTIONS)

def workspace_lock(workspace_id):
    key = str(workspace_id)
    with _WORKSPACE_LOCKS_GUARD:
        return _WORKSPACE_LOCKS.setdefault(key, threading.RLock())

def clear_workspace(root):
    preserved = {".npm-cache", ".pip-cache", ".home", "node_modules", ".venv"}
    for child in root.iterdir():
        # Never follow a symlink, including one using a preserved cache name.
        if child.name in preserved and not child.is_symlink():
            continue
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            shutil.rmtree(child)
BLOCKED = [
    r"\b(docker|podman|nsenter|unshare|mount|umount|chroot)\b",
    r"(^|\s)rm\s+-rf\s+/$",
    r":\(\)\s*\{\s*:\|:\s*;\s*\}\s*;",
]

class Workspace(BaseModel):
    workspace_id: str
    files: dict[str, str] = Field(default_factory=dict)
    active_file: str = ""

class ExecRequest(Workspace):
    command: str = Field(min_length=1, max_length=2000)

class InstallRequest(ExecRequest):
    framework: str = ""
    package_manager: str = ""

def auth(value):
    if not TOKEN or not hmac.compare_digest(value, f"Bearer {TOKEN}"):
        raise HTTPException(status_code=401, detail="Unauthorized")

def safe_workspace(workspace_id):
    if not re.fullmatch(r"[0-9]+", str(workspace_id)):
        raise HTTPException(status_code=400, detail="Invalid workspace id")
    ROOT.mkdir(parents=True, exist_ok=True)
    base = ROOT.resolve()
    p = (base / str(workspace_id)).resolve()
    if not p.is_relative_to(base) or p == base:
        raise HTTPException(status_code=400, detail="Workspace path is outside the runner root")
    p.mkdir(parents=True, exist_ok=True)
    p = p.resolve()
    if not p.is_relative_to(base) or p == base:
        raise HTTPException(status_code=400, detail="Workspace path is outside the runner root")
    return p

def safe_rel(path):
    path = str(path).replace("\\", "/").lstrip("/")
    if not path or len(path) > 500 or path.startswith(".git/") or any(x in (".", "..", "") for x in path.split("/")):
        raise ValueError("unsafe path")
    return path

def _assert_inside_root(root, candidate):
    base = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base) or resolved == base:
        raise ValueError("workspace path escapes the workspace root")
    return resolved

def write_snapshot(root, files):
    root = root.resolve()
    if len(files) > MAX_FILES:
        raise ValueError(f"workspace exceeds {MAX_FILES} files")
    total = 0
    for rel, content in files.items():
        rel = safe_rel(rel)
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE:
            raise ValueError("file too large")
        total += len(content.encode())
        if total > MAX_WORKSPACE_BYTES:
            raise ValueError("workspace exceeds 50 MB source limit")
        target = _assert_inside_root(root, root / rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = _assert_inside_root(root, target)
        target.write_text(content, encoding="utf-8")

def snapshot(root):
    out = {}
    root = root.resolve()
    skip = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
    for p in root.rglob("*"):
        if p.is_symlink() or not p.is_file() or any(part in skip for part in p.relative_to(root).parts):
            continue
        try:
            _assert_inside_root(root, p)
            if p.stat().st_size > MAX_FILE:
                continue
            data = p.read_bytes()
            if b"\x00" in data:
                continue
            out[str(p.relative_to(root)).replace(os.sep, "/")] = data.decode("utf-8")
        except (OSError, ValueError):
            continue
    return out

def _tail_reader(stream, output):
    while True:
        chunk = stream.read(8192)
        if not chunk:
            break
        output.extend(chunk)
        if len(output) > MAX_OUTPUT:
            del output[:-MAX_OUTPUT]

def _tail_text(output):
    return bytes(output).decode("utf-8", errors="replace")

def _kill_process_group(proc):
    if proc is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            proc.kill()
        except OSError:
            pass

def _run_command_with_slot(root, command):
    if any(re.search(pattern, command, re.I) for pattern in BLOCKED):
        raise HTTPException(status_code=400, detail="Command blocked by sandbox policy.")
    root = root.resolve()
    home = root / ".home"
    temp = root / ".tmp"
    home.mkdir(exist_ok=True)
    temp.mkdir(exist_ok=True)
    env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(home),
        "TMPDIR": str(temp),
        "npm_config_cache": str(root / ".npm-cache"),
        "PIP_CACHE_DIR": str(root / ".pip-cache"),
        "PYTHONUNBUFFERED": "1",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "CI": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
    }
    started = time.monotonic()
    proc = None
    stdout_tail, stderr_tail = bytearray(), bytearray()
    readers = []
    timed_out = False
    orphaned_processes = False
    try:
        proc = subprocess.Popen(
            ["bash", "-c", command],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            close_fds=True,
            bufsize=0,
        )
        for stream, tail in ((proc.stdout, stdout_tail), (proc.stderr, stderr_tail)):
            reader = threading.Thread(target=_tail_reader, args=(stream, tail), daemon=True)
            reader.start()
            readers.append(reader)
        try:
            proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_group(proc)
            proc.wait()
        # Do not leave background children holding the output pipes open.
        for reader in readers:
            reader.join(timeout=1)
        if any(reader.is_alive() for reader in readers):
            orphaned_processes = True
            _kill_process_group(proc)
            for reader in readers:
                reader.join(timeout=2)
        return {
            "exit_code": 124 if timed_out else (125 if orphaned_processes else proc.returncode),
            "stdout": _tail_text(stdout_tail),
            "stderr": _tail_text(stderr_tail) or (f"Execution timed out after {TIMEOUT} seconds." if timed_out else ("Background child processes were terminated after the command exited." if orphaned_processes else "")),
            "duration_ms": int((time.monotonic()-started)*1000),
            "files": snapshot(root),
        }
    except Exception:
        if proc is not None and proc.poll() is None:
            _kill_process_group(proc)
            proc.wait()
        raise

def run_command(root, command):
    if not EXECUTION_SLOTS.acquire(timeout=EXECUTION_SLOT_WAIT_SECONDS):
        raise HTTPException(
            status_code=429,
            detail="Runner is at its concurrent execution limit. Retry shortly.",
            headers={"Retry-After": str(EXECUTION_SLOT_WAIT_SECONDS)},
        )
    try:
        return _run_command_with_slot(root, command)
    finally:
        EXECUTION_SLOTS.release()

@app.get("/health")
def health():
    # Liveness only: the process is responsive.
    return {"status": "ok"}

def runner_readiness():
    if not TOKEN:
        raise HTTPException(status_code=503, detail="Runner authentication is not configured")
    try:
        ROOT.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(ROOT).free < 64 * 1024 * 1024:
            raise HTTPException(status_code=503, detail="Runner workspace storage is below the safety threshold")
        with tempfile.NamedTemporaryFile(prefix=".runner-ready-", dir=ROOT):
            pass
    except HTTPException:
        raise
    except OSError:
        raise HTTPException(status_code=503, detail="Runner workspace storage is not writable")
    return {"status": "ready"}

@app.get("/health/ready")
def readiness():
    return runner_readiness()

@app.post("/sync")
def sync(payload: Workspace, authorization: str = Header(default="")):
    auth(authorization)
    with workspace_lock(payload.workspace_id):
        root = safe_workspace(payload.workspace_id)
        # Keep real dependency/cache directories, but replace source files.
        clear_workspace(root)
        write_snapshot(root, payload.files)
        return {"status": "synced", "files": snapshot(root)}

@app.post("/snapshot")
def get_snapshot(payload: Workspace, authorization: str = Header(default="")):
    auth(authorization)
    with workspace_lock(payload.workspace_id):
        return {"files": snapshot(safe_workspace(payload.workspace_id))}

@app.post("/install")
def install(payload: InstallRequest, authorization: str = Header(default="")):
    auth(authorization)
    with workspace_lock(payload.workspace_id):
        root = safe_workspace(payload.workspace_id)
        write_snapshot(root, payload.files)
        return run_command(root, payload.command)

@app.post("/exec")
def execute(payload: ExecRequest, authorization: str = Header(default="")):
    auth(authorization)
    with workspace_lock(payload.workspace_id):
        root = safe_workspace(payload.workspace_id)
        write_snapshot(root, payload.files)
        return run_command(root, payload.command)
