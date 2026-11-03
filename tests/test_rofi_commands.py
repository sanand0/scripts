"""Commands picker: dynamic panel entries, registry parsing and action routing."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "rofi" / "rofi-commands.py"
SPEC = importlib.util.spec_from_file_location("rofi_commands", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.registry = self.home / "commands.tsv"
        self.registry.write_text(
            "# label\tmode\tdirectory\tcommand\n"
            "Backup\tterminal\t~/code/scripts\t./backupwhatsapp.py\n"
            "Refresh\tbackground\t~/code/scripts\t./update-files\n"
        )
        self.previous_registry = MODULE.REGISTRY
        MODULE.REGISTRY = self.registry
        self.addCleanup(setattr, MODULE, "REGISTRY", self.previous_registry)

    def test_registry_is_extensible_and_handles_invalid_rows(self):
        self.registry.write_text(self.registry.read_text() + "Bad line\n")
        with patch("sys.stderr"):
            entries = MODULE.configured_items()
        self.assertEqual(["Backup", "Refresh"], [x.name for x in entries])
        self.assertEqual("terminal", entries[0].mode)
        self.assertEqual("./backupwhatsapp.py", entries[0].command)
        self.assertEqual("command:Backup", entries[0].key)

    def test_command_lookup_does_not_enumerate_panel(self):
        with patch.object(MODULE, "panel_items", side_effect=AssertionError("slow panel scan")):
            self.assertEqual("Backup", MODULE.find_item("command:Backup").name)

    def test_terminal_uses_canonical_vscode_action(self):
        (self.home / "code/scripts").mkdir(parents=True)
        item = MODULE.configured_items()[0]
        with patch.dict(os.environ, {"HOME": str(self.home)}), patch.object(MODULE.subprocess, "Popen") as popen:
            MODULE.activate(item)
        arguments = popen.call_args.args[0]
        self.assertEqual(str(SOURCE.parent / "rofi-files.sh"), arguments[0])
        self.assertEqual("--terminal", arguments[1])
        self.assertEqual(str(self.home / "code/scripts"), arguments[2])
        self.assertEqual("./backupwhatsapp.py", arguments[3])

    def test_background_command_has_workdir_and_log(self):
        (self.home / "code/scripts").mkdir(parents=True)
        with patch.dict(os.environ, {"HOME": str(self.home)}), patch.object(MODULE.subprocess, "Popen") as popen:
            MODULE.activate(MODULE.configured_items()[1])
        argv = popen.call_args.args[0]
        self.assertEqual(["bash", "-lc"], argv[:2])
        self.assertIn("cd -- ", argv[2])
        self.assertIn("&& ./update-files", argv[2])
        self.assertTrue((self.home / ".cache/sanand-scripts/rofi-commands.log").exists())

    def test_context_actions_for_panel_and_commands(self):
        p = MODULE.Item("System", "panel", 1700, 1170)
        with patch.object(MODULE, "find_item", return_value=p), patch.object(MODULE.subprocess, "run") as run, patch.object(MODULE, "activate") as activate:
            run.return_value.stdout = "1\n"
            MODULE.action_menu("panel:System")
            self.assertIn("Right-click", run.call_args.kwargs["input"])
            activate.assert_called_once_with(p, "right")
        cmd = MODULE.configured_items()[0]
        with patch.object(MODULE, "find_item", return_value=cmd), patch.object(MODULE.subprocess, "run") as run, patch.object(MODULE, "activate") as activate:
            run.return_value.stdout = "1\n"
            MODULE.action_menu("command:Backup")
            self.assertIn("Run in VS Code terminal", run.call_args.kwargs["input"])
            activate.assert_called_once_with(cmd, "terminal")

    def test_panel_click_uses_live_coordinates(self):
        item = MODULE.Item("Date and Time", "panel", 1650, 1180)
        with patch.object(MODULE.subprocess, "run") as run:
            MODULE.activate(item)
        self.assertEqual(["xdotool", "mousemove", "--sync", "1650", "1180", "click", "1"],
                         run.call_args.args[0])

    def test_script_lists_command_rows_without_gnome(self):
        env = dict(os.environ, ROFI_RETV="0", ROFI_COMMANDS_NO_PANEL="1")
        result = subprocess.run([str(SOURCE)], env=env, check=True, capture_output=True)
        self.assertIn(b"Command: Backup WhatsApp\x00info\x1fcommand:Backup WhatsApp", result.stdout)
        self.assertIn(b"Command: Refresh Rofi file index", result.stdout)
        self.assertNotIn(b"Panel:", result.stdout)


if __name__ == "__main__":
    unittest.main()
