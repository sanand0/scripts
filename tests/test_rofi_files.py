"""Test fast Rofi routing, file/directory actions, and VS Code terminal commands."""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "rofi" / "rofi-files.sh"


class RofiPickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.directory = self.home / "code" / "exam"
        subprocess.run(["git", "init", "-q", str(self.directory)], check=True)
        self.file = self.directory / "README.md"
        self.file.write_text("Hello exam\n")
        cache = self.home / ".cache" / "sanand-scripts"
        cache.mkdir(parents=True)
        (cache / "files._home.txt").write_text("code/exam/README.md\n")
        (cache / "frecent.txt").write_text("code/exam/README.md\n")
        bindir = self.home / "bin"
        bindir.mkdir()
        stubs = {
            "setsid": '#!/bin/bash\nprintf "%s\\n" "$*" >> "$TEST_LAUNCH"\n',
            "xclip": '#!/bin/bash\ncat > "$TEST_CLIP"\n',
            "rofi": '#!/bin/bash\nprintf "%s\\n" "$*" >> "$TEST_LAUNCH"\ncat > "$TEST_MENU"\nprintf "%s\\n" "$TEST_PICK"\n',
            "xprop": '#!/bin/bash\nprintf \'WM_CLASS(STRING) = "code", "Code"\\n\'\n',
            "xdotool": '#!/bin/bash\nprintf "xdotool %s\\n" "$*" >> "$TEST_LAUNCH"\ncase "$1" in getactivewindow) echo 123;; search) echo 123;; esac\n',
            "notify-send": "#!/bin/bash\nexit 0\n",
        }
        for name, content in stubs.items():
            p = bindir / name
            p.write_text(content)
            p.chmod(0o755)
        self.clip = self.home / "clip"
        self.log = self.home / "log"
        self.menu = self.home / "menu"
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            PATH=f"{bindir}:{os.environ['PATH']}",
            TEST_CLIP=str(self.clip),
            TEST_LAUNCH=str(self.log),
            TEST_MENU=str(self.menu),
            TEST_PICK="0",
            ROFI_SOURCE_WINDOW="123",
        )

    def picker(self, *args, retv=0, info="", env=None):
        settings = dict(self.env, ROFI_RETV=str(retv), ROFI_INFO=info)
        if env:
            settings.update(env)
        return subprocess.run(
            ["bash", str(SCRIPT), *map(str, args)],
            env=settings, capture_output=True, check=True
        ).stdout

    def log_text(self):
        for _ in range(30):
            if self.log.exists():
                break
            time.sleep(.01)
        return self.log.read_text() if self.log.exists() else ""

    def test_file_and_directory_providers_are_independent(self):
        files = self.picker()
        directories = self.picker(env={"ROFI_PROVIDER": "directories"})
        self.assertIn(b"code/exam/README.md", files)
        self.assertNotIn(b"Directory: code/exam", files)
        self.assertIn(b"Directory: code/exam\x00info\x1fdirectory:", directories)
        self.assertNotIn(b"code/exam/README.md", directories)

    def test_directory_wrapper_lists_only_directories(self):
        wrapper = SCRIPT.parent / "rofi-directories.sh"
        output = subprocess.run(["sh", str(wrapper)], env=dict(self.env, ROFI_RETV="0"),
                                check=True, capture_output=True).stdout
        self.assertIn(b"Directory: code/exam", output)
        self.assertNotIn(b"code/exam/README.md", output)

    def test_browser_list_uses_compact_rofi_info_rows(self):
        script = SCRIPT.parent / "rofi-chrome-tabs.sh"
        edge = self.home / "code" / "scripts" / "edge"
        edge.parent.mkdir(parents=True, exist_ok=True)
        edge.write_text('#!/bin/sh\nprintf \'{"windows":[{"tabs":[{"cdp_id":"abc123","url":"https://example.com/a","title":"Hello"}]}]}\\n\'\n')
        edge.chmod(0o755)
        output = subprocess.run(["bash", str(script)], env=dict(self.env, ROFI_RETV="0"),
                                check=True, capture_output=True).stdout
        self.assertIn(b"example.com  Hello\x00info\x1fabc123\n", output)
        self.assertNotIn(b"\\u0000info", output)

    def test_recent_paths_keep_exact_spaces(self):
        recent = self.home / ".cache/sanand-scripts/frecent.txt"
        recent.write_text("Documents/books/A  B.epub\n" + recent.read_text())
        self.assertIn(b"Documents/books/A  B.epub\n", self.picker())

    def test_modified_enter_opens_separate_menu_not_combined_results(self):
        for retv in range(10, 17):
            self.log.unlink(missing_ok=True)
            result = self.picker(retv=retv, info="code/exam/README.md")
            self.assertEqual(b"", result)
            self.assertIn("--menu file", self.log_text())

    def test_directory_enter_opens_file_manager(self):
        self.picker(retv=1, info=f"directory:{self.directory}")
        self.assertIn(f"xdg-open {self.directory}", self.log_text())

    def test_action_dismisses_only_its_own_picker(self):
        process = subprocess.Popen(["sleep", "20"])
        pidfile = self.home / "picker.pid"
        pidfile.write_text(f"{process.pid}\n")
        try:
            self.picker(retv=11, info=f"directory:{self.directory}",
                        env={"ROFI_PICKER_PIDFILE": str(pidfile)})
            self.assertEqual(-15, process.wait(timeout=2))
            self.assertIn("--menu directory", self.log_text())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=2)

    def test_back_action_reopens_top_level_picker(self):
        for kind, path, letter in (("directory", self.directory, "d"),
                                   ("file", self.file, "f")):
            self.log.unlink(missing_ok=True)
            self.picker("--menu", kind, path, env={"TEST_PICK": "11"})
            expected = f"/rofi/../rofi-picker {letter}"
            for _ in range(50):
                if expected in self.log_text():
                    break
                time.sleep(.01)
            self.assertIn(expected, self.log_text())

    def test_directory_menu_contains_commands(self):
        self.picker("--menu", "directory", self.directory, env={"TEST_PICK": "1"})
        choices = self.menu.read_text()
        self.assertIn("Browse directory files", choices)
        self.assertIn("Resume Codex (VS Code terminal)", choices)
        self.assertIn("-dmenu", self.log_text())

    def test_non_git_directory_hides_git_actions(self):
        folder = self.home / "Documents" / "Notes"
        folder.mkdir(parents=True)
        self.picker("--menu", "directory", folder, env={"TEST_PICK": "4"})
        choices = self.menu.read_text()
        self.assertIn("Open in Files", choices)
        self.assertIn("Browse directory files", choices)
        self.assertNotIn("Git status", choices)
        self.assertEqual(str(folder), self.clip.read_text())

    def test_direct_shortcuts_reuse_dispatcher(self):
        dconf = (SCRIPT.parent.parent / "setup/media-keys.dconf").read_text()
        self.assertIn("command='/home/sanand/code/scripts/rofi-picker p'", dconf)
        self.assertIn("command='/home/sanand/code/scripts/rofi-picker m'", dconf)

    def test_cli_command_uses_existing_vscode_terminal(self):
        self.picker("--terminal", self.directory, "./backupwhatsapp.py")
        log = self.log_text()
        self.assertIn(f"cd -- {self.directory} && ./backupwhatsapp.py", log)
        self.assertIn("ctrl+alt+shift+F12", log)
        self.assertNotIn("gnome-terminal", log)

    def test_directory_git_status_types_actual_shell_command(self):
        self.picker("--menu", "directory", self.directory, env={"TEST_PICK": "5"})
        log = self.log_text()
        self.assertIn("xdotool windowactivate --sync 123", log)
        self.assertIn("xdotool key --clearmodifiers ctrl+alt+shift+F12", log)
        self.assertIn(f"xdotool type --clearmodifiers --delay 0 -- cd -- {self.directory} && git status", log)
        self.assertIn("xdotool key --clearmodifiers Return", log)
        self.assertNotIn("ctrl+alt+shift+F11", log)
        self.assertNotIn("ctrl+shift+p", log)
        self.assertNotIn("gnome-terminal", log)
        self.assertFalse((self.home / ".cache/sanand-scripts/rofi-vscode-command.fish").exists())

    def test_directory_path_with_spaces_is_escaped(self):
        directory = self.home / "code" / "a b"
        subprocess.run(["git", "init", "-q", str(directory)], check=True)
        self.picker("--menu", "directory", directory, env={"TEST_PICK": "5"})
        self.assertIn("a\\ b && git status", self.log_text())

    def test_file_menu_copies_file_contents(self):
        self.picker("--menu", "file", self.file, env={"TEST_PICK": "7"})
        self.assertEqual("Hello exam\n", self.clip.read_text())

    def test_menu_open_matches_direct_open_for_music(self):
        music = self.home / "Music" / "song.mp3"
        music.parent.mkdir()
        music.write_bytes(b"music")
        self.picker("--menu", "file", music, env={"TEST_PICK": "0"})
        expected = f"play-music {music}"
        for _ in range(40):
            if expected in self.log_text():
                break
            time.sleep(.01)
        self.assertIn(expected, self.log_text())

    def test_zoxide_frecency_orders_directories(self):
        (self.home / "code" / "zeta").mkdir(parents=True)
        z = self.home / "bin" / "zoxide"
        z.write_text('#!/bin/sh\nprintf "10 %s\\n3 %s\\n" "$HOME/code/zeta" "$HOME/code/exam"\n')
        z.chmod(0o755)
        lines = self.picker(env={"ROFI_PROVIDER": "directories"}).decode().splitlines()
        directories = [line.split("\0")[0] for line in lines if line.startswith("Directory:")]
        self.assertEqual(["Directory: code/zeta", "Directory: code/exam"], directories[:2])

    def test_launcher_shows_all_labels_with_single_key_shortcuts(self):
        launcher = (SCRIPT.parent.parent / "rofi-picker").read_text()
        for key, label in (("f", "Files"), ("w", "Windows"), ("d", "Directories"),
                           ("b", "Browser tabs"), ("t", "Tabs (alias)"),
                           ("p", "Prompts"), ("m", "Transformations"),
                           ("c", "Commands")):
            self.assertIn(f"'{key} {label}'", launcher)
            self.assertNotIn(f"{key}\\0display", launcher)
        for index, key in enumerate("fwdbtpmc", 1):
            self.assertIn(f"-kb-custom-{index} {key}", launcher)
        self.assertIn('eval "$(mise env -s bash)"', launcher)
        self.assertNotIn("-show combi", launcher)
        self.assertIn('p) exec "$dir/prompt"', launcher)
        self.assertIn('m) exec "$rofi_dir/rofi-clip.sh"', launcher)
        self.assertIn('c) script="$rofi_dir/rofi-commands.py"', launcher)
        self.assertIn('-kb-custom-1 "Control+Return,Alt+Return"', launcher)
        self.assertIn('-kb-accept-alt "Control+Return,Alt+Return"', launcher)

    def test_selector_dispatches_all_keys_and_shows_readable_labels(self):
        sandbox = self.home / "launcher"
        sandbox.mkdir()
        (sandbox / "rofi").mkdir()
        launcher = sandbox / "rofi-picker"
        launcher.write_text((SCRIPT.parent.parent / "rofi-picker").read_text())
        (self.home / "bin/mise").write_text("#!/bin/sh\nexit 0\n")
        (self.home / "bin/mise").chmod(0o755)
        first_menu = self.home / "first-menu"
        (self.home / "bin/rofi").write_text(
            '#!/bin/bash\n'
            'if [[ "$1" == "-dmenu" ]]; then\n'
            '    cat > "$TEST_FIRST_MENU"\n'
            '    if [[ "$TEST_SELECTOR_EXIT" == "0" ]]; then\n'
            '        printf "%s\\n" "$TEST_SELECTOR_ROW"\n'
            '    fi\n'
            '    exit "$TEST_SELECTOR_EXIT"\n'
            'fi\n'
            'printf "rofi %s\\n" "$*" >> "$TEST_LAUNCH"\n'
        )
        for name in ("prompt", "rofi-clip.sh"):
            file = (sandbox / "rofi" / name if name.startswith("rofi-")
                    else sandbox / name)
            file.write_text('#!/bin/sh\necho ' + name + ' >> "$TEST_LAUNCH"\n')
            file.chmod(0o755)
        expected = ("-show f", "-show window", "-show d", "-show b",
                    "-show t", "prompt", "rofi-clip.sh", "-show c")
        for status, command in zip(range(10, 18), expected):
            self.log.unlink(missing_ok=True)
            settings = dict(self.env, TEST_SELECTOR_EXIT=str(status),
                            TEST_FIRST_MENU=str(first_menu))
            subprocess.run(["bash", str(launcher)], env=settings,
                           check=True, capture_output=True)
            self.assertIn(command, self.log.read_text(), f"selector exit {status}")
        labels = first_menu.read_text()
        self.assertIn("f Files", labels)
        self.assertIn("b Browser tabs", labels)
        self.assertIn("m Transformations", labels)
        self.assertIn("c Commands", labels)
        self.log.unlink()
        settings = dict(self.env, TEST_SELECTOR_EXIT="0",
                        TEST_SELECTOR_ROW="d Directories", TEST_FIRST_MENU=str(first_menu))
        subprocess.run(["bash", str(launcher)], env=settings,
                       check=True, capture_output=True)
        self.assertIn("-show d", self.log.read_text())

    def test_desktop_shortcut_path_initializes_zoxide_before_directory_picker(self):
        # The GNOME shortcut does not inherit fish's mise PATH; simulate that.
        desktop = self.home / "desktop-bin"
        hidden = self.home / "mise-bin"
        desktop.mkdir()
        hidden.mkdir()
        (self.home / "Downloads").mkdir()
        (hidden / "zoxide").write_text(
            '#!/bin/sh\nprintf "10 %s\\n" "$HOME/Downloads"\n'
        )
        (desktop / "mise").write_text(
            '#!/bin/sh\nprintf \'export PATH="%s:$PATH"\\n\' "$TEST_MISE_BIN"\n'
        )
        (desktop / "rofi").write_text(
            '#!/bin/bash\nROFI_RETV=0 ROFI_PROVIDER=directories '
            '"$TEST_SOURCE_SCRIPT" > "$TEST_PROVIDER_OUTPUT"\n'
        )
        (desktop / "xdotool").write_text(
            '#!/bin/sh\necho 123\n'
        )
        for tool in (hidden / "zoxide", desktop / "mise",
                     desktop / "rofi", desktop / "xdotool"):
            tool.chmod(0o755)
        output = self.home / "provider.txt"
        settings = dict(self.env, PATH=f"{desktop}:/usr/bin:/bin",
                        TEST_MISE_BIN=str(hidden),
                        TEST_SOURCE_SCRIPT=str(SCRIPT),
                        TEST_PROVIDER_OUTPUT=str(output))
        subprocess.run(["bash", str(SCRIPT.parent.parent / "rofi-picker"), "d"],
                       env=settings, capture_output=True, check=True)
        listing = output.read_text()
        self.assertIn("Directory: Downloads", listing)
        self.assertIn("Directory: code/exam", listing)

    def test_browser_modified_enter_opens_tab_actions(self):
        script = SCRIPT.parent / "rofi-chrome-tabs.sh"
        subprocess.run(["bash", str(script), "example.com  Example 🔑tab123"],
                       env=dict(self.env, ROFI_RETV="11", ROFI_PICKER_PIDFILE=""),
                       check=True, capture_output=True)
        self.assertIn("--actions tab123", self.log_text())

    def test_browser_actions_copy_url(self):
        script = SCRIPT.parent / "rofi-chrome-tabs.sh"
        curl = self.home / "bin" / "curl"
        curl.write_text('#!/bin/sh\nprintf \'[{"id":"tab123","url":"https://example.com/a","title":"Example"}]\\n\'\n')
        curl.chmod(0o755)
        subprocess.run(["bash", str(script), "--actions", "tab123"],
                       env=dict(self.env, TEST_PICK="1"), check=True, capture_output=True)
        self.assertEqual("https://example.com/a\n", self.clip.read_text())

    def test_window_actions_copy_id(self):
        script = SCRIPT.parent / "rofi-window-actions.sh"
        subprocess.run(["bash", str(script), "0x123"], env=dict(self.env, TEST_PICK="2"),
                       check=True, capture_output=True)
        self.assertEqual("0x123", self.clip.read_text())

    def test_home_shorthand_in_selected_path(self):
        notes = self.home / "Documents" / "Notes"
        notes.mkdir(parents=True)
        target = notes / "hello.md"
        target.write_text("hello")
        self.picker(retv=1, info="~/Documents/Notes/hello.md")
        self.assertIn(f"xdg-open {target}", self.log_text())

    def test_file_open_unchanged(self):
        self.picker(retv=1, info="code/exam/README.md")
        self.assertIn(f"xdg-open {self.file}", self.log_text())
        self.assertEqual("code/exam/README.md",
                         (self.home / ".cache/sanand-scripts/frecent.txt").read_text().splitlines()[0])

    def test_missing_cache_and_spaces(self):
        for p in (self.home / ".cache/sanand-scripts").iterdir():
            p.unlink()
        self.assertIn(b"Directory: code/exam", self.picker(env={"ROFI_PROVIDER": "directories"}))
        path = self.directory / "file with spaces.md"
        path.write_text("hi")
        self.picker(retv=11, info=str(path))
        self.assertIn(f"--menu file {path}", self.log_text())


if __name__ == "__main__":
    unittest.main()
