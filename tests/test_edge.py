import argparse
import struct
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from datetime import datetime
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
loader = SourceFileLoader("edge", str(Path(__file__).resolve().parents[1] / "edge"))
spec = spec_from_loader(loader.name, loader)
edge = module_from_spec(spec)
sys.modules[loader.name] = edge
loader.exec_module(edge)


def align4(value):
    return value + (-value % 4)


def pickle_string(value):
    data = value.encode()
    return struct.pack("<I", len(data)) + data + b"\0" * (align4(len(data)) - len(data))


def pickle_string16(value):
    data = value.encode("utf-16-le")
    return struct.pack("<I", len(value)) + data + b"\0" * (align4(len(data)) - len(data))


def command(command_id, payload):
    return struct.pack("<HB", len(payload) + 1, command_id) + payload


def navigation(tab_id, index, url, title):
    body = struct.pack("<ii", tab_id, index) + pickle_string(url) + pickle_string16(title)
    return command(6, struct.pack("<I", len(body)) + body)


def tab_group(tab_id, group_id=None):
    high, low = group_id or (0, 0)
    return command(
        25, struct.pack("<i4xQQ?7x", tab_id, high, low, group_id is not None)
    )


def tab_group_metadata(group_id, title):
    body = (
        struct.pack("<QQ", *group_id)
        + pickle_string16(title)
        + struct.pack("<I??2x", 0, False, False)
    )
    return command(27, struct.pack("<I", len(body)) + body)


def snss(*commands):
    return b"SNSS" + struct.pack("<I", 3) + b"".join(commands)


