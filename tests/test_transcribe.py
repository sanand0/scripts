"""Offline coverage for the minimal transcribe CLI."""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

SCRIPT = Path(__file__).resolve().parents[1] / "transcribe"
RUNNER = CliRunner()


def load_script():
    spec = importlib.util.spec_from_loader("simple_transcribe", SourceFileLoader("simple_transcribe", str(SCRIPT)))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fake_client(monkeypatch, calls, response="Transcript from model"):
    responses = iter(response) if isinstance(response, (list, tuple)) else None

    class Client:
        def __init__(self, *, api_key):
            calls.append(("key", api_key))
            self.files = SimpleNamespace(upload=self.upload)
            self.chats = SimpleNamespace(create=self.create)

        def upload(self, *, file):
            calls.append(("upload", file))
            return SimpleNamespace(name="files/test", source=file, state="ACTIVE")

        def create(self, *, model, config):
            assert config.thinking_config.thinking_level in {"low", "medium", "high"}
            calls.append(("chat", model, config.system_instruction))
            return SimpleNamespace(send_message=self.send_message)

        def send_message(self, contents):
            calls.append(("message", contents[0].source))
            text = next(responses) if responses is not None else response
            blank = not text.strip()
            return SimpleNamespace(
                text=text,
                candidates=[] if blank else [SimpleNamespace(finish_reason="STOP")],
                prompt_feedback=SimpleNamespace(block_reason=SimpleNamespace(name="OTHER")) if blank else None,
                usage_metadata=SimpleNamespace(
                    prompt_token_count=1000, total_token_count=1000 if blank else 1100,
                    cached_content_token_count=0,
                ),
            )

    config = lambda *, system_instruction, thinking_config: SimpleNamespace(
        system_instruction=system_instruction, thinking_config=thinking_config
    )
    thinking = lambda *, thinking_level: SimpleNamespace(thinking_level=thinking_level)
    genai = SimpleNamespace(Client=Client, types=SimpleNamespace(GenerateContentConfig=config, ThinkingConfig=thinking))
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=genai))
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("TRANSCRIBE_CALLS_MODEL", raising=False)


def test_multiple_paths_default_prompt_model_and_same_directory(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls)
    files = [tmp_path / "with space.mp3", tmp_path / "nested" / "sample.opus"]
    files[1].parent.mkdir()
    for file in files:
        file.write_bytes(b"test audio")

    result = RUNNER.invoke(module.app, [str(f) for f in files])

    assert result.exit_code == 0, result.output
    assert [f.with_suffix(".md").read_text() for f in files] == ["Transcript from model\n"] * 2
    assert calls == [
        ("key", "test-key"),
        ("upload", files[0]), ("chat", module.DEFAULT_MODEL, "Transcribe"), ("message", files[0]),
        ("upload", files[1]), ("chat", module.DEFAULT_MODEL, "Transcribe"), ("message", files[1]),
    ]
    assert module.DEFAULT_MODEL == "gemini-3.8-flash"
    assert "model=gemini-3.8-flash\tthinking=low\tcost_est_usd=$0.001125" in result.output


def test_skip_existing_without_api_call(tmp_path, monkeypatch):
    module = load_script()
    audio = tmp_path / "audio.opus"
    audio.write_bytes(b"audio")
    output = audio.with_suffix(".md")
    output.write_text("keep\n")
    monkeypatch.setattr(module, "build_client", lambda: (_ for _ in ()).throw(AssertionError("unexpected API")))

    result = RUNNER.invoke(module.app, [str(audio)])

    assert result.exit_code == 0, result.output
    assert "SKIP" in result.output
    assert output.read_text() == "keep\n"


def test_force_model_and_prompt_after_file_arguments(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls, response="Corrected transcript\n")
    audio = tmp_path / "meeting.opus"
    audio.write_bytes(b"audio")
    audio.with_suffix(".md").write_text("old")

    result = RUNNER.invoke(module.app, [str(audio), "--prompt", "Fix basic spelling", "--model", "gemini-test", "--force"])

    assert result.exit_code == 0, result.output
    assert ("chat", "gemini-test", "Fix basic spelling") in calls
    assert audio.with_suffix(".md").read_text() == "Corrected transcript\n"


def test_empty_response_preserves_previous_transcript(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls, response="  ")
    audio = tmp_path / "meeting.opus"
    audio.write_bytes(b"audio")
    output = audio.with_suffix(".md")
    output.write_text("previous transcript\n")

    result = RUNNER.invoke(module.app, [str(audio), "--force"])

    assert result.exit_code == 1
    assert "empty transcript" in result.output
    assert output.read_text() == "previous transcript\n"


