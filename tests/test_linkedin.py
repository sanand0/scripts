#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click>=8.2",
#   "lxml>=6",
#   "markdownify>=1.2",
#   "playwright>=1.54",
#   "pytest>=8",
# ]
# ///
"""Tests for the sibling linkedin.py script."""

from __future__ import annotations

import asyncio
import gzip
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "linkedin.py"
SPEC = importlib.util.spec_from_file_location("linkedin", SCRIPT)
assert SPEC and SPEC.loader
linkedin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(linkedin)


def page(*sections: str, title: str = "Example Person") -> str:
    return (
        f"<html><head><title>{title} | LinkedIn</title></head>"
        f"<body><main>{''.join(sections)}</main></body></html>"
    )


def section(label: str, body: str = "") -> str:
    return f"<section><h2>{label}</h2>{body}</section>"


def saved_profile(directory: Path, *, optional_sections: bool) -> None:
    profile_sections = [
        section(
            "Example Person",
            "<p>· 1st</p><p>· 2nd</p>"
            "<p>Software builder</p><p>Example City</p>"
            "<a href='/connect'>Connect</a>",
        )
    ]
    if optional_sections:
        profile_sections.append(section("About", "<p>Builds useful things.</p>"))
    (directory / "profile.html").write_text(page(*profile_sections))
    (directory / "experience.html").write_text(
        page(
            section(
                "Experience",
                "<p>Engineer</p><p>Example Labs</p><p>2020 - Present</p>"
                "<p>· Built reliable systems</p><p>• Kept them simple</p>",
            )
        )
    )
    education = (
        section("Education", "<p>Example University</p>")
        if optional_sections
        else "<section></section>"
    )
    (directory / "education.html").write_text(page(education))


def render_saved_profile(directory: Path) -> object:
    return linkedin.render_profile(
        {
            name: (directory / f"{name}.html").read_text()
            for name in ("profile", "experience", "education")
        },
        "https://www.linkedin.com/in/example-person/",
        request_count=0,
    )


def cache_profile(directory: Path) -> None:
    source = directory / "source"
    source.mkdir()
    saved_profile(source, optional_sections=True)
    base = "https://www.linkedin.com/in/example-person/"
    for name, url in {
        "profile": base,
        "experience": f"{base}details/experience/",
        "education": f"{base}details/education/",
    }.items():
        linkedin.write_cache(
            directory,
            {
                "schema_version": 1,
                "kind": "page",
                "url": url,
                "final_url": url,
                "fetched_at": datetime.now(UTC).isoformat(),
                "status": 200,
                "content_type": "text/html",
                "response_body": f"raw {name}",
                "dom": (source / f"{name}.html").read_text(),
            },
        )


def test_optional_sections_are_omitted(tmp_path: Path) -> None:
    saved_profile(tmp_path, optional_sections=False)

    result = render_saved_profile(tmp_path)

    assert result.markdown.startswith("# Example Person\n")
    assert "## Experience" in result.markdown
    assert "## About" not in result.markdown
    assert "## Education" not in result.markdown
    assert "Connect" not in result.markdown
    assert "· 1st" not in result.markdown
    assert "· 2nd" in result.markdown


def test_markdown_preserves_sections_and_normalizes_bullets(tmp_path: Path) -> None:
    saved_profile(tmp_path, optional_sections=True)

    markdown = render_saved_profile(tmp_path).markdown

    assert "## About\n\nBuilds useful things." in markdown
    assert "## Experience\n\nEngineer" in markdown
    assert "- Built reliable systems" in markdown
    assert "- Kept them simple" in markdown
    assert "## Education\n\nExample University" in markdown


def test_cache_path_mirrors_url_and_distinguishes_queries(tmp_path: Path) -> None:
    profile = linkedin.cache_path(
        tmp_path, "https://www.linkedin.com/in/example-person/details/education/"
    )
    search = linkedin.cache_path(
        tmp_path,
        "https://www.linkedin.com/search/results/people/?keywords=Example&page=2",
    )

    assert profile.relative_to(tmp_path).as_posix() == (
        "urls/www.linkedin.com/in/example-person/details/education/index.json.gz"
    )
    assert search.parent.relative_to(tmp_path).as_posix() == (
        "urls/www.linkedin.com/search/results/people"
    )
    assert search.name.startswith("index__q_keywords-Example_page-2__")
    assert search != linkedin.cache_path(
        tmp_path,
        "https://www.linkedin.com/search/results/people/?keywords=Other&page=2",
    )
    assert (
        linkedin.cache_path(
            tmp_path,
            "https://www.linkedin.com/in/example-person/details/education/#fragment",
        )
        == profile
    )


