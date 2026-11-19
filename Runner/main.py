import hmac, os, re, subprocess, time, shutil, signal, threading, weakref, tempfile, sys, errno, ctypes.util, glob
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Developer OS Secure Workspace Runner")
ROOT = Path("/workspaces")
TOKEN = os.environ.get("IDE_RUNNER_TOKEN", "")
MAX_FILE = 1_000_000
MAX_FILES = 2_000
MAX_WORKSPACE_BYTES = 50_000_000
MAX_SNAPSHOT_ENTRIES = 10_000
MAX_OUTPUT = 50_000
TIMEOUT = 120
MAX_COMMAND_CPU_SECONDS = 125
MAX_COMMAND_FILE_BYTES = 256 * 1024 * 1024
MAX_COMMAND_OPEN_FILES = 256
# Reserve a unique, unprivileged Linux identity for every numeric workspace ID.
# Keeping the sum below INT32_MAX avoids platform-specific uid_t edge cases.
WORKSPACE_UID_BASE = 10_000
MAX_WORKSPACE_ID = 2_147_473_647

def command_argv(command, root, uid, gid):
    # The helper installs a kernel-enforced Landlock filesystem boundary before
    # dropping to the workspace-specific UID/GID and execing user-controlled code.
    helper = Path(__file__).with_name("sandbox_exec.py")
    return [sys.executable, str(helper), str(root.resolve()), str(uid), str(gid), command]

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

def find_nss_wrapper_library():
    """Resolve the distro NSS wrapper library even when it lacks an unversioned symlink."""
    patterns = (
        "/usr/lib/*/libnss_wrapper.so*",
        "/lib/*/libnss_wrapper.so*",
        "/usr/lib/libnss_wrapper.so*",
        "/lib/libnss_wrapper.so*",
    )
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            if os.path.isfile(candidate):
                return os.path.realpath(candidate)
    return ctypes.util.find_library("nss_wrapper")


def _secure_workspace_root():
    """Keep the shared parent root-owned and non-writable by command identities."""
    ROOT.mkdir(parents=True, exist_ok=True)
    if ROOT.is_symlink():
        raise HTTPException(status_code=503, detail="Runner workspace root must not be a symlink")
    base = ROOT.resolve(strict=True)
    if not base.is_dir():
        raise HTTPException(status_code=503, detail="Runner workspace root is not a directory")
    try:
        os.chown(base, 0, 0)
        base.chmod(0o755)
        subprocess.run(
            ["setfacl", "-b", "-k", str(base)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=503, detail="Runner workspace root permissions are unavailable") from exc
    return base


def safe_workspace(workspace_id):
    # Workspace identifiers are database IDs, not arbitrary path fragments.
    # Canonicalize them before deriving a filesystem path.
    raw_id = str(workspace_id)
    if not re.fullmatch(r"[1-9][0-9]{0,9}", raw_id) or int(raw_id) > MAX_WORKSPACE_ID:
        raise HTTPException(status_code=400, detail="Invalid workspace id")
    canonical_id = str(int(raw_id))
    base = _secure_workspace_root()
    candidate = base / canonical_id
    try:
        # Reject a pre-existing symlink rather than resolving through it.
        if candidate.is_symlink():
            raise HTTPException(status_code=400, detail="Workspace path is not a real directory")
        candidate.mkdir(mode=0o700, exist_ok=True)
        p = candidate.resolve(strict=True)
        if not p.is_relative_to(base) or p == base or p != candidate:
            raise HTTPException(status_code=400, detail="Workspace path is outside the runner root")
        if not p.is_dir():
            raise HTTPException(status_code=400, detail="Workspace path is not a directory")
        os.chown(p, 0, 0)
        p.chmod(0o700)
        return p
    except HTTPException:
        raise
    except OSError:
        raise HTTPException(status_code=400, detail="Workspace path is not available")

def safe_rel(path):
    path = str(path).replace("\\", "/").lstrip("/")
    parts = path.split("/")
    if (
        not path
        or len(path) > 500
        or "\x00" in path
        or any(part in (".", "..", "", ".git", ".home", ".tmp", ".npm-cache", ".pip-cache") for part in parts)
    ):
        raise ValueError("unsafe path")
    return path

def _assert_inside_root(root, candidate):
    base = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base) or resolved == base:
        raise ValueError("workspace path escapes the workspace root")
    return resolved

