import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

import main


class WorkspaceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspaces"
        self.root.mkdir()
        self.addCleanup(self.temp.cleanup)

    def test_workspace_rejects_symlink_escape(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "42").symlink_to(outside, target_is_directory=True)
        with patch.object(main, "ROOT", self.root):
            with self.assertRaises(HTTPException):
                main.safe_workspace("42")

    def test_write_snapshot_rejects_symlink_parent_escape(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        workspace = self.root / "7"
        workspace.mkdir()
        (workspace / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            main.write_snapshot(workspace, {"linked/pwned.txt": "must not be written"})
        self.assertFalse((outside / "pwned.txt").exists())

    def test_snapshot_ignores_symlinked_files(self):
        outside = Path(self.temp.name) / "secret.txt"
        outside.write_text("private", encoding="utf-8")
        workspace = self.root / "8"
        workspace.mkdir()
        (workspace / "leak.txt").symlink_to(outside)
        self.assertNotIn("leak.txt", main.snapshot(workspace))

    def test_timed_out_command_kills_only_its_process_group(self):
        workspace = self.root / "9"
        workspace.mkdir()
        with patch.object(main, "TIMEOUT", 0.1):
            result = main.run_command(workspace, "sleep 5 & wait")
        self.assertEqual(result["exit_code"], 124)
        self.assertIn("timed out", result["stderr"].lower())

    def test_command_output_is_bounded_while_streaming(self):
        workspace = self.root / "10"
        workspace.mkdir()
        result = main.run_command(workspace, "python3 -c \"print('x' * 100000)\"")
        self.assertEqual(result["exit_code"], 0)
        self.assertLessEqual(len(result["stdout"]), main.MAX_OUTPUT)
        self.assertTrue(result["stdout"].endswith("\n"))

    def test_command_inherits_cpu_file_descriptor_and_core_limits(self):
        workspace = self.root / "12"
        workspace.mkdir()
        command = (
            "python3 -c 'import resource; "
            "print(resource.getrlimit(resource.RLIMIT_CPU)[0]); "
            "print(resource.getrlimit(resource.RLIMIT_FSIZE)[0]); "
            "print(resource.getrlimit(resource.RLIMIT_NOFILE)[0]); "
            "print(resource.getrlimit(resource.RLIMIT_CORE)[0])'"
        )
        result = main.run_command(workspace, command)
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(
            result["stdout"].splitlines(),
            [
                str(main.MAX_COMMAND_CPU_SECONDS),
                str(main.MAX_COMMAND_FILE_BYTES),
                str(main.MAX_COMMAND_OPEN_FILES),
                "0",
            ],
        )

    def test_command_is_passed_as_argument_not_bootstrap_interpolation(self):
        command = "printf '%s' '$(touch should-not-exist)'"
        argv = main.command_argv(command)
        self.assertEqual(argv[-1], command)
        self.assertNotIn(command, argv[2])

    def test_sync_cleanup_unlinks_symlinks_instead_of_following_them(self):
        workspace = self.root / "11"
        workspace.mkdir()
        outside = Path(self.temp.name) / "outside-cache"
        outside.mkdir()
        protected = outside / "keep.txt"
        protected.write_text("do not delete", encoding="utf-8")
        (workspace / "node_modules").symlink_to(outside, target_is_directory=True)
        (workspace / "source.txt").write_text("old", encoding="utf-8")

        main.clear_workspace(workspace)

        self.assertFalse((workspace / "node_modules").exists())
        self.assertFalse((workspace / "source.txt").exists())
        self.assertEqual(protected.read_text(encoding="utf-8"), "do not delete")

    def test_workspace_lock_is_shared_for_the_same_workspace(self):
        first = main.workspace_lock("123")
        second = main.workspace_lock("123")
        other = main.workspace_lock("124")
        self.assertIs(first, second)
        self.assertIsNot(first, other)

    def test_execution_limit_returns_retryable_429(self):
        with patch.object(main, "EXECUTION_SLOTS", __import__("threading").BoundedSemaphore(0)):
            with patch.object(main, "_run_command_with_slot") as execute:
                with patch.object(main, "EXECUTION_SLOT_WAIT_SECONDS", 0.01):
                    with self.assertRaises(HTTPException) as error:
                        main.run_command(self.root, "echo blocked")
        self.assertEqual(error.exception.status_code, 429)
        self.assertEqual(error.exception.headers["Retry-After"], "0.01")
        execute.assert_not_called()

    def test_readiness_requires_runner_token(self):
        with patch.object(main, "TOKEN", ""):
            with patch.object(main, "ROOT", self.root):
                with self.assertRaises(HTTPException) as error:
                    main.runner_readiness()
        self.assertEqual(error.exception.status_code, 503)

    def test_readiness_checks_workspace_volume_write_access(self):
        with patch.object(main, "TOKEN", "test-token"):
            with patch.object(main, "ROOT", self.root):
                self.assertEqual(main.runner_readiness(), {"status": "ready"})


if __name__ == "__main__":
    unittest.main()
