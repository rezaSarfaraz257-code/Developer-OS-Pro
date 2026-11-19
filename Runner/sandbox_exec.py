"""Fail-closed Linux Landlock sandbox launcher for workspace commands.

The launcher installs filesystem rules before dropping to the workspace-specific
UID/GID. The restrictions survive exec and cannot be relaxed by the command.
"""
import ctypes
import errno
import os
import sys

SYS_LANDLOCK_CREATE_RULESET = 444
SYS_LANDLOCK_ADD_RULE = 445
SYS_LANDLOCK_RESTRICT_SELF = 446
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

# Landlock filesystem access rights, ABI 1.
EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
REMOVE_DIR = 1 << 4
REMOVE_FILE = 1 << 5
MAKE_CHAR = 1 << 6
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
MAKE_SOCK = 1 << 9
MAKE_FIFO = 1 << 10
MAKE_BLOCK = 1 << 11
MAKE_SYM = 1 << 12
REFER = 1 << 13
TRUNCATE = 1 << 14
IOCTL_DEV = 1 << 15

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.syscall.restype = ctypes.c_long
LIBC.prctl.restype = ctypes.c_int


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
        ("reserved", ctypes.c_uint32),
    ]


def _syscall(number, *args):
    result = LIBC.syscall(ctypes.c_long(number), *args)
    if result < 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))
    return int(result)


def landlock_abi_version():
    """Return the supported Landlock ABI, or raise when the kernel lacks it."""
    return _syscall(
        SYS_LANDLOCK_CREATE_RULESET,
        ctypes.c_void_p(),
        ctypes.c_size_t(0),
        ctypes.c_uint(LANDLOCK_CREATE_RULESET_VERSION),
    )


def _handled_access(abi):
    rights = (1 << 13) - 1
    if abi >= 2:
        rights |= REFER
    if abi >= 3:
        rights |= TRUNCATE
    if abi >= 5:
        rights |= IOCTL_DEV
    return rights


def _add_path_rule(ruleset_fd, path, allowed_access):
    if not os.path.exists(path):
        return
    path_fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    try:
        rule = PathBeneathAttr(allowed_access, path_fd, 0)
        _syscall(
            SYS_LANDLOCK_ADD_RULE,
            ctypes.c_int(ruleset_fd),
            ctypes.c_int(LANDLOCK_RULE_PATH_BENEATH),
            ctypes.byref(rule),
            ctypes.c_uint(0),
        )
    finally:
        os.close(path_fd)


def apply_workspace_landlock(workspace):
    """Allow full access only inside workspace and read/execute access to OS files."""
    abi = landlock_abi_version()
    handled = _handled_access(abi)
    ruleset_attr = RulesetAttr(handled)
    ruleset_fd = _syscall(
        SYS_LANDLOCK_CREATE_RULESET,
        ctypes.byref(ruleset_attr),
        ctypes.sizeof(ruleset_attr),
        ctypes.c_uint(0),
    )
    try:
        _add_path_rule(ruleset_fd, os.path.realpath(workspace), handled)

        system_read = EXECUTE | READ_FILE | READ_DIR
        for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/opt", "/etc", "/proc", "/sys", "/dev"):
            _add_path_rule(ruleset_fd, path, system_read)

        # Common harmless device output is needed by shell tools (for example,
        # redirection to /dev/null); no other device write access is granted.
        _add_path_rule(ruleset_fd, "/dev/null", READ_FILE | WRITE_FILE)

        if LIBC.prctl(
            ctypes.c_int(PR_SET_NO_NEW_PRIVS),
            ctypes.c_ulong(1),
            ctypes.c_ulong(0),
            ctypes.c_ulong(0),
            ctypes.c_ulong(0),
        ) != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, os.strerror(error_number))

        _syscall(SYS_LANDLOCK_RESTRICT_SELF, ctypes.c_int(ruleset_fd), ctypes.c_uint(0))
    finally:
        os.close(ruleset_fd)


def main():
    if len(sys.argv) != 5:
        raise SystemExit("sandbox launcher expects workspace, uid, gid and command")
    workspace, uid_text, gid_text, command = sys.argv[1:]
    uid, gid = int(uid_text), int(gid_text)
    apply_workspace_landlock(workspace)

    # Landlock is already enforced and survives this exec. setpriv drops every
    # capability and switches to the workspace's unique unprivileged identity.
    argv = [
        "setpriv",
        f"--reuid={uid}",
        f"--regid={gid}",
        "--clear-groups",
        "--bounding-set=-all",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--no-new-privs",
        "--",
        "/bin/bash",
        "-c",
        command,
    ]
    os.execvpe("setpriv", argv, os.environ.copy())


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        print(f"Runner filesystem sandbox unavailable: {exc}", file=sys.stderr)
        raise SystemExit(126)
