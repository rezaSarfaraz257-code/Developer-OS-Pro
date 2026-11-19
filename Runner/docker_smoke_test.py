import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = os.environ.get("RUNNER_SMOKE_URL", "http://127.0.0.1:18080").rstrip("/")
TOKEN = os.environ.get("RUNNER_SMOKE_TOKEN", "")


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(BASE_URL + path, data=data, headers=headers)
    with urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_ready():
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urlopen(BASE_URL + "/health/ready", timeout=2) as response:
                if response.status == 200:
                    return
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Runner did not become ready: {last_error}")


def main():
    if not TOKEN:
        raise RuntimeError("RUNNER_SMOKE_TOKEN is required")
    wait_ready()
    request("/sync", {"workspace_id": "902", "files": {"secret.txt": "workspace-private-marker"}})
    # Materialize workspace 902 under its own UID before checking isolation from 901.
    initialized = request("/exec", {
        "workspace_id": "902",
        "files": {"secret.txt": "workspace-private-marker"},
        "command": "chmod 755 . && chmod 644 secret.txt && test -f secret.txt",
    })
    if initialized.get("exit_code") != 0:
        raise AssertionError(f"Sibling workspace initialization failed: {initialized}")
    result = request("/exec", {
        "workspace_id": "901",
        "files": {"main.py": "print('container-smoke-ok')"},
        "command": (
            "id -u; id -g; "
            "grep -E '^(NoNewPrivs|CapEff|CapBnd):' /proc/self/status; "
            "if cat /proc/$PPID/environ >/dev/null 2>&1; then echo parent-env-readable; "
            "else echo parent-env-protected; fi; "
            "if cat ../902/secret.txt >/dev/null 2>&1; then echo sibling-readable; "
            "else echo sibling-protected; fi; "
            "cat main.py"
        ),
    })
    if result.get("exit_code") != 0:
        raise AssertionError(f"Runner command failed: {result}")
    output = result.get("stdout", "").splitlines()
    expected = [
        "10901",
        "10901",
        "CapEff:\t0000000000000000",
        "CapBnd:\t0000000000000000",
        "NoNewPrivs:\t1",
        "parent-env-protected",
        "sibling-protected",
        "print('container-smoke-ok')",
    ]
    if output != expected:
        raise AssertionError(f"Unexpected sandbox output: {output!r}")
    print("Runner container smoke test passed: unprivileged UID, empty capabilities, NNP, parent env and workspace isolation.")


if __name__ == "__main__":
    main()
