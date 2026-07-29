#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pytest>=8.0.0",
#     "python-frontmatter>=1.0.0",
#     "markdown-it-py>=3.0.0",
#     "premailer>=3.10.0",
#     "pygments>=2.17.0",
#     "typer>=0.12.0",
#     "platformdirs>=4.0.0",
#     "google-auth>=2.0.0",
#     "google-auth-oauthlib>=1.0.0",
#     "google-auth-httplib2>=0.2.0",
#     "google-api-python-client>=2.0.0",
# ]
# ///
"""Tests for the sibling htmlemail.py script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import htmlemail

SCRIPT = Path(__file__).resolve().parents[1] / "htmlemail.py"


def render(
    tmp_path: Path,
    markdown: str,
    *,
    frontmatter: str = "title: Test",
    base_url: str | None = "https://example.com/blog/post/",
) -> tuple[str, str]:
    path = tmp_path / "post.md"
    path.write_text(f"---\n{frontmatter}\n---\n\n{markdown}")
    return htmlemail.markdown_to_email_html(path, base_url)


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("- A\n  - B\n", ("<ul", "<li", "B")),
        ("```python\nprint('hi')\n```\n", ("print", "<pre", "<code")),
        ("| A | B |\n| - | - |\n| 1 | 2 |\n", ("<table", "<th", "<td")),
        ('<div markdown="1">**bold**</div>', ("<div", "**bold**")),
        ("Line 1\\\nLine 2\n", ("Line 1", "Line 2", "<br")),
    ],
)
def test_markdown_rendering(tmp_path: Path, markdown: str, expected: tuple[str, ...]) -> None:
    _subject, html = render(tmp_path, markdown)

    assert all(fragment in html for fragment in expected)


def test_youtube_embed(tmp_path: Path) -> None:
    _subject, html = render(tmp_path, '<iframe src="https://www.youtube.com/embed/abc123"></iframe>')

    assert "youtu.be/abc123" in html
    assert "i.ytimg.com" in html


def test_video_embed(tmp_path: Path) -> None:
    _subject, html = render(
        tmp_path,
        """
<video controls poster="../poster.webp" title="Demo walkthrough">
  <source src="../clip.webm" type="video/webm">
  <source src="../clip.mp4" type="video/mp4">
  <track kind="captions" src="../clip.en.vtt" srclang="en" label="English">
</video>
""",
    )

    assert "<video" not in html
    assert "<strong>Video:</strong>" in html and "Watch video" in html
    assert "https://example.com/blog/clip.webm" in html
    assert "<strong>Captions:</strong>" in html
    assert "https://example.com/blog/clip.en.vtt" in html


def test_audio_embed(tmp_path: Path) -> None:
    _subject, html = render(
        tmp_path,
        """
<audio controls aria-label="Interview recording">
  <source src="../episode.ogg" type="audio/ogg">
  <source src="../episode.mp3" type="audio/mpeg">
  <track kind="subtitles" src="../episode.en.vtt" srclang="en">
</audio>
""",
    )

    assert "<audio" not in html
    assert "<strong>Audio:</strong>" in html and "Listen to audio" in html
    assert "https://example.com/blog/episode.ogg" in html
    assert "<strong>Captions:</strong>" in html
    assert "https://example.com/blog/episode.en.vtt" in html


def test_cli_base_url_resolves_relative_links(tmp_path: Path) -> None:
    _subject, html = render(tmp_path, "[rel](../x)\n\n![img](../i.png)\n")

    assert "https://example.com/blog/x" in html
    assert "https://example.com/blog/i.png" in html
    assert "s-anand.net" not in html


def test_missing_base_url_warns_and_preserves_relative_links(tmp_path: Path) -> None:
    path = tmp_path / "post.md"
    path.write_text("---\ntitle: Test\n---\n\n[rel](../x)\n\n![img](../i.png)\n")

    rendered = htmlemail.render_email(path)

    assert "../x" in rendered.html and "../i.png" in rendered.html
    assert rendered.warnings and "Relative href/src URLs" in rendered.warnings[0]
    assert "s-anand.net" not in rendered.html


def test_frontmatter_base_url_resolves_relative_links(tmp_path: Path) -> None:
    _subject, html = render(
        tmp_path,
        "[rel](../x)\n",
        frontmatter="title: Test\nbase_url: https://frontmatter.example/blog/post/",
        base_url=None,
    )

    assert "https://frontmatter.example/blog/x" in html


def test_html_is_auto_detected_and_premailer_applies(tmp_path: Path) -> None:
    path = tmp_path / "post.HTML"
    path.write_text("<style>p { color: red; }</style><p>Hello</p>")

    rendered = htmlemail.render_email(path)

    assert 'style="color:red"' in rendered.html
    assert "font-family" not in rendered.html


def test_input_format_overrides_extension(tmp_path: Path) -> None:
    html_path = tmp_path / "post.html"
    html_path.write_text("# Hello")
    markdown_path = tmp_path / "post.md"
    markdown_path.write_text("# Hello")

    assert "<h1" in htmlemail.render_email(html_path, input_format="markdown").html
    assert "<h1" not in htmlemail.render_email(markdown_path, input_format="html").html


def test_cli_input_format_override(tmp_path: Path) -> None:
    path = tmp_path / "post.html"
    path.write_text("# Hello")

    result = subprocess.run(
        ["uv", "run", str(SCRIPT), str(path), "--input-format", "markdown"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "<h1" in result.stdout


def test_invalid_input_format(tmp_path: Path) -> None:
    path = tmp_path / "post.md"
    path.write_text("Hello")

    with pytest.raises(htmlemail.HtmlemailError, match="must be html or markdown"):
        htmlemail.render_email(path, input_format="text")


def test_recipient_token_and_scope_helpers() -> None:
    assert htmlemail.format_recipients(["a@example.com", "b@example.com"]) == "a@example.com, b@example.com"
    token_name = htmlemail.token_filename_for_email("A.B+X@Gmail.COM")
    assert token_name.startswith("a_b_x_gmail_com-") and token_name.endswith(".json")
    assert htmlemail.canonical_scope_set(htmlemail.SCOPES) == htmlemail.canonical_scope_set(
        "openid https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.send"
    )


def test_config_path_creation_and_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTMLEMAIL_CONFIG_DIR", str(tmp_path))

    assert htmlemail.get_config_dir().exists()
    config = htmlemail.load_config()
    config.setdefault("profiles", {})["a@example.com"] = {"verified_email": "a@example.com"}
    htmlemail.save_config(config)

    assert htmlemail.load_config()["profiles"]["a@example.com"]["verified_email"] == "a@example.com"


def test_sender_identity_validation() -> None:
    htmlemail.validate_sender_identity("a@example.com", {"email": "A@Example.com"})

    with pytest.raises(htmlemail.HtmlemailError, match="Authenticated Google account"):
        htmlemail.validate_sender_identity("a@example.com", {"email": "b@example.com"})


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
