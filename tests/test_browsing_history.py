import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browsing_history


def history_row(source: str, visit_id: int) -> dict[str, object]:
    return {
        "activity_source": "history",
        "timestamp": "2026-07-17T12:00:00Z",
        "_sort_visit_time": 13_450_000_000_000_000,
        "url": "https://example.com/page",
        "title": "Example",
        "profile": "Default",
        "profile_name": "Synced account",
        "source": source,
        "visit_id": visit_id,
        "url_id": visit_id,
    }


class BrowsingHistoryTest(unittest.TestCase):
    def test_default_roots_prioritize_cdp_and_still_include_both_config_trees(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            edge = home / ".config/microsoft-edge"
            cdp = home / ".config/microsoft-edge-cdp"
            edge.mkdir(parents=True)
            cdp.mkdir()

            with patch.object(browsing_history.Path, "home", return_value=home):
                roots = browsing_history.default_roots()

        self.assertEqual(roots[:2], [cdp, edge])
        self.assertEqual(len(roots), len(set(roots)))

    def test_history_identity_ignores_source_path_and_local_visit_id(self):
        cdp = history_row("/home/me/.config/microsoft-edge-cdp/Default/History", 10)
        edge = history_row("/home/me/.config/microsoft-edge/Default/History", 900)

        self.assertEqual(browsing_history.record_id(cdp), browsing_history.record_id(edge))

    def test_sync_keeps_one_logical_visit_and_prefers_first_root(self):
        rows = [
            history_row("/home/me/.config/microsoft-edge-cdp/Default/History", 10),
            history_row("/home/me/.config/microsoft-edge/Default/History", 900),
        ]
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "history.db"
            with patch.object(browsing_history, "merged_rows", return_value=iter(rows)):
                count = browsing_history.sync_database(db, [Path(row["source"]) for row in rows])
            with sqlite3.connect(db) as con:
                stored = con.execute("SELECT source, visit_id FROM activity").fetchall()

        self.assertEqual(count, 1)
        self.assertEqual(stored, [(rows[0]["source"], "10")])

    def test_existing_cross_root_duplicates_are_collapsed_during_schema_migration(self):
        rows = [
            history_row("/home/me/.config/microsoft-edge/Default/History", 900),
            history_row("/home/me/.config/microsoft-edge-cdp/Default/History", 10),
        ]
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "history.db"
            with sqlite3.connect(db) as con:
                columns = ", ".join(f"{name} TEXT" for name in browsing_history.DB_COLUMNS)
                con.execute(
                    f"CREATE TABLE activity ({columns}, first_seen_at TEXT, updated_at TEXT)"
                )
                for row in rows:
                    data = browsing_history.normalize_db_row(row)
                    data["record_id"] = str(row["visit_id"])
                    names = [*browsing_history.DB_COLUMNS, "first_seen_at", "updated_at"]
                    values = [data.get(name, "2026-07-17 12:00:00") for name in names]
                    con.execute(
                        f"INSERT INTO activity ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})",
                        values,
                    )

            with patch.object(browsing_history, "merged_rows", return_value=iter(())):
                browsing_history.sync_database(db, [])
            with sqlite3.connect(db) as con:
                pk = [
                    row[1]
                    for row in sorted(con.execute("PRAGMA table_info(activity)"), key=lambda row: row[5])
                    if row[5]
                ]
                stored = con.execute("SELECT source, visit_id FROM activity").fetchall()

        self.assertEqual(pk, ["activity_source", "record_id"])
        self.assertEqual(stored, [(rows[1]["source"], "10")])


if __name__ == "__main__":
    unittest.main()
