import os
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

    def test_workspace_is_private_from_creation(self):
        with patch.object(main, "ROOT", self.root):
            workspace = main.safe_workspace("21")
        self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)

    def test_workspace_rejects_symlink_escape(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (self.root / "42").symlink_to(outside, target_is_directory=True)
        with patch.object(main, "ROOT", self.root):
            with self.assertRaises(HTTPException):
                main.safe_workspace("42")

    def test_workspace_id_must_be_a_canonical_positive_decimal(self):
        with patch.object(main, "ROOT", self.root):
            for invalid in ("0", "01", "-1", "../1", "1/2", "9" * 19, str(main.MAX_WORKSPACE_ID + 1)):
                with self.subTest(workspace_id=invalid):
                    with self.assertRaises(HTTPException):
                        main.safe_workspace(invalid)

    def test_workspace_rejects_symlink_root_without_following_it(self):
        outside = Path(self.temp.name) / "linked-outside"
        outside.mkdir()
        (self.root / "43").symlink_to(outside, target_is_directory=True)
        with patch.object(main, "ROOT", self.root):
            with self.assertRaises(HTTPException):
                main.safe_workspace("43")
        self.assertEqual(list(outside.iterdir()), [])

    def test_write_snapshot_rejects_symlink_parent_escape(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        workspace = self.root / "7"
        workspace.mkdir()
        (workspace / "linked").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            main.write_snapshot(workspace, {"linked/pwned.txt": "must not be written"})
        self.assertFalse((outside / "pwned.txt").exists())

    def test_write_snapshot_rejects_symlinked_file_target(self):
        outside = Path(self.temp.name) / "outside-file.txt"
        outside.write_text("keep this content", encoding="utf-8")
        workspace = self.root / "44"
        workspace.mkdir()
        (workspace / "linked.txt").symlink_to(outside)
        with self.assertRaises(ValueError):
            main.write_snapshot(workspace, {"linked.txt": "must not overwrite"})
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep this content")

    def test_write_snapshot_rejects_nul_and_nested_git_paths(self):
        workspace = self.root / "46"
        workspace.mkdir()
        for unsafe_path in ("bad\x00name.py", "src/.git/config"):
            with self.subTest(path=unsafe_path):
                with self.assertRaises(ValueError):
                    main.write_snapshot(workspace, {unsafe_path: "blocked"})
        self.assertFalse((workspace / "src").exists())

    def test_write_snapshot_rejects_invalid_utf8_surrogate_text(self):
        workspace = self.root / "47"
        workspace.mkdir()
        with self.assertRaises(ValueError):
            main.write_snapshot(workspace, {"source.py": "\ud800"})

    def test_write_snapshot_creates_nested_files_without_following_links(self):
        workspace = self.root / "45"
        workspace.mkdir()
        main.write_snapshot(workspace, {"src/nested/app.py": "print('safe')"})
        self.assertEqual(
            (workspace / "src" / "nested" / "app.py").read_text(encoding="utf-8"),
            "print('safe')",
        )

    def test_snapshot_rejects_too_many_source_files_instead_of_truncating(self):
        workspace = self.root / "17"
        workspace.mkdir()
        (workspace / "a.py").write_text("a", encoding="utf-8")
        (workspace / "b.py").write_text("b", encoding="utf-8")
        with patch.object(main, "MAX_FILES", 1):
            with self.assertRaises(HTTPException) as error:
                main.snapshot(workspace)
        self.assertEqual(error.exception.status_code, 413)

    def test_snapshot_rejects_total_source_bytes_over_limit(self):
        workspace = self.root / "18"
        workspace.mkdir()
        (workspace / "large.py").write_text("1234", encoding="utf-8")
        with patch.object(main, "MAX_WORKSPACE_BYTES", 3):
            with self.assertRaises(HTTPException) as error:
                main.snapshot(workspace)
        self.assertEqual(error.exception.status_code, 413)

    def test_snapshot_rejects_excessive_directory_entries(self):
        workspace = self.root / "19"
        workspace.mkdir()
        (workspace / "nested").mkdir()
        with patch.object(main, "MAX_SNAPSHOT_ENTRIES", 0):
            with self.assertRaises(HTTPException) as error:
                main.snapshot(workspace)
        self.assertEqual(error.exception.status_code, 413)
    def test_snapshot_ignores_binary_files_containing_nul_bytes(self):
        workspace = self.root / "20"
        workspace.mkdir()
        (workspace / "image.bin").write_bytes(b"header\x00payload")
        (workspace / "source.py").write_text("print(1)", encoding="utf-8")
        result = main.snapshot(workspace)
        self.assertNotIn("image.bin", result)
        self.assertEqual(result["source.py"], "print(1)")
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

    def test_detached_background_child_is_terminated_after_shell_exit(self):
        workspace = self.root / "13"
        workspace.mkdir()
        result = main.run_command(
            workspace,
            "sleep 5 >/dev/null 2>&1 & echo background-started",
        )
        self.assertEqual(result["exit_code"], 125)
        self.assertIn("background child processes were terminated", result["stderr"].lower())

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
        workspace = self.root / "31"
        workspace.mkdir()
        argv = main.command_argv(command, workspace, 10031, 10031)
        self.assertEqual(argv[-1], command)
        self.assertNotIn(command, argv[1])

    def test_command_runs_as_unprivileged_identity_with_no_new_privileges(self):
        workspace = self.root / "14"
        workspace.mkdir()
        command = "id -u; id -g; grep -E '^(NoNewPrivs|CapEff|CapBnd):' /proc/self/status"
        result = main.run_command(workspace, command)
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        lines = result["stdout"].splitlines()
        expected_uid, expected_gid = main.workspace_identity(workspace)
        self.assertEqual(lines[:2], [str(expected_uid), str(expected_gid)])
        status = {line.split(":")[0]: line.split()[1] for line in lines[2:]}
        self.assertEqual(status["NoNewPrivs"], "1")
        self.assertEqual(status["CapEff"], "0000000000000000")
        self.assertEqual(status["CapBnd"], "0000000000000000")

    def test_landlock_blocks_other_workspace_even_when_dac_permissions_are_open(self):
        with patch.object(main, "ROOT", self.root):
            first = main.safe_workspace("51")
            second = main.safe_workspace("52")
        prepare_first = main.run_command(
            first,
            "chmod 755 . && printf 'private-workspace-data' > secret.txt && chmod 644 secret.txt",
        )
        self.assertEqual(prepare_first["exit_code"], 0, prepare_first["stderr"])
        result = main.run_command(second, "cat ../51/secret.txt")
        self.assertNotEqual(result["exit_code"], 0)
        self.assertNotIn("private-workspace-data", result["stdout"])

    def test_command_cannot_read_runner_parent_environment(self):
        workspace = self.root / "16"
        workspace.mkdir()
        parent_pid = os.getpid()
        command = f"if cat /proc/{parent_pid}/environ >/dev/null 2>&1; then echo readable; else echo protected; fi"
        result = main.run_command(workspace, command)
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["stdout"].strip(), "protected")

    def test_command_cannot_access_another_workspace(self):
        with patch.object(main, "ROOT", self.root):
            first = main.safe_workspace("31")
            second = main.safe_workspace("32")
        (second / "secret.txt").write_text("private workspace data", encoding="utf-8")
        # Run in both workspaces so each directory is owned by its actual command UID.
        first_result = main.run_command(first, "echo first-workspace")
        second_result = main.run_command(second, "cat ../31/secret.txt")
        self.assertEqual(first_result["exit_code"], 0, first_result["stderr"])
        self.assertNotEqual(second_result["exit_code"], 0)
        self.assertNotIn("private workspace data", second_result["stdout"])
        self.assertNotEqual(main.workspace_identity(first), main.workspace_identity(second))

    def test_workspace_is_private_and_writable_by_command_identity(self):
        workspace = self.root / "15"
        workspace.mkdir()
        (workspace / "source.py").write_text("print('ok')", encoding="utf-8")
        result = main.run_command(workspace, "echo generated > generated.txt && cat generated.txt")
        self.assertEqual(result["exit_code"], 0, result["stderr"])
        self.assertEqual(result["stdout"].strip(), "generated")
        self.assertEqual((workspace / "generated.txt").stat().st_uid, 65534)
        self.assertEqual(workspace.stat().st_uid, 65534)
        self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)

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

    def test_readiness_requires_landlock_support(self):
        with patch.object(main, "TOKEN", "test-token"):
            with patch.object(main, "landlock_abi_version", return_value=0):
                with patch.object(main, "ROOT", self.root):
                    with self.assertRaises(HTTPException) as error:
                        main.runner_readiness()
        self.assertEqual(error.exception.status_code, 503)

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