def _write_file_beneath(root, relative_path, content):
    """Write below root using directory descriptors and O_NOFOLLOW at every hop."""
    raw_parts = relative_path.split("/")
    parts = [os.path.basename(component) for component in raw_parts]
    if any(
        component != raw or component in ("", ".", "..") or "\x00" in component
        for component, raw in zip(parts, raw_parts)
    ):
        raise ValueError("unsafe workspace path component")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    root_fd = os.open(root, directory_flags)
    parent_fd = root_fd
    opened_fds = []
    try:
        for component in parts[:-1]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=parent_fd)  # lgtm [py/path-injection]
            except FileExistsError:
                pass
            next_fd = os.open(component, directory_flags, dir_fd=parent_fd)  # lgtm [py/path-injection]
            opened_fds.append(next_fd)
            parent_fd = next_fd
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW
        file_fd = os.open(parts[-1], file_flags, 0o600, dir_fd=parent_fd)  # lgtm [py/path-injection]
        try:
            view = memoryview(content)
            while view:
                written = os.write(file_fd, view)
                if written <= 0:
                    raise OSError(errno.EIO, "workspace file write made no progress")
                view = view[written:]
        finally:
            os.close(file_fd)
    finally:
        for descriptor in reversed(opened_fds):
            os.close(descriptor)
        os.close(root_fd)

def write_snapshot(root, files):
    root = root.resolve()
    if len(files) > MAX_FILES:
        raise ValueError(f"workspace exceeds {MAX_FILES} files")
    total = 0
    for rel, content in files.items():
        rel = safe_rel(rel)
        if not isinstance(content, str):
            raise ValueError("file content must be text")
        try:
            encoded = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("file content must be valid UTF-8 text") from exc
        if len(encoded) > MAX_FILE:
            raise ValueError("file too large")
        total += len(encoded)
        if total > MAX_WORKSPACE_BYTES:
            raise ValueError("workspace exceeds 50 MB source limit")
        # Resolve each component relative to an already-open directory and
        # reject symlinks atomically; resolve-then-write would leave a TOCTOU gap.
        try:
            _write_file_beneath(root, rel, encoded)
        except OSError as exc:
            raise ValueError("unsafe or unavailable workspace path") from exc

def snapshot(root):
    """Return a bounded UTF-8 source snapshot; fail rather than silently truncate."""
    out = {}
    root = root.resolve()
    skip = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".home", ".tmp", ".npm-cache", ".pip-cache"}
    total_bytes = 0
    visited_entries = 0
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories[:] = sorted(
            name for name in directories
            if name not in skip and not (current_path / name).is_symlink()
        )
        for name in directories:
            visited_entries += 1
            if visited_entries > MAX_SNAPSHOT_ENTRIES:
                raise HTTPException(status_code=413, detail="Workspace exceeds the snapshot entry limit")
        for name in sorted(files):
            path = current_path / name
            visited_entries += 1
            if visited_entries > MAX_SNAPSHOT_ENTRIES:
                raise HTTPException(status_code=413, detail="Workspace exceeds the snapshot entry limit")
            if path.is_symlink() or not path.is_file():
                continue
            try:
                _assert_inside_root(root, path)
                size = path.stat().st_size
                if size > MAX_FILE:
                    continue
                if len(out) >= MAX_FILES:
                    raise HTTPException(status_code=413, detail=f"Workspace exceeds {MAX_FILES} snapshot files")
                if total_bytes + size > MAX_WORKSPACE_BYTES:
                    raise HTTPException(status_code=413, detail="Workspace exceeds the 50 MB snapshot source limit")
                data = path.read_bytes()
                if b"\x00" in data:
                    continue
                try:
                    decoded = data.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                out[str(path.relative_to(root)).replace(os.sep, "/")] = decoded
                total_bytes += len(data)
            except HTTPException:
                raise
            except (OSError, ValueError):
                continue
    return out
def _tail_reader(stream, output):
    try:
        while True:
            chunk = stream.read(8192)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > MAX_OUTPUT:
                del output[:-MAX_OUTPUT]
    finally:
        stream.close()

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

def _terminate_remaining_process_group(proc):
    if proc is None:
        return False
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    except OSError:
        _kill_process_group(proc)
        return True
    # The shell has exited. Any remaining member is an orphaned command child.
    time.sleep(0.1)
    _kill_process_group(proc)
    return True

def workspace_identity(root):
    """Return the stable, unique unprivileged UID/GID assigned to a workspace."""
    raw_id = Path(root).name
    if not re.fullmatch(r"[1-9][0-9]{0,9}", raw_id):
        raise HTTPException(status_code=400, detail="Invalid workspace id")
    workspace_number = int(raw_id)
    if workspace_number > MAX_WORKSPACE_ID:
        raise HTTPException(status_code=400, detail="Invalid workspace id")
    identity = WORKSPACE_UID_BASE + workspace_number
    return identity, identity


