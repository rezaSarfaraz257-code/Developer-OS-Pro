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
    p = ROOT / str(workspace_id)
    p.mkdir(parents=True, exist_ok=True)
    return p

def safe_rel(path):
    path = str(path).replace("\\", "/").lstrip("/")
    if not path or len(path) > 500 or path.startswith(".git/") or any(x in (".", "..", "") for x in path.split("/")):
        raise ValueError("unsafe path")
    return path

def write_snapshot(root, files):
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
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

def snapshot(root):
    out = {}
    skip = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
    for p in root.rglob("*"):
        if not p.is_file() or any(part in skip for part in p.relative_to(root).parts):
            continue
        try:
            if p.stat().st_size > MAX_FILE:
                continue
            data = p.read_bytes()
            if b"\x00" in data:
                continue
            out[str(p.relative_to(root)).replace(os.sep, "/")] = data.decode("utf-8")
        except Exception:
            continue
    return out

def run_command(root, command):
    if any(re.search(pattern, command, re.I) for pattern in BLOCKED):
        raise HTTPException(status_code=400, detail="Command blocked by sandbox policy.")
    env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": str(root / ".home"),
        "npm_config_cache": str(root / ".npm-cache"),
        "PIP_CACHE_DIR": str(root / ".pip-cache"),
        "PYTHONUNBUFFERED": "1",
    }
    (root / ".home").mkdir(exist_ok=True)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            ["bash", "-lc", command], cwd=root, env=env,
            capture_output=True, text=True, timeout=TIMEOUT,
            start_new_session=True,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-MAX_OUTPUT:],
            "stderr": proc.stderr[-MAX_OUTPUT:],
            "duration_ms": int((time.monotonic()-started)*1000),
            "files": snapshot(root),
        }
    except subprocess.TimeoutExpired as exc:
        # Kill the entire process group so timed-out dev servers/child processes
        # cannot survive the request and consume the shared runner.
        try:
            os.killpg(proc.pid if "proc" in locals() else 0, signal.SIGKILL)
        except Exception:
            pass
        return {
            "exit_code": 124,
            "stdout": (exc.stdout or "")[-MAX_OUTPUT:] if isinstance(exc.stdout, str) else "",
            "stderr": "Execution timed out after 120 seconds.",
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
