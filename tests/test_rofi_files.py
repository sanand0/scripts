"""Pure callback tests for the Rofi files/projects script (no GUI required)."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rofi-files.sh"


class RofiPickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / "code" / "exam" / ".git").mkdir(parents=True)
        (self.home / "code" / "exam" / "README.md").write_text("Hello exam\n")
        cache = self.home / ".cache" / "sanand-scripts"
        cache.mkdir(parents=True)
        (cache / "files._home.txt").write_text("code/exam/README.md\n")
        (cache / "frecent.txt").write_text("code/exam/README.md\n")
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        # Mock clipboard and spawned application without involving a GUI.
        (bin_dir / "xclip").write_text('#!/bin/sh\ncat > "$TEST_CLIP"\n')
        (bin_dir / "setsid").write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LAUNCH"\n')
        for path in bin_dir.iterdir():
            path.chmod(0o755)
        self.clip = self.home / "clipboard"
        self.launch = self.home / "launch.log"
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                        TEST_CLIP=str(self.clip), TEST_LAUNCH=str(self.launch))
        self.file = str(self.home / "code" / "exam" / "README.md")
        self.project = str(self.home / "code" / "exam")

    def run_picker(self, retv=0, data="", info="", selection=""):
        env = dict(self.env, ROFI_RETV=str(retv), ROFI_DATA=data, ROFI_INFO=info)
        return subprocess.run(["bash", str(SCRIPT), selection], env=env, capture_output=True, check=True).stdout

    def test_global_shows_projects_and_files(self):
        output = self.run_picker()
        self.assertIn(b"Project: exam\x00info\x1fproject:", output)
        self.assertIn(b"code/exam/README.md", output)
        self.assertIn(b"\x00data\x1fglobal", output)

    def test_any_modified_enter_shows_identical_file_actions(self):
        results = [self.run_picker(retv=n, info="code/exam/README.md") for n in range(10, 17)]
        self.assertTrue(all(x == results[0] for x in results))
        self.assertIn(b"\x00data\x1factions:file:", results[0])
        self.assertIn(b"Copy Git-relative path", results[0])

    def test_project_enter_opens_project_actions(self):
        result = self.run_picker(retv=1, info=f"project:{self.project}")
        self.assertIn(b"Browse project files", result)
        self.assertIn(b"Resume Codex session", result)

    def test_browse_then_file_actions_then_back(self):
        result = self.run_picker(retv=1, data=f"actions:project:{self.project}", info="browse")
        self.assertIn(b"\x00data\x1fbrowse:", result)
        self.assertIn(b"README.md", result)
        result = self.run_picker(retv=10, data=f"browse:{self.project}", info=f"file:{self.file}")
        self.assertIn(b"Open file in VS Code", result)
        result = self.run_picker(retv=1, data=f"browse:{self.project}", info="back")
        self.assertIn(b"Browse project files", result)

    def test_zoxide_frecency_prioritizes_projects(self):
        (self.home / "code" / "zeta" / ".git").mkdir(parents=True)
        zoxide = self.home / "bin" / "zoxide"
        zoxide.write_text('#!/bin/sh\nprintf "10 %s\\n3 %s\\n" "$HOME/code/zeta" "$HOME/code/exam"\n')
        zoxide.chmod(0o755)
        lines = self.run_picker().decode().split("\n")
        projects = [line for line in lines if line.startswith("Project:")]
        self.assertEqual(["Project: zeta", "Project: exam"], [line.split("\0")[0] for line in projects])

    def test_clipboard_and_relative_git_path(self):
        self.run_picker(retv=1, data=f"actions:file:{self.file}", info="copy-text")
        self.assertEqual("Hello exam\n", self.clip.read_text())
        self.run_picker(retv=1, data=f"actions:file:{self.file}", info="copy-path")
        self.assertEqual(self.file, self.clip.read_text())

    def test_open_preserves_default_action_and_remembers(self):
        self.run_picker(retv=1, info="code/exam/README.md")
        # Spawned command can finish after the picker callback exits.
        import time
        for _ in range(40):
            if self.launch.exists():
                break
            time.sleep(.01)
        self.assertIn("xdg-open", self.launch.read_text())
        recent = self.home / ".cache" / "sanand-scripts" / "frecent.txt"
        self.assertEqual("code/exam/README.md", recent.read_text().splitlines()[0])

    def test_missing_caches_and_spaces_are_safe(self):
        cache = self.home / ".cache" / "sanand-scripts"
        for path in cache.iterdir():
            path.unlink()
        result = self.run_picker()
        self.assertIn(b"Project: exam", result)
        p = self.home / "code" / "exam" / "file with spaces.md"
        p.write_text("abc")
        result = self.run_picker(retv=11, info=str(p))
        self.assertIn(b"Copy file contents", result)


if __name__ == "__main__":
    unittest.main()

