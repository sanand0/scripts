"""Tests for the single-file translate CLI. Run: uv run --with websockets --with python-dotenv --with pytest pytest tests/test_translate.py"""
import importlib.machinery
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

FILE = Path(__file__).resolve().parent.parent / "translate"
LOADER = importlib.machinery.SourceFileLoader("translate_script_under_test", str(FILE))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
translate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = translate
LOADER.exec_module(translate)


def test_setup_translation():
    settings = translate.Settings(language="ta", echo=False)
    setup = settings.setup()["setup"]
    assert setup["model"] == "models/gemini-3.5-live-translate-preview"
    assert setup["generationConfig"]["translationConfig"] == {
        "targetLanguageCode": "ta", "echoTargetLanguage": False
    }
    assert "systemInstruction" not in setup


def test_setup_live_agent():
    settings = translate.Settings(model="gemini-3.8-live", language="fr", voice="Aoede", temperature=0.7)
    setup = settings.setup()["setup"]
    assert "Translate" in setup["systemInstruction"]["parts"][0]["text"]
    assert setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Aoede"
    assert setup["generationConfig"]["temperature"] == 0.7


@pytest.mark.parametrize("name,code", [
    ("hindi", "hi"), ("Tamil", "ta"), ("pt-BR", "pt-BR"), ("fr", "fr"), ("zh-Hans", "zh-Hans")
])
def test_languages(name, code):
    assert translate.valid_language(name) == code


@pytest.mark.parametrize("name", ["", "bad!", "gemini-3-flash-preview", "other-live-model"])
def test_invalid_models(name):
    with pytest.raises(ValueError):
        translate.valid_model(name)


def test_usage_cumulative_reports_do_not_double_count():
    u = translate.SessionUsage(translate.DEFAULT_MODEL)
    u.update({"promptTokenCount": 100, "responseTokenCount": 20})
    u.update({"promptTokenCount": 100, "responseTokenCount": 20})
    u.update({"promptTokenCount": 130, "responseTokenCount": 40})
    assert u.tokens() == (130, 40)
    u.update({"promptTokenCount": 12, "responseTokenCount": 4})
    assert u.tokens() == (142, 44)
    assert u.charge() == pytest.approx((142 * 3.5 + 44 * 21) / 1_000_000)


def test_usage_fallback_pcm_duration():
    u = translate.SessionUsage(translate.DEFAULT_MODEL, input_bytes=32000, output_bytes=48000)
    assert u.tokens() == (25, 25)
    assert u.charge() == pytest.approx((25 * 3.5 + 25 * 21) / 1_000_000)


def test_unknown_model_cost_explicitly_unknown():
    u = translate.SessionUsage("gemini-4-live-preview")
    assert u.charge() is None


def test_save_key_keeps_other_values_and_private_permissions(tmp_path):
    path = tmp_path / ".env"
    path.write_text("OTHER_SECRET=keep\nGEMINI_API_KEY=old\nSOMETHING=yes\n")
    translate.save_key("newkey", path)
    assert path.read_text() == "OTHER_SECRET=keep\nGEMINI_API_KEY=newkey\nSOMETHING=yes\n"
    assert path.stat().st_mode & 0o777 == 0o600


def test_save_key_does_not_follow_symlinks(tmp_path):
    target = tmp_path / "target"
    target.write_text("secret\n")
    symlink = tmp_path / ".env"
    symlink.symlink_to(target)
    with pytest.raises(RuntimeError):
        translate.save_key("not-saved", symlink)
    assert target.read_text() == "secret\n"


def test_key_lookup_prefers_exported_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    monkeypatch.setenv("GOOGLE_API_KEY", "other-env")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(translate, "ENV_FILE", tmp_path / "script.env")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=from-cwd\n")
    (tmp_path / "script.env").write_text("GEMINI_API_KEY=from-script\n")
    assert translate.key_from_sources() == ("from-env", "environment GEMINI_API_KEY")
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("GOOGLE_API_KEY")
    assert translate.key_from_sources()[0] == "from-cwd"
    (tmp_path / ".env").unlink()
    assert translate.key_from_sources()[0] == "from-script"


def test_safe_error_hides_query_key():
    assert "ABC123" not in translate.safe_error(ValueError(
        "Error connecting to wss://example.test/?key=ABC123&model=foo"))

def test_supported_language_catalog():
    assert len(translate.LANGUAGES) == 78
    assert translate.valid_language("Norwegian") == "no"
    assert translate.valid_language("nb") == "nb"
    assert translate.valid_language("Chinese (Traditional)") == "zh-Hant"
    assert translate.valid_language("Portuguese (Brazil)") == "pt-BR"
    assert translate.valid_language("portuguese (portugal)") == "pt-PT"
    assert translate.valid_language("TAMIL") == "ta"
    assert translate.language_name("ta") == "Tamil"
    assert translate.language_name("nb") == "Norwegian"
    listing = translate.format_languages()
    for name, codes in translate.LANGUAGES.items():
        assert name in listing
        for code in codes:
            assert code in listing


@pytest.mark.parametrize("invalid", ["INVALID_LANGUAGE", "", "pt", "zz", "English-US", "tamilian"])
def test_invalid_languages(invalid):
    with pytest.raises(ValueError, match="Unsupported language"):
        translate.valid_language(invalid)


def test_lang_list_invalid_does_not_reconnect(capsys):
    import asyncio
    from unittest.mock import AsyncMock
    app = translate.Translator(translate.Settings(language="hi"), "unused", "test")
    app.reconfigure = AsyncMock()
    assert asyncio.run(app.command("lang")) is True
    first_output = capsys.readouterr().out
    assert "Hindi" in first_output and "zh-Hant" in first_output
    assert asyncio.run(app.command("lang INVALID_LANGUAGE")) is True
    invalid_output = capsys.readouterr().out
    assert "Unknown language" in invalid_output
    assert "Portuguese (Brazil)" in invalid_output
    assert app.settings.language == "hi"
    app.reconfigure.assert_not_awaited()


def test_lang_full_name_and_code_do_not_reconnect_unnecessarily(capsys):
    import asyncio
    from unittest.mock import AsyncMock
    app = translate.Translator(translate.Settings(language="hi"), "unused", "test")
    app.reconfigure = AsyncMock()
    assert asyncio.run(app.command("lang Portuguese (Brazil)")) is True
    assert app.settings.language == "pt-BR"
    app.reconfigure.assert_awaited_once()
    app.reconfigure.reset_mock()
    assert asyncio.run(app.command("lang PT-br")) is True
    app.reconfigure.assert_not_awaited()
    assert "Already translating" in capsys.readouterr().out


def test_translate_model_voice_setting_does_not_claim_to_pin_voice(capsys):
    import asyncio
    from unittest.mock import AsyncMock
    app = translate.Translator(translate.Settings(), "unused", "test")
    app.reconfigure = AsyncMock()
    assert asyncio.run(app.command("voice Aoede")) is True
    assert app.settings.voice == "Aoede"
    assert "cannot lock the voice" in capsys.readouterr().out
    app.reconfigure.assert_not_awaited()
