import os, re, subprocess, time, shutil, signal
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
    if not TOKEN or value != f"Bearer {TOKEN}":
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

def _bounded_output(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-MAX_OUTPUT:]

def run_command(root, command):
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
    try:
        proc = subprocess.Popen(
            ["bash", "-c", command],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            close_fds=True,
        )
        stdout, stderr = proc.communicate(timeout=TIMEOUT)
        return {
            "exit_code": proc.returncode,
            "stdout": _bounded_output(stdout),
            "stderr": _bounded_output(stderr),
            "duration_ms": int((time.monotonic()-started)*1000),
            "files": snapshot(root),
        }
    except subprocess.TimeoutExpired as exc:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                proc.kill()
        stdout, stderr = ("", "")
        if proc is not None:
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
        return {
            "exit_code": 124,
            "stdout": _bounded_output(stdout if stdout else exc.stdout),
            "stderr": _bounded_output(stderr if stderr else exc.stderr) or f"Execution timed out after {TIMEOUT} seconds.",
            "duration_ms": int((time.monotonic()-started)*1000),
            "files": snapshot(root),
        }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/sync")
def sync(payload: Workspace, authorization: str = Header(default="")):
    auth(authorization)
    root = safe_workspace(payload.workspace_id)
    # Keep dependency directories, but replace source tree so the database is the source of truth.
    for child in root.iterdir():
        if child.name not in {".npm-cache", ".pip-cache", ".home", "node_modules", ".venv"}:
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    write_snapshot(root, payload.files)
    return {"status": "synced", "files": snapshot(root)}

@app.post("/snapshot")
def get_snapshot(payload: Workspace, authorization: str = Header(default="")):
    auth(authorization)
    return {"files": snapshot(safe_workspace(payload.workspace_id))}

@app.post("/install")
def install(payload: InstallRequest, authorization: str = Header(default="")):
    auth(authorization)
    root = safe_workspace(payload.workspace_id)
    write_snapshot(root, payload.files)
    result = run_command(root, payload.command)
    return result

@app.post("/exec")
def execute(payload: ExecRequest, authorization: str = Header(default="")):
    auth(authorization)
    root = safe_workspace(payload.workspace_id)
    write_snapshot(root, payload.files)
    return run_command(root, payload.command)
