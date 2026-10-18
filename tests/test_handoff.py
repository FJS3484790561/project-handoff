from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/project-handoff/scripts/handoff.py"
spec = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="handoff-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "家里 project"
        self.office = self.base / "公司 project"
        self.remote = self.base / "remote.git"
        self.home.mkdir()
        self.env = os.environ.copy()
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", PYTHONIOENCODING="utf-8")
        self.command(["git", "init", "--bare", "-b", "main", str(self.remote)])
        self.cli("init", self.home)
        self.identity(self.home)
        self.git(self.home, "remote", "add", "origin", str(self.remote))

    def command(self, args, success=True):
        result = subprocess.run(args, capture_output=True, env=self.env, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace") + result.stdout.decode("utf-8", "replace"))
        return result

    def git(self, root, *args):
        return self.command(["git", "-C", str(root), *args]).stdout.decode("utf-8").strip()

    def cli(self, action, root, *args, success=True):
        result = self.command([sys.executable, str(SCRIPT), action, "--project", str(root), *args], success=False)
        data = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(result.returncode == 0, success, data)
        self.assertEqual(data["ok"], success, data)
        return data

    def identity(self, root):
        self.git(root, "config", "user.name", "Test Developer")
        self.git(root, "config", "user.email", "test@example.invalid")
        self.git(root, "config", "core.autocrlf", "false")

    def files(self, root):
        result = self.command(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
        return list(dict.fromkeys(filter(None, result.stdout.decode("utf-8").split("\0"))))

    def status(self, root, text):
        (root / "docs/status.md").write_text("# Current state\n\n" + text + "\n", encoding="utf-8")

    def publish(self):
        self.status(self.home, "Initial requirements captured; tests not run.")
        result = self.cli("finish", self.home, "--message", "Initial handoff", "--files", *self.files(self.home))
        self.assertTrue(result["remote_verified"])
        self.assertTrue(result["complete"])
        return result

    def clone(self):
        self.command(["git", "clone", str(self.remote), str(self.office)])
        self.identity(self.office)

    def test_round_trip_between_two_computers(self):
        first = self.publish()
        self.clone()
        restored = self.cli("start", self.office)
        self.assertEqual(restored["head"], first["head"])
        (self.office / "登录 page.txt").write_text("login implemented\n", encoding="utf-8")
        self.status(self.office, "Login implemented. Next: refresh token. Tests not run.")
        second = self.cli("finish", self.office, "--message", "Login WIP", "--files", "登录 page.txt", "docs/status.md")
        resumed = self.cli("start", self.home)
        self.assertEqual(resumed["head"], second["head"])
        self.assertEqual((self.home / "登录 page.txt").read_text(), "login implemented\n")
        self.assertIn("refresh token", (self.home / "docs/status.md").read_text())

    def test_init_preserves_existing_docs_and_rules(self):
        root = self.base / "existing"
        root.mkdir()
        (root / "docs").mkdir()
        original = b"# Existing rules\r\nKeep this exact content."
        (root / "AGENTS.md").write_bytes(original)
        (root / "docs/product.md").write_text("Existing spec", encoding="utf-8")
        self.cli("init", root)
        once = (root / "AGENTS.md").read_bytes()
        self.assertTrue(once.startswith(original))
        self.cli("init", root)
        self.assertEqual((root / "AGENTS.md").read_bytes(), once)
        self.assertEqual((root / "docs/product.md").read_text(), "Existing spec")

    def test_dirty_start_does_not_overwrite(self):
        self.publish()
        self.status(self.home, "Unsaved local work")
        self.cli("start", self.home, success=False)
        self.assertIn("Unsaved local work", (self.home / "docs/status.md").read_text())

    def test_remote_ahead_rejects_finish_before_commit(self):
        before = self.publish()["head"]
        self.clone()
        self.status(self.office, "Office work")
        self.cli("finish", self.office, "--message", "Office", "--files", "docs/status.md")
        self.status(self.home, "Home uncommitted work")
        self.cli("finish", self.home, "--message", "Home", "--files", "docs/status.md", success=False)
        self.assertEqual(self.git(self.home, "rev-parse", "HEAD"), before)
        self.assertEqual(self.git(self.home, "diff", "--cached", "--name-only"), "")

    def test_divergence_preserves_both_histories(self):
        self.publish()
        self.clone()
        self.status(self.office, "Office commit")
        self.cli("finish", self.office, "--message", "Office", "--files", "docs/status.md")
        self.status(self.home, "Separate home commit")
        self.git(self.home, "add", "docs/status.md")
        self.git(self.home, "commit", "-m", "Local commit")
        before = self.git(self.home, "rev-parse", "HEAD")
        result = self.cli("start", self.home, success=False)
        self.assertIn("分叉", result["error"])
        self.assertEqual(self.git(self.home, "rev-parse", "HEAD"), before)

    def test_local_ahead_rejects_start(self):
        self.publish()
        self.status(self.home, "Local-only commit")
        self.git(self.home, "add", "docs/status.md")
        self.git(self.home, "commit", "-m", "Local")
        result = self.cli("start", self.home, success=False)
        self.assertIn("未推送", result["error"])

    def test_branch_mismatch_rejects(self):
        self.publish()
        self.git(self.home, "switch", "-c", "another")
        self.cli("start", self.home, success=False)
        self.cli("finish", self.home, success=False)
        self.assertEqual(self.git(self.home, "branch", "--show-current"), "another")

    def test_missing_status_update_blocks_new_commit(self):
        before = self.publish()["head"]
        (self.home / "feature.txt").write_text("new feature\n")
        result = self.cli("finish", self.home, "--message", "Feature", "--files", "feature.txt", success=False)
        self.assertIn("尚未更新", result["error"])
        self.assertEqual(self.git(self.home, "rev-parse", "HEAD"), before)
        self.assertEqual(self.git(self.home, "diff", "--cached", "--name-only"), "feature.txt")

    def test_push_failure_keeps_commit_then_retry_succeeds(self):
        first = self.publish()["head"]
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8", newline="\n")
        hook.chmod(0o755)
        self.status(self.home, "Work saved locally; awaiting push")
        result = self.cli("finish", self.home, "--message", "Saved", "--files", "docs/status.md", success=False)
        self.assertNotEqual(result["head"], first)
        self.assertEqual(self.git(self.remote, "rev-parse", "refs/heads/main"), first)
        hook.unlink()
        result = self.cli("finish", self.home)
        self.assertTrue(result["complete"])
        self.assertEqual(result["head"], self.git(self.remote, "rev-parse", "refs/heads/main"))

    def test_remaining_untracked_work_is_reported(self):
        self.publish()
        (self.home / "local-notes.txt").write_text("keep local\n")
        self.status(self.home, "Feature checkpoint")
        result = self.cli("finish", self.home, "--message", "Checkpoint", "--files", "docs/status.md")
        self.assertTrue(result["remote_verified"])
        self.assertFalse(result["complete"])
        self.assertIn("local-notes.txt", [x["path"] for x in result["remaining"]])

    def test_unselected_staging_is_preserved_and_blocks_commit(self):
        self.publish()
        (self.home / "unrelated.txt").write_text("other task\n")
        self.git(self.home, "add", "unrelated.txt")
        self.status(self.home, "Our task")
        self.cli("finish", self.home, "--message", "Checkpoint", "--files", "docs/status.md", success=False)
        self.assertEqual(self.git(self.home, "diff", "--cached", "--name-only"), "unrelated.txt")

    def test_environment_file_is_not_published(self):
        before = self.publish()["head"]
        (self.home / ".env").write_text("PASSWORD=test\n")
        self.status(self.home, "Updated")
        self.cli("finish", self.home, "--message", "Bad selection", "--files", ".env", "docs/status.md", success=False)
        self.assertEqual(self.git(self.remote, "rev-parse", "main"), before)

    def test_token_inside_arbitrary_file_is_not_published(self):
        before = self.publish()["head"]
        (self.home / "config.txt").write_text("token=" + "ghp_" + "a" * 36 + "\n")
        self.status(self.home, "Updated")
        result = self.cli("finish", self.home, "--message", "Bad selection", "--files", "config.txt", "docs/status.md", success=False)
        self.assertNotIn("a" * 36, json.dumps(result))
        self.assertEqual(self.git(self.remote, "rev-parse", "main"), before)

    def test_deletion_and_json_file_list(self):
        self.publish()
        (self.home / "old.txt").write_text("temporary\n")
        self.status(self.home, "Old file added")
        self.cli("finish", self.home, "--message", "Add", "--files", "old.txt", "docs/status.md")
        (self.home / "old.txt").unlink()
        self.status(self.home, "Old file removed")
        manifest = self.base / "selected.json"
        manifest.write_text(json.dumps(["old.txt", "docs/status.md"]), encoding="utf-8")
        self.cli("finish", self.home, "--message", "Remove", "--files-from", str(manifest))
        self.assertNotIn("old.txt", self.git(self.home, "ls-tree", "--name-only", "HEAD"))

    def test_paths_cannot_escape_or_select_entire_directory(self):
        self.publish()
        (self.base / "outside.txt").write_text("outside\n")
        for value in ("../outside.txt", ".", "docs", str(self.base / "outside.txt"), ".git/config"):
            with self.subTest(value=value):
                self.cli("finish", self.home, "--message", "Invalid", "--files", value, success=False)
        self.assertEqual(self.git(self.home, "status", "--porcelain"), "")

    def test_ignored_documents_block_initialization(self):
        root = self.base / "ignored"
        root.mkdir()
        (root / ".gitignore").write_text("docs/\n")
        result = self.cli("init", root, success=False)
        self.assertIn("忽略", result["error"])
        self.assertFalse((root / ".handoff.json").exists())

    def test_initialization_rejects_nested_project(self):
        child = self.home / "nested"
        child.mkdir()
        self.cli("init", child, success=False)
        self.assertFalse((child / ".handoff.json").exists())

    def test_inspect_is_read_only_without_remote_access(self):
        self.publish()
        self.git(self.home, "remote", "set-url", "origin", str(self.base / "missing.git"))
        result = self.cli("inspect", self.home)
        self.assertFalse(result["remote_checked"])
        self.assertEqual(result["changes"], [])

    def test_remote_unavailable_does_not_commit(self):
        before = self.publish()["head"]
        self.git(self.home, "remote", "set-url", "origin", str(self.base / "missing.git"))
        self.status(self.home, "Not yet pushed")
        self.cli("finish", self.home, "--message", "Offline", "--files", "docs/status.md", success=False)
        self.assertEqual(self.git(self.home, "rev-parse", "HEAD"), before)
        self.assertEqual(self.git(self.home, "diff", "--cached", "--name-only"), "")

    def test_installer_is_repeatable_and_backs_up_updates(self):
        target = self.base / "installed skills"
        installer.install(ROOT, target, False)
        second = installer.install(ROOT, target, False)
        self.assertTrue(all(x["status"] == "unchanged" for x in second))
        path = target / "brainstorm-lite/SKILL.md"
        original = path.read_bytes()
        path.write_bytes(b"User modified skill")
        with self.assertRaises(ValueError):
            installer.install(ROOT, target, False)
        result = installer.install(ROOT, target, True)
        backup = next(Path(x["backup"]) for x in result if x.get("backup"))
        self.assertEqual((backup / "SKILL.md").read_bytes(), b"User modified skill")
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