def test_empty_low_retry_medium_transcribes_and_bills_both(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls, response=["", "Speech recovered at medium thinking"])
    audio = tmp_path / "recording.opus"
    audio.write_bytes(b"audio")
    result = RUNNER.invoke(module.app, [str(audio)])
    assert result.exit_code == 0, result.output
    assert audio.with_suffix(".md").read_text() == "Speech recovered at medium thinking\n"
    assert result.output.count("RETRY") == 1
    assert "thinking=low+medium\tcost_est_usd=$0.001875" in result.output
    assert len([x for x in calls if x[0] == "upload"]) == 1
    assert len([x for x in calls if x[0] == "chat"]) == 2


def test_low_and_medium_empty_retry_high_success(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls, response=["", "", "Recovered with high thinking"])
    audio = tmp_path / "recovered.opus"
    audio.write_bytes(b"audio")
    result = RUNNER.invoke(module.app, [str(audio)])
    assert result.exit_code == 0, result.output
    assert audio.with_suffix(".md").read_text() == "Recovered with high thinking\n"
    assert result.output.count("RETRY") == 2
    assert "thinking=low+medium+high\tcost_est_usd=$0.002625" in result.output
    assert len([x for x in calls if x[0] == "chat"]) == 3


def test_three_empty_responses_keep_existing_transcript_and_report_cost(tmp_path, monkeypatch):
    module = load_script()
    fake_client(monkeypatch, [], response=["", "", ""])
    audio = tmp_path / "recording.opus"
    audio.write_bytes(b"audio")
    output = audio.with_suffix(".md")
    output.write_text("keep previous\n")
    result = RUNNER.invoke(module.app, [str(audio), "--force"])
    assert result.exit_code == 1
    assert output.read_text() == "keep previous\n"
    assert "block_reason=OTHER" in result.output
    assert "cost_est_usd=$0.002250" in result.output


def test_estimate_cost_accounts_for_cached_and_thinking_tokens():
    module = load_script()
    usage = SimpleNamespace(prompt_token_count=1200, cached_content_token_count=200, total_token_count=1700)
    expected = (1000 * 0.75 + 200 * 0.075 + 500 * 3.75) / 1_000_000
    assert module.estimate_cost(usage, "gemini-3.8-flash") == expected
    assert module.estimate_cost(usage, "unknown-model") is None
    legacy = SimpleNamespace(
        prompt_token_count=1200, total_token_count=1700, cached_content_token_count=200,
        prompt_tokens_details=[SimpleNamespace(modality="AUDIO", token_count=1100), SimpleNamespace(modality="TEXT", token_count=100)],
        cache_tokens_details=[SimpleNamespace(modality="AUDIO", token_count=200)],
    )
    legacy_expected = (900 * 1.0 + 100 * 0.5 + 200 * 0.1 + 500 * 3.0) / 1_000_000
    assert module.estimate_cost(legacy, "gemini-3-flash-preview") == legacy_expected


def test_failed_transcript_does_not_stop_following_files(tmp_path, monkeypatch):
    module = load_script()
    files = [tmp_path / f"{name}.opus" for name in ("first", "bad", "last")]
    for file in files:
        file.write_bytes(b"audio")
    previous = files[1].with_suffix(".md")
    previous.write_text("previous transcript\n")
    seen = []
    monkeypatch.setattr(module, "build_client", lambda: object())

    def transcribe(_client, path, _model, _prompt):
        seen.append(path.name)
        if path == files[1]:
            raise RuntimeError("simulated model error")
        return module.Transcript(f"transcript for {path.stem}\n", 0.002, "low")

    monkeypatch.setattr(module, "transcribe_file", transcribe)
    result = RUNNER.invoke(module.app, [*(str(file) for file in files), "--force"])
    assert result.exit_code == 1
    assert seen == [file.name for file in files]
    assert "ERROR " + str(files[1]) in result.output
    assert "FAILED 1/3 recording(s):" in result.output
    assert files[0].with_suffix(".md").read_text() == "transcript for first\n"
    assert files[2].with_suffix(".md").read_text() == "transcript for last\n"
    assert previous.read_text() == "previous transcript\n"