class EdgeTest(unittest.TestCase):
    def test_profile_argument_is_repeatable_with_requested_defaults(self):
        parser = argparse.ArgumentParser()
        edge.add_session_arguments(parser)
        self.assertIsNone(parser.parse_args([]).profile)
        self.assertEqual(parser.parse_args([]).profile or edge.DEFAULT_PROFILES, edge.DEFAULT_PROFILES)
        self.assertEqual(parser.parse_args(["--profile", "one", "--profile", "two"]).profile, [Path("one"), Path("two")])

    def test_is_profile_open_checks_live_edge_process(self):
        with patch.object(Path, "readlink", return_value=Path("host-123")), patch.object(
            Path, "read_bytes", return_value=b"/opt/microsoft/msedge/msedge\0--type=browser"
        ):
            self.assertTrue(edge.is_profile_open(Path("profile")))
        with patch.object(Path, "readlink", return_value=Path("host-123")), patch.object(
            Path, "read_bytes", return_value=b"/usr/bin/firefox\0"
        ):
            self.assertFalse(edge.is_profile_open(Path("profile")))
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(edge.is_profile_open(Path(directory)))

    def test_load_profiles_skips_profiles_without_an_open_browser(self):
        profiles = [Path("closed"), Path("open")]
        with patch.object(edge, "is_profile_open", side_effect=lambda profile: profile.name == "open"), patch.object(
            edge, "load_windows", return_value=([edge.Window(1)], Path("Session"))
        ) as load_windows:
            loaded = edge.load_profiles(profiles, None)
        self.assertEqual(loaded[0][0], Path("open"))
        self.assertEqual(loaded[0][1][0].profile, Path("open"))
        load_windows.assert_called_once_with(Path("open"), None)

    def test_md_searches_all_profiles_and_identifies_ambiguous_matches(self):
        first = edge.Tab(1, navigations={0: edge.Navigation("https://one.example/", "Shared one")})
        second = edge.Tab(1, navigations={0: edge.Navigation("https://two.example/", "Shared two")})
        loaded = [
            (Path("microsoft-edge-cdp"), [edge.Window(1, tabs=[first])], Path("Session_1")),
            (Path("microsoft-edge"), [edge.Window(1, tabs=[second])], Path("Session_2")),
        ]
        output = StringIO()
        with patch.object(edge, "load_profiles", return_value=loaded), patch.object(edge, "tab_markdown") as tab_markdown, redirect_stdout(output):
            result = edge.md_command(["shared"], edge.DEFAULT_PROFILES, None, "http://localhost:9222")
        self.assertEqual(result, 1)
        self.assertIn("microsoft-edge-cdp\tShared one", output.getvalue())
        self.assertIn("microsoft-edge\tShared two", output.getvalue())
        tab_markdown.assert_not_called()

    def test_md_extracts_unique_match_from_second_profile(self):
        tab = edge.Tab(1, navigations={0: edge.Navigation("https://two.example/", "Only target")})
        loaded = [(Path("first"), [], Path("Session_1")), (Path("second"), [edge.Window(1, tabs=[tab])], Path("Session_2"))]
        with patch.object(edge, "load_profiles", return_value=loaded), patch.object(edge, "tab_markdown", return_value="Body") as tab_markdown:
            result = edge.md_command(["target"], edge.DEFAULT_PROFILES, None, "http://localhost:9222")
        self.assertEqual(result, 0)
        tab_markdown.assert_called_once_with(tab, "http://localhost:9222")

    def test_same_exact_group_name_in_two_profiles_is_ambiguous(self):
        first = edge.Tab(1, group="Research", group_id=(1, 1), navigations={0: edge.Navigation("https://one.example/", "One")})
        second = edge.Tab(2, group="Research", group_id=(2, 2), navigations={0: edge.Navigation("https://two.example/", "Two")})
        loaded = [(Path("first"), [edge.Window(1, tabs=[first])], Path("Session_1")), (Path("second"), [edge.Window(2, tabs=[second])], Path("Session_2"))]
        output = StringIO()
        with patch.object(edge, "load_profiles", return_value=loaded), patch.object(edge, "tab_markdown") as tab_markdown, redirect_stdout(output):
            result = edge.md_command(["research"], edge.DEFAULT_PROFILES, None, "http://localhost:9222")
        self.assertEqual(result, 1)
        self.assertIn("first\tOne", output.getvalue())
        self.assertIn("second\tTwo", output.getvalue())
        tab_markdown.assert_not_called()

    def test_parse_windows_in_tab_order(self):
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            command(0, struct.pack("<ii", 100, 11)),
            command(0, struct.pack("<ii", 200, 20)),
            command(2, struct.pack("<ii", 11, 0)),
            command(2, struct.pack("<ii", 10, 1)),
            command(2, struct.pack("<ii", 20, 0)),
            navigation(10, 0, "https://later.example/", "Later"),
            navigation(11, 0, "https://first.example/", "First"),
            navigation(20, 0, "https://other.example/", "Other"),
        )

        parsed = edge.parse_snss(data)

        self.assertEqual([window.id for window in parsed], [100, 200])
        self.assertEqual([tab.url for tab in parsed[0].tabs], ["https://first.example/", "https://later.example/"])
        self.assertEqual(parsed[1].tabs[0].title, "Other")

    def test_closed_tabs_are_excluded(self):
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            command(2, struct.pack("<ii", 10, 0)),
            navigation(10, 0, "https://closed.example/", "Closed"),
            command(16, struct.pack("<iq", 10, 0)),
        )

        self.assertEqual(edge.parse_snss(data), [])

    def test_pruned_front_updates_navigation_indices(self):
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            command(2, struct.pack("<ii", 10, 0)),
            navigation(10, 0, "https://old.example/", "Old"),
            navigation(10, 1, "https://current.example/", "Current"),
            command(7, struct.pack("<ii", 10, 1)),
            command(11, struct.pack("<ii", 10, 1)),
        )

        parsed = edge.parse_snss(data)

        self.assertEqual(parsed[0].tabs[0].url, "https://current.example/")

    def test_default_session_file_uses_newest_session(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions = Path(directory) / "Default" / "Sessions"
            sessions.mkdir(parents=True)
            old = sessions / "Session_1"
            new = sessions / "Session_2"
            old.write_bytes(b"old")
            new.write_bytes(b"new")

            self.assertEqual(edge.default_session_file(Path(directory)), new)

    def test_text_output_includes_titles_by_default(self):
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            command(2, struct.pack("<ii", 10, 0)),
            navigation(10, 0, "https://example.com/", "Example title"),
        )
        output = StringIO()

        with redirect_stdout(output):
            edge.print_text(edge.parse_snss(data), Path("Session"), urls_only=False)

        self.assertRegex(output.getvalue(), r"^# Timestamp: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00")
        self.assertIn("  1. Example title\n     https://example.com/", output.getvalue())

    def test_group_and_pinned_state_are_in_outputs(self):
        group_id = (123, 456)
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            command(0, struct.pack("<ii", 100, 11)),
            command(2, struct.pack("<ii", 10, 0)),
            command(2, struct.pack("<ii", 11, 1)),
            navigation(10, 0, "https://pinned.example/", "Pinned"),
            navigation(11, 0, "https://plain.example/", "Plain"),
            command(12, struct.pack("<i?3x", 10, True)),
            tab_group(10, group_id),
            tab_group_metadata(group_id, "Research"),
        )
        windows = edge.parse_snss(data)
        output = StringIO()

        with redirect_stdout(output):
            edge.print_text(windows, Path("Session"), urls_only=False)

        tabs = edge.windows_to_json(windows, Path("Session"))["windows"][0]["tabs"]
        self.assertEqual((tabs[0]["group"], tabs[0]["pinned"]), ("Research", True))
        self.assertEqual((tabs[1]["group"], tabs[1]["pinned"]), (None, False))
        self.assertIn(
            "  1. [PIN] Pinned [Research]\n     https://pinned.example/",
            output.getvalue(),
        )

    def test_later_group_and_pin_commands_replace_prior_state(self):
        group_id = (123, 456)
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            navigation(10, 0, "https://example.com/", "Example"),
            command(12, struct.pack("<i?3x", 10, True)),
            command(12, struct.pack("<i?3x", 10, False)),
            tab_group(10, group_id),
            tab_group(10),
            tab_group_metadata(group_id, "Research"),
        )

        tab = edge.parse_snss(data)[0].tabs[0]

        self.assertFalse(tab.pinned)
        self.assertIsNone(tab.group)

    def test_json_output_includes_utc_timestamp(self):
        result = edge.windows_to_json([], Path("Session"))

        timestamp = datetime.fromisoformat(str(result["timestamp"]))

        self.assertEqual(timestamp.utcoffset().total_seconds(), 0)
        self.assertEqual(result["source"], "Session")

    def test_find_tabs_matches_title_group_and_url_case_insensitively(self):
        windows = [
            edge.Window(
                1,
                tabs=[
                    edge.Tab(1, group="Research", navigations={0: edge.Navigation("https://example.com/one", "Alpha")}),
                    edge.Tab(2, group="Other", navigations={0: edge.Navigation("https://docs.example/guide", "Beta")}),
                ],
            )
        ]

        self.assertEqual([tab.id for tab in edge.find_tabs(windows, "ALP")], [1])
        self.assertEqual([tab.id for tab in edge.find_tabs(windows, "search")], [1])
        self.assertEqual([tab.id for tab in edge.find_tabs(windows, "DOCS.EX")], [2])

    def test_md_lists_all_ambiguous_matches_without_connecting_to_cdp(self):
        tabs = [
            edge.Tab(1, group="One", navigations={0: edge.Navigation("https://a.example/", "Shared A")}),
            edge.Tab(2, group=None, navigations={0: edge.Navigation("https://b.example/", "Shared B")}),
        ]
        output = StringIO()

        with patch.object(edge, "load_windows", return_value=([edge.Window(1, tabs=tabs)], Path("Session"))), patch.object(
            edge, "tab_markdown"
        ) as tab_markdown, redirect_stdout(output):
            result = edge.md_command(["shared"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 1)
        self.assertEqual(
            output.getvalue(),
            "## shared\n\nProfile\tTitle\tTab group\tURL\nprofile\tShared A\tOne\thttps://a.example/\nprofile\tShared B\t\thttps://b.example/\n",
        )
        tab_markdown.assert_not_called()

    def test_md_outputs_markdown_for_only_match(self):
        tab = edge.Tab(1, group="Notes", navigations={0: edge.Navigation("https://example.com/", "Target")})
        output = StringIO()

        with patch.object(edge, "load_windows", return_value=([edge.Window(1, tabs=[tab])], Path("Session"))), patch.object(
            edge, "tab_markdown", return_value="# Main\n\nBody"
        ) as tab_markdown, redirect_stdout(output):
            result = edge.md_command(["target"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue(),
            "# Target\n\n- URL: https://example.com/\n- Tab group: Notes\n\n# Main\n\nBody\n",
        )
        tab_markdown.assert_called_once_with(tab, "http://localhost:9222")

    def test_md_reports_no_match(self):
        error = StringIO()

        with patch.object(edge, "load_windows", return_value=([], Path("Session"))), redirect_stderr(error):
            result = edge.md_command(["missing"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 1)
        self.assertEqual(error.getvalue(), "No tab matches: missing\n")

    def test_md_reports_every_ambiguous_phrase_before_extracting_any_tab(self):
        tabs = [
            edge.Tab(1, navigations={0: edge.Navigation("https://one.example/a", "Alpha one")}),
            edge.Tab(2, navigations={0: edge.Navigation("https://two.example/a", "Alpha two")}),
            edge.Tab(3, group="Beta one", navigations={0: edge.Navigation("https://three.example/", "Unique")}),
            edge.Tab(4, group="Beta two", navigations={0: edge.Navigation("https://four.example/", "Other")}),
        ]
        output = StringIO()

        with patch.object(edge, "load_windows", return_value=([edge.Window(1, tabs=tabs)], Path("Session"))), patch.object(
            edge, "tab_markdown"
        ) as tab_markdown, redirect_stdout(output):
            result = edge.md_command(["alpha", "unique", "beta"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 1)
        self.assertIn("## alpha\n\nProfile\tTitle\tTab group\tURL", output.getvalue())
        self.assertIn("Alpha one\t\thttps://one.example/a", output.getvalue())
        self.assertIn("## beta\n\nProfile\tTitle\tTab group\tURL", output.getvalue())
        self.assertNotIn("## unique", output.getvalue())
        tab_markdown.assert_not_called()

    def test_md_outputs_multiple_unique_tabs_with_metadata_and_separator(self):
        first = edge.Tab(1, group="Research", navigations={0: edge.Navigation("https://one.example/", "First")})
        second = edge.Tab(2, navigations={0: edge.Navigation("https://two.example/", "Second")})
        output = StringIO()

        with patch.object(
            edge, "load_windows", return_value=([edge.Window(1, tabs=[first, second])], Path("Session"))
        ), patch.object(edge, "tab_markdown", side_effect=["First body", "Second body"]), redirect_stdout(output):
            result = edge.md_command(["first", "two.example"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 0)
        self.assertEqual(
            output.getvalue(),
            "# First\n\n- URL: https://one.example/\n- Tab group: Research\n\nFirst body\n\n"
            "---\n\n# Second\n\n- URL: https://two.example/\n\nSecond body\n",
        )

    def test_md_outputs_same_tab_once_when_multiple_phrases_match_it(self):
        tab = edge.Tab(1, navigations={0: edge.Navigation("https://example.com/guide", "Useful guide")})
        output = StringIO()

        with patch.object(edge, "load_windows", return_value=([edge.Window(1, tabs=[tab])], Path("Session"))), patch.object(
            edge, "tab_markdown", return_value="Body"
        ) as tab_markdown, redirect_stdout(output):
            result = edge.md_command(["useful", "example.com"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 0)
        self.assertEqual(output.getvalue().count("# Useful guide"), 1)
        tab_markdown.assert_called_once_with(tab, "http://localhost:9222")

    def test_md_exact_group_match_outputs_every_group_tab_in_order(self):
        tabs = [
            edge.Tab(1, group="Deep Research", navigations={0: edge.Navigation("https://one.example/", "First")}),
            edge.Tab(2, group="Deep Research", navigations={0: edge.Navigation("https://two.example/", "Second")}),
            edge.Tab(3, group="Other", navigations={0: edge.Navigation("https://three.example/", "Third")}),
        ]
        output = StringIO()

        with patch.object(edge, "load_windows", return_value=([edge.Window(1, tabs=tabs)], Path("Session"))), patch.object(
            edge, "tab_markdown", side_effect=["First body", "Second body"]
        ), redirect_stdout(output):
            result = edge.md_command(["DEEP research"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 0)
        self.assertLess(output.getvalue().index("# First"), output.getvalue().index("# Second"))
        self.assertNotIn("# Third", output.getvalue())

    def test_md_exact_group_match_takes_precedence_over_other_partial_matches(self):
        tabs = [
            edge.Tab(1, group="Research", navigations={0: edge.Navigation("https://one.example/", "Grouped")}),
            edge.Tab(2, group=None, navigations={0: edge.Navigation("https://two.example/", "Research notes")}),
        ]
        output = StringIO()

        with patch.object(edge, "load_windows", return_value=([edge.Window(1, tabs=tabs)], Path("Session"))), patch.object(
            edge, "tab_markdown", return_value="Body"
        ), redirect_stdout(output):
            result = edge.md_command(["research"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 0)
        self.assertIn("# Grouped", output.getvalue())
        self.assertNotIn("# Research notes", output.getvalue())

    def test_md_mixes_groups_and_unique_phrases_and_deduplicates_tabs(self):
        tabs = [
            edge.Tab(1, group="One", navigations={0: edge.Navigation("https://one.example/", "First")}),
            edge.Tab(2, group="One", navigations={0: edge.Navigation("https://two.example/", "Second")}),
            edge.Tab(3, group="Two", navigations={0: edge.Navigation("https://three.example/", "Third")}),
            edge.Tab(4, group="Two", navigations={0: edge.Navigation("https://four.example/", "Fourth")}),
            edge.Tab(5, navigations={0: edge.Navigation("https://five.example/", "Fifth")}),
        ]
        output = StringIO()

        with patch.object(edge, "load_windows", return_value=([edge.Window(1, tabs=tabs)], Path("Session"))), patch.object(
            edge, "tab_markdown", side_effect=["1", "2", "5", "3", "4"]
        ) as tab_markdown, redirect_stdout(output):
            result = edge.md_command(["one", "second", "fifth", "two"], Path("profile"), None, "http://localhost:9222")

        self.assertEqual(result, 0)
        self.assertEqual([output.getvalue().count(f"# {title}") for title in ("First", "Second", "Fifth", "Third", "Fourth")], [1] * 5)
        self.assertEqual(tab_markdown.call_count, 5)
        positions = [output.getvalue().index(f"# {title}") for title in ("First", "Second", "Fifth", "Third", "Fourth")]
        self.assertEqual(positions, sorted(positions))

    def test_html_to_markdown_keeps_main_content_and_absolute_links(self):
        html = """
        <html><head><title>Article</title></head><body>
          <nav>Site navigation that should not appear</nav>
          <article><h1>Useful title</h1><p>This is the useful article body with enough text
          for readability to identify it as the main content.</p>
          <p><a href="/guide">Read the guide</a></p></article>
        </body></html>
        """

        markdown = edge.html_to_markdown(html, "https://example.com/posts/one")

        self.assertIn("# Useful title", markdown)
        self.assertIn("[Read the guide](https://example.com/guide)", markdown)
        self.assertNotIn("Site navigation", markdown)

    def test_html_to_markdown_keeps_all_chatgpt_turns(self):
        html = """
        <html><body><nav>Chat history</nav><main>
          <section data-testid="conversation-turn-1"><div data-message-author-role="user"><p>First question</p></div></section>
          <section data-testid="conversation-turn-2"><div data-message-author-role="assistant"><p>First complete answer</p></div></section>
          <section data-testid="conversation-turn-3"><div data-message-author-role="user"><p>Follow-up question</p></div></section>
          <section data-testid="conversation-turn-4"><div data-message-author-role="assistant"><p>Final complete answer</p></div></section>
        </main></body></html>
        """

        markdown = edge.html_to_markdown(html, "https://chatgpt.com/c/123")

        self.assertIn("First question", markdown)
        self.assertIn("First complete answer", markdown)
        self.assertIn("Follow-up question", markdown)
        self.assertIn("Final complete answer", markdown)
        self.assertNotIn("Chat history", markdown)

    def test_html_to_markdown_keeps_all_claude_turns(self):
        html = """
        <html><body><div role="main">
          <div data-testid="user-message"><p>Claude question one</p></div>
          <div data-is-streaming="false"><div class="font-claude-response"><p>Claude answer one</p></div></div>
          <div data-testid="user-message"><p>Claude question two</p></div>
          <div data-is-streaming="false"><div class="font-claude-response"><p>Claude answer two</p></div></div>
        </div></body></html>
        """

        markdown = edge.html_to_markdown(html, "https://claude.ai/chat/123")

        self.assertIn("Claude question one", markdown)
        self.assertIn("Claude answer one", markdown)
        self.assertIn("Claude question two", markdown)
        self.assertIn("Claude answer two", markdown)

    def test_html_to_markdown_keeps_all_gemini_conversations(self):
        html = """
        <html><body>
          <div class="conversation-container"><user-query><p>Gemini question</p></user-query><model-response><p>Gemini answer</p></model-response></div>
          <div class="conversation-container"><user-query><p>Gemini follow-up</p></user-query><model-response><p>Gemini final answer</p></model-response></div>
        </body></html>
        """

        markdown = edge.html_to_markdown(html, "https://gemini.google.com/app/123")

        self.assertIn("Gemini question", markdown)
        self.assertIn("Gemini answer", markdown)
        self.assertIn("Gemini follow-up", markdown)
        self.assertIn("Gemini final answer", markdown)

    def test_html_to_markdown_prefers_large_semantic_section_over_tiny_article(self):
        cards = "".join(f"<h2>Plugin {index}</h2><p>Useful plugin description {index} with meaningful details.</p>" for index in range(20))
        html = f"""
        <html><body><article><p>Small promotional card.</p></article>
          <section><h1>Plugin directory</h1>
            <div class="w-form-done">Thank you! Your submission has been received!</div>
            <div class="u-display-none">This is hidden CMS metadata.</div>
            {cards}
          </section>
        </body></html>
        """

        markdown = edge.html_to_markdown(html, "https://claude.com/plugins")

        self.assertIn("# Plugin directory", markdown)
        self.assertIn("## Plugin 0", markdown)
        self.assertIn("## Plugin 19", markdown)
        self.assertNotIn("submission has been received", markdown)
        self.assertNotIn("hidden CMS metadata", markdown)


if __name__ == "__main__":
    unittest.main()
