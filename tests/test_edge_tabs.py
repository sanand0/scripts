import struct
import sys
import tempfile
import unittest
from datetime import datetime
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import edge_tabs


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


class EdgeTabsTest(unittest.TestCase):
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

        parsed = edge_tabs.parse_snss(data)

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

        self.assertEqual(edge_tabs.parse_snss(data), [])

    def test_pruned_front_updates_navigation_indices(self):
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            command(2, struct.pack("<ii", 10, 0)),
            navigation(10, 0, "https://old.example/", "Old"),
            navigation(10, 1, "https://current.example/", "Current"),
            command(7, struct.pack("<ii", 10, 1)),
            command(11, struct.pack("<ii", 10, 1)),
        )

        parsed = edge_tabs.parse_snss(data)

        self.assertEqual(parsed[0].tabs[0].url, "https://current.example/")

    def test_default_session_file_uses_newest_session(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions = Path(directory) / "Default" / "Sessions"
            sessions.mkdir(parents=True)
            old = sessions / "Session_1"
            new = sessions / "Session_2"
            old.write_bytes(b"old")
            new.write_bytes(b"new")

            self.assertEqual(edge_tabs.default_session_file(Path(directory)), new)

    def test_text_output_includes_titles_by_default(self):
        data = snss(
            command(0, struct.pack("<ii", 100, 10)),
            command(2, struct.pack("<ii", 10, 0)),
            navigation(10, 0, "https://example.com/", "Example title"),
        )
        output = StringIO()

        with redirect_stdout(output):
            edge_tabs.print_text(edge_tabs.parse_snss(data), Path("Session"), urls_only=False)

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
        windows = edge_tabs.parse_snss(data)
        output = StringIO()

        with redirect_stdout(output):
            edge_tabs.print_text(windows, Path("Session"), urls_only=False)

        tabs = edge_tabs.windows_to_json(windows, Path("Session"))["windows"][0]["tabs"]
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

        tab = edge_tabs.parse_snss(data)[0].tabs[0]

        self.assertFalse(tab.pinned)
        self.assertIsNone(tab.group)

    def test_json_output_includes_utc_timestamp(self):
        result = edge_tabs.windows_to_json([], Path("Session"))

        timestamp = datetime.fromisoformat(str(result["timestamp"]))

        self.assertEqual(timestamp.utcoffset().total_seconds(), 0)
        self.assertEqual(result["source"], "Session")


if __name__ == "__main__":
    unittest.main()