def test_missing_middle_file_is_skipped(tmp_path, monkeypatch):
    module = load_script()
    good = tmp_path / "good.opus"
    last = tmp_path / "last.opus"
    missing = tmp_path / "missing.opus"
    good.write_bytes(b"audio")
    last.write_bytes(b"audio")
    monkeypatch.setattr(module, "build_client", lambda: object())
    monkeypatch.setattr(module, "transcribe_file", lambda _client, *_args: module.Transcript("ok\n", 0.001, "low"))

    result = RUNNER.invoke(module.app, [str(good), str(missing), str(last)])
    assert result.exit_code == 1
    assert "Not a file" in result.output
    assert good.with_suffix(".md").read_text() == "ok\n"
    assert last.with_suffix(".md").read_text() == "ok\n"


def test_missing_file_is_an_error(tmp_path):
    module = load_script()
    result = RUNNER.invoke(module.app, [str(tmp_path / "missing.opus")])
    assert result.exit_code != 0
    assert "Not a file" in result.output


def test_refuse_markdown_as_input_even_when_forced(tmp_path):
    module = load_script()
    path = tmp_path / "notes.md"
    path.write_text("original notes")
    result = RUNNER.invoke(module.app, [str(path), "--force"])
    assert result.exit_code != 0
    assert "Expected audio" in result.output
    assert path.read_text() == "original notes"


def test_env_model_override(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls)
    monkeypatch.setenv("TRANSCRIBE_CALLS_MODEL", "env-model")
    audio = tmp_path / "test.mp3"
    audio.write_bytes(b"audio")
    result = RUNNER.invoke(module.app, [str(audio)])
    assert result.exit_code == 0, result.output
    assert ("chat", "env-model", "Transcribe") in calls


def test_cwd_env_precedes_script_env(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls)
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=current-key\n")
    client = module.build_client()
    assert client is not None
    assert calls == [("key", "current-key")]


def test_script_env_fallback(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls)
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.chdir(tmp_path)
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    (script_dir / ".env").write_text("GEMINI_API_KEY=script-key\n")
    monkeypatch.setattr(module, "__file__", str(script_dir / "transcribe"))
    module.build_client()
    assert calls == [("key", "script-key")]


def test_processing_upload_waits_until_active(monkeypatch):
    module = load_script()
    calls = []
    states = iter(["PROCESSING", "ACTIVE"])

    def get(*, name):
        calls.append(("get", name))
        return SimpleNamespace(name=name, state=next(states))

    client = SimpleNamespace(files=SimpleNamespace(get=get))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))
    result = module.wait_for_file_active(client, SimpleNamespace(name="files/abc", state="PROCESSING"))
    assert result.state == "ACTIVE"
    assert calls == [("sleep", 2), ("get", "files/abc"), ("sleep", 2), ("get", "files/abc")]


def test_failed_processing_stops_with_explanation(monkeypatch):
    import pytest

    module = load_script()
    client = SimpleNamespace(files=SimpleNamespace(get=lambda **kwargs: SimpleNamespace(
        name=kwargs["name"], state="FAILED", error="unsupported codec"
    )))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="unsupported codec"):
        module.wait_for_file_active(client, SimpleNamespace(name="files/bad", state="PROCESSING"))


def test_waiting_for_active_times_out(monkeypatch):
    import pytest

    module = load_script()
    client = SimpleNamespace(files=SimpleNamespace(get=lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not poll"))))
    with pytest.raises(TimeoutError, match="did not become ACTIVE"):
        module.wait_for_file_active(client, SimpleNamespace(name="files/slow", state="PROCESSING"), timeout=0)


def test_webm_is_remuxed_losslessly_and_original_preserved(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls)
    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"original")

    def fake_ffmpeg(command, **kwargs):
        assert command[command.index("-i") + 1] == str(audio)
        assert command[command.index("-c:a") + 1] == "copy"
        assert command[command.index("-f") + 1] == "ogg"
        Path(command[-1]).write_bytes(b"remuxed")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_ffmpeg)
    result = RUNNER.invoke(module.app, [str(audio)])
    assert result.exit_code == 0, result.output
    uploads = [call[1] for call in calls if call[0] == "upload"]
    assert len(uploads) == 1 and uploads[0].suffix == ".opus"
    assert uploads[0].parent != tmp_path and not uploads[0].exists()
    assert audio.read_bytes() == b"original"
    assert audio.with_suffix(".md").read_text() == "Transcript from model\n"


def test_webm_remux_failure_does_not_upload_or_write(tmp_path, monkeypatch):
    module = load_script()
    calls = []
    fake_client(monkeypatch, calls)
    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"bad header")
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr="bad container"))
    result = RUNNER.invoke(module.app, [str(audio)])
    assert result.exit_code == 1
    assert "bad container" in result.output
    assert not audio.with_suffix(".md").exists()
    assert not any(call[0] == "upload" for call in calls)
