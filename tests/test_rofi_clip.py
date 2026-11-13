from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import textwrap

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "rofi" / "rofi-clip.sh"


def test_vtt_to_text_removes_youtube_rolling_overlap():
    text = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000 align:start position:0%

Hello<00:00:01.000><c> everyone</c>

00:00:02.000 --> 00:00:02.010
Hello everyone

00:00:02.010 --> 00:00:04.000
Hello everyone
welcome<00:00:03.000><c> to class.</c>

00:00:04.000 --> 00:00:04.010
welcome to class.
"""
    result = run_transform("transform_vtt_to_text", text)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Hello everyone welcome to class.\n"


def test_vtt_to_text_preserves_speakers_repetitions_and_paragraphs(tmp_path):
    source = tmp_path / "captions.vtt"
    source.write_text("""WEBVTT

STYLE
::cue {color: lime;}

NOTE a comment
not speech

first-cue
00:00.000 --> 00:01.000
<v Alice><i>Yes.</i> &amp; 2 &lt; 3.</v>

second-cue
00:01.000 --> 00:02.000
<v Alice>Yes.</v>

3
00:02.000 --> 00:03.000
<v Bob>Yes.</v>

4
00:06.000 --> 00:07.000
<v Bob>Next topic.</v>
""")
    result = run_transform("transform_vtt_to_text", str(source))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Alice: Yes. & 2 < 3. Yes.\n\nBob: Yes.\n\nBob: Next topic.\n"


def test_vtt_to_text_rejects_non_vtt():
    result = run_transform("transform_vtt_to_text", "This is not a caption file.")
    assert result.returncode != 0
    assert result.stdout == ""


def test_vtt_to_text_menu_is_wired():
    result = run_shell('source "$1"; printf "%s" "${MENU_FNS["VTT to text                   (subtitles or file path)"]}"')
    assert result.stdout == "transform_vtt_to_text"


def test_vtt_to_text_runs_through_clipboard_menu(tmp_path):
    result = run_shell(f'''
        source "$1"
        ACTIVATION_LOG="{tmp_path}/activations.tsv"
        clipboard_get() {{ printf 'WEBVTT\n\n00:00.000 --> 00:01.000\nHello world.\n'; }}
        rofi() {{ cat >/dev/null; printf 'VTT to text                   (subtitles or file path)'; }}
        clipboard_set() {{ cat; }}
        main
    ''')
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Hello world."
    assert "VTT to text" in (tmp_path / "activations.tsv").read_text()


@pytest.mark.skipif(not shutil.which("fish") or not shutil.which("jaq"), reason="needs fish and jaq")
@pytest.mark.parametrize("manual,automatic,expected", [
    ({"en-US": [{"ext": "vtt", "url": "manual"}]},
     {"en": [{"ext": "vtt", "url": "automatic"}]}, "manual"),
    ({}, {"en-orig": [{"ext": "vtt", "url": "original"}],
          "en-fr": [{"ext": "vtt", "url": "translated"}]}, "original"),
    ({"fr": [{"ext": "vtt", "url": "french"}]}, {}, None),
])
def test_youtube_subtitles_prefers_edited_english(tmp_path, manual, automatic, expected):
    setup = (SCRIPT_PATH.parents[1] / "setup.fish").read_text()
    function = setup.split("function youtube-subtitles ", 1)[1].split("\n# Extract the first embedded", 1)[0]
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"subtitles": manual, "automatic_captions": automatic}))
    result = subprocess.run(["fish", "-c", f'''
        function uvx; cat "{metadata}"; end
        function curl; printf '%s' "$argv[-1]"; end
        function youtube-subtitles {function}
        youtube-subtitles 'https://www.youtube.com/watch?v=test'
    '''], capture_output=True, text=True)
    if expected is None:
        assert result.returncode != 0
        assert result.stdout == ""
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout == expected


@pytest.mark.parametrize("failed_tool", ["xclip", "mise"])
def test_direct_html_conversion_preserves_clipboard_on_failure(tmp_path, monkeypatch, failed_tool):
    writes = tmp_path / "writes"
    for tool in ("xclip", "mise"):
        content = "#!/bin/bash\n"
        if tool == "xclip":
            content += f'if [[ " $* " != *" -o "* ]]; then echo write >> "{writes}"; exit; fi\n'
        content += "exit 1\n" if tool == failed_tool else "printf '<p>Keep</p>'\n"
        target = tmp_path / tool
        target.write_text(content)
        target.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + ":/usr/bin:/bin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DISPLAY", ":test")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("ROFI_CLIP_DEBUG_LOG", str(tmp_path / "debug.log"))

    result = subprocess.run(["bash", str(SCRIPT_PATH), "--html-to-markdown"], capture_output=True, text=True)

    assert result.returncode != 0
    assert not writes.exists()


@pytest.mark.parametrize("backend", ["x11", "wayland"])
@pytest.mark.parametrize("direct", [True, False])
def test_html_conversion_updates_expected_selections(tmp_path, monkeypatch, backend, direct):
    writes = tmp_path / "writes"
    reader = "xclip" if backend == "x11" else "wl-paste"
    writer = "xclip" if backend == "x11" else "wl-copy"
    for tool in {reader, writer, "mise", "rofi"}:
        if tool == "rofi":
            body = "exit 99" if direct else "cat >/dev/null; printf 'HTML → Markdown                (from clipboard HTML)'"
        elif tool == "mise":
            body = "cat >/dev/null; printf '**Converted**'"
        else:
            body = f'if [[ "$0" == *wl-paste || " $* " == *" -o "* ]]; then printf "<p>HTML only</p>"; else printf "%s\\t%s\\n" "$*" "$(cat)" >> "{writes}"; fi'
        target = tmp_path / tool
        target.write_text("#!/bin/bash\n" + body + "\n")
        target.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path) + ":/usr/bin:/bin")
    monkeypatch.setenv("DISPLAY", ":test")
    monkeypatch.setenv("ROFI_CLIP_DEBUG_LOG", str(tmp_path / "debug.log"))
    if backend == "wayland":
        monkeypatch.setenv("WAYLAND_DISPLAY", "test")
    else:
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    command = ["bash", str(SCRIPT_PATH)] + (["--html-to-markdown"] if direct else [])
    result = subprocess.run(command, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    rows = writes.read_text().splitlines()
    assert len(rows) == (2 if direct else 1)
    assert all(row.endswith("\t**Converted**") for row in rows)
    assert "primary" not in rows[0]
    if direct:
        assert "primary" in rows[1]


def test_media_key_uses_direct_rofi_html_conversion():
    config = (SCRIPT_PATH.parents[1] / "setup" / "media-keys.dconf").read_text()
    section = config.split("[custom-keybindings/copy-to-markdown]\n", 1)[1].split("\n\n", 1)[0]
    assert "binding='<Control><Alt>c'" in section
    assert "command='/home/sanand/code/scripts/rofi/rofi-clip.sh --html-to-markdown'" in section


def run_transform(transform_name: str, text: str) -> subprocess.CompletedProcess[str]:
    command = textwrap.dedent(
        """\
        source "$1"
        bootstrap_tool_paths
        INPUT="$2"
        "$3"
        """
    )
    return subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH), text, transform_name],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )


def run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )


def test_transform_text_to_slug_transliterates_and_normalizes() -> None:
    result = run_transform("transform_text_to_slug", " Peoples' Café ")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "peoples-cafe"


def test_transform_text_to_slug_collapses_runs_and_trims_edges() -> None:
    result = run_transform("transform_text_to_slug", "---Hello___world!!!---")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello-world"


def test_transform_text_to_slug_flattens_multiline_input() -> None:
    result = run_transform("transform_text_to_slug", "First line\n\nSecond line")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "first-line-second-line"


def test_transform_html_to_md_reuses_shared_helpers() -> None:
    command = textwrap.dedent(
        """\
        source "$1"
        bootstrap_tool_paths
        clipboard_get_html() { printf '<p>Hello</p>'; }
        html_to_markdown() { printf 'Hello'; }
        transform_html_to_md
        """
    )

    result = subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Hello"


def test_transform_html_to_md_falls_back_to_plain_text_clipboard_input() -> None:
    command = textwrap.dedent(
        """\
        source "$1"
        bootstrap_tool_paths
        INPUT='<p>Hello</p>'
        clipboard_get_html() { printf ''; }
        html_to_markdown() {
            local html
            html=$(cat)
            [[ "$html" == '<p>Hello</p>' ]] || exit 1
            printf 'Hello'
        }
        transform_html_to_md
        """
    )

    result = subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Hello"


def test_menu_exposes_html_to_markdown_command() -> None:
    result = run_shell(
        textwrap.dedent(
            """\
            source "$1"
            bootstrap_tool_paths
            printf '%s' "${MENU_FNS["HTML → Markdown                (from clipboard HTML)"]}"
            """
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "transform_html_to_md"


def test_transform_strip_tracking_cleans_standalone_url() -> None:
    result = run_transform(
        "transform_strip_tracking",
        "https://example.com/article?utm_source=newsletter&chapter=2&ref=sidebar",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "https://example.com/article?chapter=2"


def test_transform_strip_tracking_cleans_links_in_markdown_list() -> None:
    text = (
        "- [First](https://example.com/a?utm_source=email&keep=1)\n"
        "\n"
        "  - [Second link](https://example.org/b?gclid=abc&lang=en&ref=menu)  \n"
        "    Notes stay here.\n"
    )
    expected = (
        "- [First](https://example.com/a?keep=1)\n"
        "\n"
        "  - [Second link](https://example.org/b?lang=en)  \n"
        "    Notes stay here.\n"
    )

    result = run_transform("transform_strip_tracking", text)

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


def test_transform_strip_tracking_changes_only_embedded_urls() -> None:
    text = (
        "Before  https://one.example/path?utm_medium=social&id=7, then\t"
        "https://two.example/?fbclid=abc.\n"
        "Keep literal utm_source=yes and all surrounding whitespace.\n"
    )
    expected = (
        "Before  https://one.example/path?id=7, then\t"
        "https://two.example/.\n"
        "Keep literal utm_source=yes and all surrounding whitespace.\n"
    )

    result = run_transform("transform_strip_tracking", text)

    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
