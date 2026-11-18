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


if __name__ == "__main__":
    unittest.main()
