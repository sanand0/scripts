from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "backuptwitter.py"
SPEC = importlib.util.spec_from_file_location("backuptwitter", SCRIPT)
assert SPEC and SPEC.loader
backup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backup
SPEC.loader.exec_module(backup)


def test_fetch_skips_broken_client_transaction_initialization(monkeypatch, tmp_path: Path, capsys) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs):
            self._ensure_client_transaction()

        def _ensure_client_transaction(self) -> None:
            raise AssertionError("the broken transaction initializer was called")

        def fetch_list_timeline(self, source_id: str, limit: int) -> list[dict[str, str]]:
            return [{"id": "1"}]

    class FakeClientModule:
        _ABSOLUTE_MAX_COUNT = 500
        TwitterClient = FakeClient

    monkeypatch.setattr(backup, "working_dir", lambda cwd: _NullContext())
    package = _module(__path__=[])
    monkeypatch.setitem(sys.modules, "twitter_cli", package)
    monkeypatch.setitem(sys.modules, "twitter_cli.client", FakeClientModule)
    package.client = FakeClientModule
    package.auth = _module(get_cookies=lambda: {"auth_token": "a", "ct0": "c"})
    package.config = _module(load_config=lambda: {})
    package.serialization = _module(tweets_to_data=lambda tweets: tweets)
    monkeypatch.setitem(sys.modules, "twitter_cli.auth", package.auth)
    monkeypatch.setitem(sys.modules, "twitter_cli.config", package.config)
    monkeypatch.setitem(sys.modules, "twitter_cli.serialization", package.serialization)

    result = backup.fetch({"kind": "list", "id": "list"}, 1, tmp_path)

    assert result["data"] == [{"id": "1"}]
    assert "Failed to init ClientTransaction" not in capsys.readouterr().err


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _module(**values):
    return type("FakeModule", (), values)