def test_default_cache_and_corrupt_record(tmp_path: Path) -> None:
    assert linkedin.DEFAULT_CACHE_DIR == (
        Path.home() / ".cache/sanand-scripts/linkedin-cli"
    )
    url = "https://www.linkedin.com/in/example-person/"
    path = linkedin.cache_path(tmp_path, url)
    path.parent.mkdir(parents=True)
    path.write_text("not gzip")

    assert linkedin.read_cache(tmp_path, url, cache_days=30) is None


def test_cache_preserves_raw_response_and_dom_with_expiry(tmp_path: Path) -> None:
    url = "https://www.linkedin.com/in/example-person/"
    fetched_at = datetime(2026, 1, 1, tzinfo=UTC)
    record = {
        "schema_version": 1,
        "kind": "page",
        "url": url,
        "final_url": url,
        "fetched_at": fetched_at.isoformat(),
        "status": 200,
        "content_type": "text/html",
        "response_body": "<html>original response</html>",
        "dom": "<html>hydrated DOM</html>",
    }

    path = linkedin.write_cache(tmp_path, record)

    with gzip.open(path, "rt") as file:
        assert json.load(file) == record
    assert (
        linkedin.read_cache(
            tmp_path, url, cache_days=30, now=fetched_at + timedelta(days=29)
        )
        == record
    )
    assert (
        linkedin.read_cache(
            tmp_path, url, cache_days=30, now=fetched_at + timedelta(days=31)
        )
        is None
    )
    assert (
        linkedin.read_cache(
            tmp_path,
            url,
            cache_days=30,
            refresh=True,
            now=fetched_at + timedelta(days=1),
        )
        is None
    )


def test_cli_uses_fresh_cache_without_browser(tmp_path: Path) -> None:
    cache_profile(tmp_path)

    completed = subprocess.run(
        [
            "uv",
            "run",
            str(SCRIPT),
            "profile",
            "https://www.linkedin.com/in/example-person/",
            "--cache-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.startswith("# Example Person\n")
    assert completed.stderr.count("CACHE") == 3


def test_fetch_opens_linkedin_from_empty_browser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    response = SimpleNamespace(
        ok=True,
        status=200,
        text=AsyncMock(return_value="raw"),
        all_headers=AsyncMock(return_value={}),
    )
    tab = SimpleNamespace(
        url="https://www.linkedin.com/in/example-person/",
        goto=AsyncMock(return_value=response),
        wait_for_timeout=AsyncMock(),
        locator=MagicMock(return_value=SimpleNamespace(count=AsyncMock(return_value=1))),
        content=AsyncMock(return_value="<main>profile</main>"),
        title=AsyncMock(return_value="Example Person | LinkedIn"),
        close=AsyncMock(),
    )
    context = SimpleNamespace(pages=[], new_page=AsyncMock(return_value=tab))
    manager = MagicMock()
    manager.__aenter__.return_value.chromium.connect_over_cdp = AsyncMock(
        return_value=SimpleNamespace(contexts=[context])
    )
    monkeypatch.setattr(linkedin, "async_playwright", lambda: manager)
    expected = object()
    monkeypatch.setattr(linkedin, "render_profile", MagicMock(return_value=expected))

    result = asyncio.run(
        linkedin.fetch_profile(
            "https://www.linkedin.com/in/example-person/",
            "http://localhost:9222",
            0,
            tmp_path,
            30,
            False,
        )
    )

    assert result is expected
    context.new_page.assert_awaited_once()
    tab.close.assert_awaited_once()


def test_rejects_non_profile_url() -> None:
    with pytest.raises(Exception, match="expected https://www.linkedin.com/in/"):
        linkedin.normalize_profile_url("https://example.com/not-linkedin")


def test_profile_vanity_alias() -> None:
    assert linkedin.normalize_profile_url("example-person-123") == (
        "https://www.linkedin.com/in/example-person-123/"
    )
    with pytest.raises(Exception, match="vanity"):
        linkedin.normalize_profile_url("not/a/vanity")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