def _prepare_workspace_for_execution(root, uid, gid):
    # Each workspace gets its own stable UID/GID. A shared nobody identity would
    # let one workspace process traverse every other workspace owned by nobody.
    # Make only this workspace accessible to its identity; never follow symlinks.
    root = root.resolve()
    # Keep the workspace root owned by root. A named POSIX ACL grants access
    # only to this workspace's UID; the command user cannot chmod or widen it.
    os.chown(root, 0, 0)
    root.chmod(0o700)
    try:
        subprocess.run(
            ["setfacl", "-b", "-k", str(root)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5,
        )
        acl = (
            f"u:{uid}:rwx,m::rwx,"
            f"d:u::rwx,d:u:{uid}:rwx,d:g::---,d:m::rwx,d:o::---"
        )
        subprocess.run(
            ["setfacl", "-m", acl, str(root)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=503, detail="Runner workspace ACL isolation is unavailable") from exc

    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_directories = []
        for name in directories:
            child = current_path / name
            if child.is_symlink():
                continue
            os.chown(child, uid, gid, follow_symlinks=False)
            child.chmod(0o700)
            safe_directories.append(name)
        directories[:] = safe_directories
        for name in files:
            child = current_path / name
            if not child.is_symlink():
                if current_path == root / ".home" and name in {"passwd", "group"}:
                    os.chown(child, 0, 0, follow_symlinks=False)
                    child.chmod(0o444)
                else:
                    os.chown(child, uid, gid, follow_symlinks=False)

def _run_command_with_slot(root, command):
    if any(re.search(pattern, command, re.I) for pattern in BLOCKED):
        raise HTTPException(status_code=400, detail="Command blocked by sandbox policy.")
    root = root.resolve()
    home = root / ".home"
    temp = root / ".tmp"
    for directory in (home, temp):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            if directory.is_dir() and not directory.is_symlink():
                shutil.rmtree(directory)
            else:
                directory.unlink()
        directory.mkdir(exist_ok=True)
    uid, gid = workspace_identity(root)
    passwd_path = home / "passwd"
    group_path = home / "group"
    for identity_file in (passwd_path, group_path):
        if identity_file.is_symlink() or identity_file.exists():
            if identity_file.is_dir() and not identity_file.is_symlink():
                shutil.rmtree(identity_file)
            else:
                identity_file.unlink()
    passwd_text = (
        "root:x:0:0:root:/root:/bin/bash\n"
        f"dos:x:{uid}:{gid}:Developer OS Workspace:{home}:/bin/bash\n"
        "nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n"
    )
    group_text = f"root:x:0:\ndos:x:{gid}:\nnogroup:x:65534:\n"
    _write_file_beneath(root, ".home/passwd", passwd_text.encode("utf-8"))
    _write_file_beneath(root, ".home/group", group_text.encode("utf-8"))
    _prepare_workspace_for_execution(root, uid, gid)
    runtime_paths = [
        "/opt/runner-venv/bin",
        "/usr/local/sbin",
        "/usr/local/bin",
        "/usr/sbin",
        "/usr/bin",
        "/sbin",
        "/bin",
    ]
    for executable in ("python", "python3", "node", "npm"):
        resolved = shutil.which(executable)
        if resolved:
            runtime_paths.insert(0, str(Path(resolved).parent))
    runtime_paths = list(dict.fromkeys(runtime_paths))
    env = {
        "PATH": os.pathsep.join(runtime_paths),
        "HOME": str(home),
        "USER": "dos",
        "LOGNAME": "dos",
        "SHELL": "/bin/bash",
        "NSS_WRAPPER_PASSWD": str(home / "passwd"),
        "NSS_WRAPPER_GROUP": str(home / "group"),
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
        # lgtm [py/command-line-injection]
        # Intentional execution boundary: user code is handed to the fixed sandbox
        # helper, which applies OS limits and drops to a workspace-only identity
        # before the shell receives it. The API server never executes this command.
        proc = subprocess.Popen(  # lgtm [py/command-line-injection]
            command_argv(command, root, uid, gid),
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
        if not timed_out and _terminate_remaining_process_group(proc):
            orphaned_processes = True
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
    if not shutil.which("setfacl"):
        raise HTTPException(status_code=503, detail="Runner POSIX ACL support is required")
    if not find_nss_wrapper_library():
        raise HTTPException(status_code=503, detail="Runner workspace identity compatibility library is required")
    try:
        _secure_workspace_root()
        with tempfile.TemporaryDirectory(prefix=".runner-acl-check-", dir=ROOT) as probe:
            uid = WORKSPACE_UID_BASE + 1
            acl = f"u:{uid}:rwx,m::rwx,d:u::rwx,d:u:{uid}:rwx,d:g::---,d:m::rwx,d:o::---"
            subprocess.run(
                ["setfacl", "-m", acl, probe],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=5,
            )
        if shutil.disk_usage(ROOT).free < 64 * 1024 * 1024:
            raise HTTPException(status_code=503, detail="Runner workspace storage is below the safety threshold")
        with tempfile.NamedTemporaryFile(prefix=".runner-ready-", dir=ROOT):
            pass
    except HTTPException:
        raise
    except subprocess.SubprocessError:
        raise HTTPException(status_code=503, detail="Runner workspace ACL isolation is unavailable")
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
