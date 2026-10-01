from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_module():
    script_path = Path(__file__).resolve().parents[1] / "call"
    if str(script_path.parent) not in sys.path:
        sys.path.insert(0, str(script_path.parent))
    spec = importlib.util.spec_from_loader(
        "transcribe_calls", SourceFileLoader("transcribe_calls", str(script_path))
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_script(
    script_path: Path,
    *args: Path | str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = (env or os.environ).copy()
    # Copies of call must ship with its existing sibling timestamp helper.
    source = Path(__file__).resolve().parents[1]
    if script_path.parent != source:
        shutil.copyfile(source / "timestamp.py", script_path.parent / "timestamp.py")
    # Integration tests must not write production caches.
    if cwd is not None:
        env["TRANSCRIBE_CALLS_PRICES_CACHE"] = str(cwd / "prices-cache.json")
        env.setdefault("TRANSCRIBE_CALLS_CACHE_DIR", str(cwd / "chunk-cache"))
    elif args and isinstance(args[0], Path):
        env.setdefault("TRANSCRIBE_CALLS_CACHE_DIR", str(args[0].parent / "chunk-cache"))
    return subprocess.run(
        ["uv", "run", str(script_path), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


def test_load_environment_falls_back_to_script_dir_env(tmp_path: Path, monkeypatch) -> None:
    current_dir = tmp_path / "current"
    script_dir = tmp_path / "script"
    current_dir.mkdir()
    script_dir.mkdir()
    script_dir.joinpath(".env").write_text("GEMINI_API_KEY=fallback-key\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "import-key")
    monkeypatch.chdir(current_dir)

    module = load_module()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    module.load_environment(current_dir=current_dir, script_dir=script_dir)

    assert os.environ["GEMINI_API_KEY"] == "fallback-key"


def test_load_environment_keeps_current_dir_env_over_script_dir_env(
    tmp_path: Path, monkeypatch
) -> None:
    current_dir = tmp_path / "current"
    script_dir = tmp_path / "script"
    current_dir.mkdir()
    script_dir.mkdir()
    current_dir.joinpath(".env").write_text("GEMINI_API_KEY=current-key\n", encoding="utf-8")
    script_dir.joinpath(".env").write_text("GEMINI_API_KEY=fallback-key\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "import-key")
    monkeypatch.chdir(current_dir)

    module = load_module()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    module.load_environment(current_dir=current_dir, script_dir=script_dir)

    assert os.environ["GEMINI_API_KEY"] == "current-key"


def write_fake_google_genai(package_root: Path) -> Path:
    genai_package = package_root / "google" / "genai"
    genai_package.mkdir(parents=True)
    (package_root / "google" / "__init__.py").write_text("from . import genai\n", encoding="utf-8")
    (genai_package / "__init__.py").write_text(
        textwrap.dedent(
            """\
            from __future__ import annotations

            import json
            import os
            from pathlib import Path

            class APIError(Exception):
                pass


            class _Errors:
                APIError = APIError


            errors = _Errors()


            class GenerateContentConfig:
                def __init__(self, system_instruction=None, **kwargs):
                    self.system_instruction = system_instruction
                    self.thinking_config = kwargs.get('thinking_config')


            class _Types:
                GenerateContentConfig = GenerateContentConfig


            types = _Types()


            class _UploadedFile:
                def __init__(self, file):
                    self.file = str(file)
                    self.name = f"files/{Path(file).name}"


            class _FilesAPI:
                def upload(self, *, file, config=None):
                    return _UploadedFile(file)


            class _ModelsAPI:
                def generate_content(self, *, model, contents, config=None):
                    log_path = os.environ["FAKE_GENAI_LOG"]
                    audio = next(item for item in contents if hasattr(item, "file"))
                    user_prompts = [item for item in contents if isinstance(item, str)]
                    with open(log_path, "a", encoding="utf-8") as handle:
                        handle.write(f"MODEL\\t{model}\\n")
                        handle.write(f"AUDIO\\t{audio.file}\\n")
                        handle.write(f"SYSTEM_PROMPT\\t{getattr(config, 'system_instruction', '')}\\n")
                        if config.thinking_config:
                            handle.write(f"THINKING\\t{config.thinking_config['thinking_level']}\\n")
                        if user_prompts:
                            handle.write(f"USER_PROMPT\\t{user_prompts[0]}\\n")
                    error_files = os.environ.get("FAKE_GENAI_ERROR_FILES", "").split(",")
                    if Path(audio.file).name in error_files:
                        raise APIError(f"forced error for {Path(audio.file).name}")
                    prompt_tokens = int(os.environ.get("FAKE_PROMPT_TOKENS", "100"))
                    output_tokens = int(os.environ.get("FAKE_OUTPUT_TOKENS", "50"))
                    thought_tokens = int(os.environ.get("FAKE_THOUGHT_TOKENS", "0"))
                    total_tokens = int(
                        os.environ.get(
                            "FAKE_TOTAL_TOKENS",
                            str(prompt_tokens + output_tokens + thought_tokens),
                        )
                    )
                    response_by_file = json.loads(os.environ.get("FAKE_GENAI_RESPONSE_BY_FILE", "{}"))
                    default_text = "\\n".join(
                        f"**Speaker**: [00:0{index}] Transcript for {Path(audio.file).name} line {index}"
                        for index in range(1, 6)
                    )
                    usage = type(
                        "UsageMetadata",
                        (),
                        {
                            "prompt_token_count": prompt_tokens,
                            "prompt_tokens_details": [type("Detail", (), {"modality": "AUDIO", "token_count": prompt_tokens})()],
                            "cache_tokens_details": [],
                            "cached_content_token_count": 0,
                            "candidates_token_count": output_tokens,
                            "thoughts_token_count": thought_tokens,
                            "total_token_count": total_tokens,
                        },
                    )()
                    return type(
                        "Response",
                        (),
                        {
                            "text": response_by_file.get(
                                Path(audio.file).name,
                                os.environ.get("FAKE_GENAI_TRANSCRIPT_TEXT", default_text),
                            ),
                            "usage_metadata": usage,
                            "model_version": model,
                        },
                    )()


            class _Chat:
                def __init__(self, models, *, model, config=None):
                    self._models = models
                    self._model = model
                    self._config = config

                def send_message(self, contents):
                    if not isinstance(contents, list):
                        contents = [contents]
                    return self._models.generate_content(
                        model=self._model, contents=contents, config=self._config
                    )


            class _ChatsAPI:
                def __init__(self, models):
                    self._models = models

                def create(self, *, model, config=None):
                    return _Chat(self._models, model=model, config=config)


            class Client:
                def __init__(self, *, api_key=None, **kwargs):
                    if not api_key:
                        raise APIError("missing api key")
                    log_path = os.environ.get("FAKE_GENAI_LOG")
                    if log_path:
                        with open(log_path, "a", encoding="utf-8") as handle:
                            handle.write(f"APIKEY\\t{api_key}\\n")
                    self.files = _FilesAPI()
                    self.models = _ModelsAPI()
                    self.chats = _ChatsAPI(self.models)
            """
        ),
        encoding="utf-8",
    )
    return package_root


def write_fake_ffmpeg_tools(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "ffprobe").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "${FAKE_FFPROBE_DURATION:-60}"
            """
        ),
        encoding="utf-8",
    )
    (bin_dir / "ffmpeg").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            output="${@: -1}"
            mkdir -p "$(dirname "$output")"
            if [[ -n "${FAKE_FFMPEG_LOG:-}" ]]; then
              printf '%s\\n' "$*" >> "$FAKE_FFMPEG_LOG"
            fi
            printf 'chunk' > "$output"
            """
        ),
        encoding="utf-8",
    )
    (bin_dir / "ffprobe").chmod(0o755)
    (bin_dir / "ffmpeg").chmod(0o755)
    return bin_dir


def write_fake_google_prices(prices_path: Path) -> Path:
    prices_path.write_text(
        json.dumps(
            {
                "vendor": "google",
                "models": [
                    {
                        "id": "gemini-3-flash-preview",
                        "name": "Gemini 3 Flash Preview",
                        "price_history": [
                            {"input": 2.0, "input_audio": 2.0, "output": 12.0, "input_cached": None}
                        ],
                    },
                    {
                        "id": "gemini-3-1-pro-preview",
                        "name": "Gemini 3.1 Pro <=200k",
                        "price_history": [
                            {"input": 2.0, "input_audio": 2.0, "output": 12.0, "input_cached": None}
                        ],
                    },
                    {
                        "id": "gemini-3-1-pro-preview-200k",
                        "name": "Gemini 3.1 Pro >200k",
                        "price_history": [
                            {"input": 4.0, "output": 18.0, "input_cached": None}
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return prices_path


def test_extract_system_prompt_prefers_first_code_fence() -> None:
    module = load_module()
    prompt = textwrap.dedent(
        """
        Intro text.

        ```markdown
        First prompt
        line two
        ```

        ```markdown
        Second prompt
        ```
        """
    )
    assert module.extract_system_prompt(prompt) == "First prompt\nline two"


def test_has_transcript_content_requires_non_empty_body() -> None:
    module = load_module()
    empty = "# Demo\n\n## Transcript\n\n"
    filled = "# Demo\n\n## Transcript\n\nHello there\n"

    assert module.has_transcript_content(empty) is False
    assert module.has_transcript_content(filled) is True


def test_upsert_transcript_section_preserves_existing_notes() -> None:
    module = load_module()
    existing = "# Demo\n\n## Notes\n\nAlready here.\n"
    updated = module.upsert_transcript_section(existing, "Demo", "Generated transcript")

    assert "## Notes\n\nAlready here." in updated
    assert "## Transcript\n\nGenerated transcript" in updated


def test_upsert_transcript_section_updates_prompt_metadata() -> None:
    module = load_module()
    existing = "---\ntags:\n---\n\n# Demo\n\n## Notes\n\nAlready here.\n"

    updated = module.upsert_transcript_section(
        existing,
        "Demo",
        "Generated transcript",
        prompt="Focus on action items",
    )

    assert "prompt: |-" in updated
    assert "  Focus on action items" in updated
    assert "## Transcript\n\nGenerated transcript" in updated


def test_upsert_transcript_section_rejects_duplicate_sections() -> None:
    module = load_module()
    markdown = "# Demo\n\n## Transcript\n\nFirst\n\n## Notes\n\nKeep me\n\n## Transcript\n\nSecond\n"

    try:
        module.upsert_transcript_section(markdown, "Demo", "Generated transcript")
    except ValueError as exc:
        assert "multiple ## Transcript sections" in str(exc)
    else:
        raise AssertionError("Expected duplicate transcript sections to be rejected")


def test_patch_transcript_section_replaces_requested_part() -> None:
    module = load_module()
    markdown = (
        "# Demo\n\n## Transcript\n\n"
        "first chunk\n\n---\n\nsecond chunk\n\n---\n\nthird chunk\n"
    )

    patched = module.patch_transcript_section(markdown, 2, "replacement chunk")

    assert "first chunk\n\n---\n\nreplacement chunk\n\n---\n\nthird chunk" in patched


def test_looks_like_transcript_accepts_speaker_lines() -> None:
    module = load_module()
    valid = "\n".join(
        f"**Speaker**: [00:0{index}] line {index}"
        for index in range(1, 6)
    )
    invalid = "It appears that you forgot to attach the audio file."

    assert module.looks_like_transcript(valid) is True
    assert module.looks_like_transcript(invalid) is False


def test_extract_prompt_metadata_reads_block_scalar() -> None:
    module = load_module()
    markdown = (
        "---\n"
        "tags:\n"
        "prompt: |-\n"
        "  Focus on action items\n"
        "---\n\n"
        "# Demo\n"
    )

    extracted = module.extract_prompt_metadata(markdown)

    assert extracted == "Focus on action items"


def test_extract_prompt_metadata_reads_inline_prompt_value() -> None:
    module = load_module()
    markdown = (
        "---\n"
        'prompt: "Focus on action items"\n'
        "---\n\n"
        "# Demo\n"
    )

    assert module.extract_prompt_metadata(markdown) == "Focus on action items"


def test_find_invalid_transcript_sections_returns_bad_part_indices() -> None:
    module = load_module()
    markdown = (
        "# Demo\n\n## Transcript\n\n"
        "**Speaker**: [00:01] okay\n"
        "**Speaker**: [00:02] fine\n"
        "**Speaker**: [00:03] yes\n"
        "**Speaker**: [00:04] sure\n"
        "**Speaker**: [00:05] done\n"
        "\n---\n\n"
        "It appears that you forgot to attach the audio file.\n"
        "\n---\n\n"
        "It looks like you forgot to attach the transcript.\n"
    )

    assert module.find_invalid_transcript_sections(markdown) == [2, 3]


def test_build_chunk_windows_prefers_friendly_nominal_size_and_uses_one_second_overlap() -> None:
    module = load_module()

    windows = module.build_chunk_windows(duration_seconds=3900, chunk_seconds=1800, overlap_seconds=1.0)

    assert windows == [(0.0, 1500.0), (1499.0, 1501.0), (2999.0, 901.0)]


def test_build_chunk_windows_uses_twenty_minute_chunks_for_forty_minutes() -> None:
    module = load_module()

    windows = module.build_chunk_windows(duration_seconds=2400, chunk_seconds=1800, overlap_seconds=1.0)

    assert windows == [(0.0, 1200.0), (1199.0, 1201.0)]


def test_build_chunk_windows_prefers_twenty_five_over_odd_even_splits() -> None:
    module = load_module()

    windows = module.build_chunk_windows(duration_seconds=5580, chunk_seconds=1800, overlap_seconds=1.0)

    assert windows == [(0.0, 1500.0), (1499.0, 1501.0), (2999.0, 1501.0), (4499.0, 1081.0)]


def test_build_chunk_windows_rejects_overlap_not_smaller_than_chunk() -> None:
    module = load_module()

    try:
        module.build_chunk_windows(duration_seconds=10, chunk_seconds=0.5, overlap_seconds=1.0)
    except ValueError as exc:
        assert "overlap_seconds must be smaller than chunk_seconds" in str(exc)
    else:
        raise AssertionError("Expected tiny chunks to be rejected")


def test_build_chunk_windows_absorbs_encoder_padding_without_extra_request():
    module = load_module()
    windows = module.build_chunk_windows(240.0065, 120)
    assert len(windows) == 2 and windows[0] == (0.0, 120.0)
    assert windows[1] == pytest.approx((119.0, 121.0065))
    windows = module.build_chunk_windows(2400.0065, 1800)
    assert len(windows) == 2 and windows[1][0] == 1199
    assert windows[-1][0] + windows[-1][1] == 2400.0065


def test_trim_transcript_to_chunk_duration_removes_model_continuation() -> None:
    module = load_module()
    transcript = (
        "**Anand**: [24:13] This is the real end of the chunk.\n\n"
        "**Shuku**: [25:12] Should I also do that peer feedback exercise?\n\n"
        "**Anand**: [25:15] Yes, absolutely."
    )

    assert module.normalize_chunk(transcript, (0, 25 * 60))[0] == (
        "**Anand**: [24:13] This is the real end of the chunk."
    )


def test_resolve_audio_path_returns_existing_path_as_is(tmp_path: Path) -> None:
    module = load_module()
    input_dir = tmp_path / "calls"
    input_dir.mkdir()
    other_dir = tmp_path / "elsewhere"
    other_dir.mkdir()
    audio_file = other_dir / "some call.opus"
    audio_file.write_bytes(b"audio")

    assert module.resolve_audio_path(str(audio_file), input_dir) == audio_file


def test_resolve_audio_path_matches_exact_stem_in_input_dir(tmp_path: Path) -> None:
    module = load_module()
    input_dir = tmp_path / "calls"
    input_dir.mkdir()
    (input_dir / "2026-05-29 Older.opus").write_bytes(b"audio")
    (input_dir / "2026-05-30 Older Extended.opus").write_bytes(b"audio")

    resolved = module.resolve_audio_path("2026-05-29 Older", input_dir)

    assert resolved == input_dir / "2026-05-29 Older.opus"


def test_resolve_audio_path_matches_exact_stem_with_extension(tmp_path: Path) -> None:
    module = load_module()
    input_dir = tmp_path / "calls"
    input_dir.mkdir()
    (input_dir / "2026-05-29 Older.opus").write_bytes(b"audio")

    resolved = module.resolve_audio_path("2026-05-29 Older.opus", input_dir)

    assert resolved == input_dir / "2026-05-29 Older.opus"


def test_resolve_audio_path_picks_most_recent_on_ambiguous_match(tmp_path: Path) -> None:
    module = load_module()
    input_dir = tmp_path / "calls"
    input_dir.mkdir()
    (input_dir / "2026-01-01 Ankor Call.opus").write_bytes(b"audio")
    (input_dir / "2026-06-01 Ankor Followup.opus").write_bytes(b"audio")

    resolved = module.resolve_audio_path("Ankor", input_dir)

    assert resolved == input_dir / "2026-06-01 Ankor Followup.opus"


def test_resolve_audio_path_matches_substring_anywhere_case_insensitively(tmp_path: Path) -> None:
    module = load_module()
    input_dir = tmp_path / "calls"
    input_dir.mkdir()
    (input_dir / "2026-08-18 Zainab Fifth Elephant.opus").write_bytes(b"audio")
    (input_dir / "2026-08-19 Unrelated Call.opus").write_bytes(b"audio")

    resolved = module.resolve_audio_path("fifth elephant", input_dir)

    assert resolved == input_dir / "2026-08-18 Zainab Fifth Elephant.opus"


def test_resolve_audio_path_prefers_exact_stem_over_substring_matches(tmp_path: Path) -> None:
    module = load_module()
    input_dir = tmp_path / "calls"
    input_dir.mkdir()
    (input_dir / "Ankor.opus").write_bytes(b"audio")
    (input_dir / "2026-06-01 Ankor Followup.opus").write_bytes(b"audio")

    resolved = module.resolve_audio_path("Ankor", input_dir)

    assert resolved == input_dir / "Ankor.opus"


def test_resolve_audio_path_rejects_missing_file(tmp_path: Path) -> None:
    module = load_module()
    input_dir = tmp_path / "calls"
    input_dir.mkdir()

    try:
        module.resolve_audio_path("does-not-exist", input_dir)
    except module.typer.BadParameter as exc:
        assert "No audio file matching" in str(exc)
    else:
        raise AssertionError("Expected missing file to be rejected")


def test_build_chunk_user_prompt_appends_part_context() -> None:
    module = load_module()

    prompt = module.build_chunk_user_prompt("Focus on action items", chunk_index=2, chunk_count=4)

    assert prompt.startswith("Focus on action items\n\n")
    assert "part 2/4 of a longer recording" in prompt


def test_resolve_prompts_uses_stored_prompt_as_user_context_and_note_prompt() -> None:
    module = load_module()

    prompts = module.resolve_prompts("System prompt text", "Stored patch prompt", None)

    assert prompts.system_prompt == "System prompt text"
    assert prompts.user_prompt == "Stored patch prompt"
    assert prompts.note_prompt == "Stored patch prompt"


def test_resolve_prompts_prefers_cli_prompt() -> None:
    module = load_module()

    prompts = module.resolve_prompts("System prompt text", "Stored patch prompt", "CLI prompt")

    assert prompts.system_prompt == "System prompt text"
    assert prompts.user_prompt == "CLI prompt"
    assert prompts.note_prompt == "CLI prompt"


def test_resolve_prompts_falls_back_to_system_prompt_with_no_stored_or_cli_prompt() -> None:
    module = load_module()

    prompts = module.resolve_prompts("System prompt text", None, None)

    assert prompts.user_prompt is None
    assert prompts.note_prompt == "System prompt text"


def test_resolve_prompts_omits_user_prompt_when_stored_prompt_matches_system_prompt() -> None:
    module = load_module()

    prompts = module.resolve_prompts("Same prompt", "Same prompt", None)

    assert prompts.user_prompt is None
    assert prompts.note_prompt == "Same prompt"


def test_script_creates_transcripts_for_multiple_audio_files(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call-a.opus"
    audio_path.write_bytes(b"fake audio")
    second_audio_path = input_dir / "call-b.opus"
    second_audio_path.write_bytes(b"fake audio")
    prompt_file.write_text(
        textwrap.dedent(
            """
            Intro text

            ```markdown
            Use this exact prompt
            ```
            """
        ),
        encoding="utf-8",
    )

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "60"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        second_audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "created call-a.md" in result.stdout
    assert "created call-b.md" in result.stdout
    assert "tokens=150 cost=$0.000800 total_cost=$0.000800" in result.stdout

    log_text = log_path.read_text(encoding="utf-8")
    assert "APIKEY\ttest-key-from-dotenv" in log_text
    assert f"AUDIO\t{audio_path}" in log_text
    assert f"AUDIO\t{second_audio_path}" in log_text
    assert "SYSTEM_PROMPT\tUse this exact prompt" in log_text
    assert "USER_PROMPT\t" not in log_text

    call_a = (output_dir / "call-a.md").read_text(encoding="utf-8")
    assert call_a.startswith(
        "---\n"
        "model: gemini-3-flash-preview\n"
        "cost: 0.000800\n"
        "prompt: |-\n"
        "  Use this exact prompt\n"
        "transcription_status: complete\n"
    )
    assert "## Transcript\n\n**Speaker**: [00:01] Transcript for call-a.opus line 1" in call_a
    call_b = (output_dir / "call-b.md").read_text(encoding="utf-8")
    assert "## Transcript\n\n**Speaker**: [00:01] Transcript for call-b.opus line 1" in call_b

    second = run_script(
        script_path, audio_path, "--out", output_dir, "--system-prompt", prompt_file, env=env, cwd=tmp_path
    )
    assert second.returncode == 0, second.stderr
    assert log_path.read_text(encoding="utf-8") == log_text
    assert "Already transcribed: call-a.md" in second.stdout


def test_script_stops_after_first_failed_audio(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_paths = [input_dir / f"call-{suffix}.opus" for suffix in ("a", "b", "c")]
    for audio_path in audio_paths:
        audio_path.write_bytes(b"fake audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["GEMINI_API_KEY"] = "test-key"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_GENAI_ERROR_FILES"] = "call-b.opus"
    env["FAKE_FFPROBE_DURATION"] = "60"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()

    result = run_script(
        script_path,
        *audio_paths,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert "forced error for call-b.opus" in result.stderr
    assert (output_dir / "call-a.md").exists()
    assert "transcription_status: incomplete" in (output_dir / "call-b.md").read_text()
    assert not (output_dir / "call-c.md").exists()
    audio_requests = [
        Path(line.split("\t", 1)[1]).name
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("AUDIO\t")
    ]
    assert audio_requests == ["call-a.opus", "call-b.opus"]


def test_script_looks_up_audio_by_stem_in_default_input_dir(tmp_path: Path) -> None:
    source_script = Path(__file__).resolve().parents[1] / "call"
    script_path = tmp_path / "call.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    missing_prompt_file = tmp_path / "missing-default-prompt.md"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "2026-05-29 Older.opus").write_bytes(b"audio")

    script_text = source_script.read_text(encoding="utf-8")
    script_text = script_text.replace(
        'Path("/home/sanand/Documents/calls")', f'Path({str(input_dir)!r})', 1
    )
    script_text = script_text.replace(
        'Path("/home/sanand/Dropbox/notes/transcripts")', f'Path({str(output_dir)!r})', 1
    )
    script_text = script_text.replace(
        'Path("/home/sanand/code/blog/pages/prompts/transcribe-call-recording.md")',
        f'Path({str(missing_prompt_file)!r})',
        1,
    )
    script_path.write_text(script_text, encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, "2026-05-29 Older", "--prompt", "Focus here", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "created 2026-05-29 Older.md" in result.stdout
    log_text = log_path.read_text(encoding="utf-8")
    assert f"AUDIO\t{input_dir / '2026-05-29 Older.opus'}" in log_text
    assert "USER_PROMPT\tFocus here" in log_text


def test_script_list_changes_reports_actions_without_probing_or_writing(tmp_path: Path) -> None:
    source_script = Path(__file__).resolve().parents[1] / "call"
    script_path = tmp_path / "call.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    bin_dir = tmp_path / "bin"
    ffprobe_log_path = tmp_path / "ffprobe.log"

    input_dir.mkdir()
    output_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "ffprobe").write_text(
        f"#!/usr/bin/env bash\nprintf called > {ffprobe_log_path}\n", encoding="utf-8"
    )
    (bin_dir / "ffprobe").chmod(0o755)
    for name in ("create.opus", "done.opus", "update.wav"):
        (input_dir / name).write_bytes(b"audio")
    (output_dir / "done.md").write_text(
        "# done\n\n## Transcript\n\nExisting transcript\n", encoding="utf-8"
    )
    existing_update = "# update\n\n## Notes\n\nNeeds transcript\n"
    (output_dir / "update.md").write_text(existing_update, encoding="utf-8")

    script_text = source_script.read_text(encoding="utf-8")
    script_text = script_text.replace(
        'Path("/home/sanand/Documents/calls")', f'Path({str(input_dir)!r})', 1
    )
    script_path.write_text(script_text, encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, "--out", output_dir, "--list-changes", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        f"create\t{input_dir / 'create.opus'}\t{output_dir / 'create.md'}",
        f"update\t{input_dir / 'update.wav'}\t{output_dir / 'update.md'}",
    ]
    assert result.stderr.strip().splitlines()[-1] == "changes=2"
    assert not (output_dir / "create.md").exists()
    assert (output_dir / "update.md").read_text(encoding="utf-8") == existing_update
    assert not ffprobe_log_path.exists()


def test_script_list_changes_rejects_audio_argument(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")

    result = run_script(script_path, audio_path, "--out", output_dir, "--list-changes", cwd=tmp_path)

    assert result.returncode != 0
    assert "--list-changes takes no AUDIO argument" in (result.stderr + result.stdout)


def test_script_requires_audio_argument_without_list_changes(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"

    result = run_script(script_path, cwd=tmp_path)

    assert result.returncode != 0
    assert "Missing argument" in (result.stderr + result.stdout)


def test_script_reports_invalid_existing_markdown(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"

    input_dir.mkdir()
    output_dir.mkdir()

    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "call.md").write_bytes(b"\xff\xfe")

    result = run_script(script_path, audio_path, "--out", output_dir)

    assert result.returncode == 1
    assert "failed to read existing Markdown" in result.stderr


def test_script_reports_duplicate_transcript_sections(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"

    input_dir.mkdir()
    output_dir.mkdir()

    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "call.md").write_text(
        "# call\n\n## Transcript\n\nFirst\n\n## Notes\n\nKeep\n\n## Transcript\n\nSecond\n",
        encoding="utf-8",
    )

    result = run_script(script_path, audio_path, "--out", output_dir)

    assert result.returncode == 1
    assert "multiple ## Transcript sections" in result.stderr


def test_script_requires_gemini_api_key_when_transcription_needed(tmp_path: Path) -> None:
    script_path = tmp_path / "call.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"

    shutil.copyfile(Path(__file__).resolve().parents[1] / "call", script_path)
    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")

    env = os.environ.copy()
    bins = tmp_path / "bin"
    write_fake_ffmpeg_tools(bins)
    env["PATH"] = f"{bins}:{env['PATH']}"
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, audio_path, "--out", output_dir, env=env, cwd=tmp_path)

    assert result.returncode == 1
    assert "GEMINI_API_KEY is not set" in result.stderr


def test_script_sends_user_prompt_with_small_audio_file(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "test.opus"
    audio_path.write_bytes(
        (Path(__file__).resolve().parents[1] / "tests" / "test.opus").read_bytes()
    )
    prompt_file.write_text("System prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--prompt",
        "Focus on action items",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    transcript = (output_dir / "test.md").read_text(encoding="utf-8")
    assert "Transcript for test.opus" in transcript
    assert "prompt: |-" in transcript
    assert "  Focus on action items" in transcript

    log_text = log_path.read_text(encoding="utf-8")
    assert f"AUDIO\t{audio_path}" in log_text
    assert "SYSTEM_PROMPT\tSystem prompt text" in log_text
    assert "USER_PROMPT\tFocus on action items" in log_text
    assert "tokens=150 cost=$0.000800 total_cost=$0.000800" in result.stdout


def test_script_uses_existing_frontmatter_prompt_for_pending_transcript(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "test.opus"
    audio_path.write_bytes(
        (Path(__file__).resolve().parents[1] / "tests" / "test.opus").read_bytes()
    )
    (output_dir / "test.md").write_text(
        "---\n"
        "prompt: Pending note context from YAML\n"
        "---\n\n"
        "# test\n\n"
        "- Existing notes stay intact.\n\n"
        "## Transcript\n",
        encoding="utf-8",
    )
    prompt_file.write_text("System prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path, audio_path, "--out", output_dir, "--system-prompt", prompt_file, env=env, cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    transcript = (output_dir / "test.md").read_text(encoding="utf-8")
    assert "- Existing notes stay intact." in transcript
    assert "Transcript for test.opus" in transcript
    assert "prompt: |-\n  Pending note context from YAML" in transcript

    log_text = log_path.read_text(encoding="utf-8")
    assert "SYSTEM_PROMPT\tSystem prompt text" in log_text
    assert "USER_PROMPT\tPending note context from YAML" in log_text


def test_script_skips_existing_prompt_metadata_without_transcribing(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    log_path = tmp_path / "genai.log"
    existing_note = (
        "---\n"
        "prompt: |-\n"
        "  Call-specific historical prompt\n"
        "---\n\n"
        "# call\n\n"
        "## Transcript\n\n"
        "**Speaker**: [00:01] line 1\n"
        "**Speaker**: [00:02] line 2\n"
        "**Speaker**: [00:03] line 3\n"
        "**Speaker**: [00:04] line 4\n"
        "**Speaker**: [00:05] line 5\n"
    )

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "call.md").write_text(existing_note, encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, audio_path, "--out", output_dir, env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Already transcribed: call.md" in result.stdout
    assert (output_dir / "call.md").read_text(encoding="utf-8") == existing_note
    assert not log_path.exists()


def test_script_updates_prompt_metadata_when_prompt_is_explicit(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "call.md").write_text(
        "# call\n\n## Transcript\n\n**Speaker**: [00:01] line 1\n",
        encoding="utf-8",
    )
    prompt_file.write_text("System prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--prompt",
        "Explicit metadata prompt",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "updated prompt metadata: call.md" in result.stdout
    transcript = (output_dir / "call.md").read_text(encoding="utf-8")
    assert "prompt: |-\n  Explicit metadata prompt" in transcript
    assert "**Speaker**: [00:01] line 1" in transcript
    assert not log_path.exists()


def test_script_force_retranscribes_existing_note(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "call.md").write_text(
        "# call\n\n## Transcript\n\nOld transcript text\n",
        encoding="utf-8",
    )
    prompt_file.write_text("System prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--force",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "updated call.md" in result.stdout
    transcript = (output_dir / "call.md").read_text(encoding="utf-8")
    assert "Old transcript text" not in transcript
    assert "Transcript for call.opus line 1" in transcript


def test_script_force_ignores_cached_chunk_transcripts(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"
    cache_dir = tmp_path / "cache"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "long.opus"
    audio_path.write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["TRANSCRIBE_CALLS_CACHE_DIR"] = str(cache_dir)
    env.pop("GEMINI_API_KEY", None)

    initial = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )
    assert initial.returncode == 0, initial.stderr
    assert len(list(cache_dir.glob("chunk-*.json"))) == 3

    (output_dir / "long.md").write_text(
        "# long\n\n## Transcript\n\nOld transcript text\n", encoding="utf-8"
    )
    env["FAKE_GENAI_TRANSCRIPT_TEXT"] = "\n".join(
        f"**Speaker**: [00:0{index}] Forced transcript line {index}" for index in range(1, 6)
    )
    forced = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "30",
        "--force",
        env=env,
        cwd=tmp_path,
    )

    assert forced.returncode == 0, forced.stderr
    audio_requests = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.startswith("AUDIO\t")]
    assert len(audio_requests) == 6
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "Old transcript text" not in transcript
    assert "Forced transcript line 1" in transcript


def test_script_chunks_long_audio_and_joins_chunk_transcripts(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    ffmpeg_log_path = tmp_path / "ffmpeg.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "long.opus"
    audio_path.write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFMPEG_LOG"] = str(ffmpeg_log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["FAKE_GENAI_RESPONSE_BY_FILE"] = json.dumps(
        {
            "long.part001.opus": "\n".join(
                [
                    *(
                        f"**Speaker**: [00:0{i}] Transcript for long.part001.opus line {i}"
                        for i in range(1, 6)
                    ),
                    "**Speaker**: [25:12] Spurious continuation beyond the chunk",
                ]
            )
        }
    )
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["TRANSCRIBE_CALLS_CACHE_DIR"] = str(tmp_path / "cache")
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "[1/3] transcribing long.opus" in result.stdout
    assert "[2/3] transcribing long.opus" in result.stdout
    assert "[3/3] transcribing long.opus" in result.stdout
    assert "tokens=450 cost=$0.002400 total_cost=$0.002400" in result.stdout
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "Transcript for long.part001.opus line 1" in transcript
    assert "\n\n---\n\n" in transcript
    assert "Transcript for long.part002.opus line 1" in transcript
    assert "Transcript for long.part003.opus line 1" in transcript
    assert "Spurious continuation" not in transcript

    ffmpeg_log = ffmpeg_log_path.read_text(encoding="utf-8").splitlines()
    assert len(ffmpeg_log) == 3
    assert "-ss 0.000 -t 1500.000 -i" in ffmpeg_log[0]
    assert "-ss 1499.000 -t 1501.000 -i" in ffmpeg_log[1]
    assert "-ss 2999.000 -t 901.000 -i" in ffmpeg_log[2]

    genai_log = log_path.read_text(encoding="utf-8")
    assert "AUDIO\t" in genai_log
    assert "long.part001.opus" in genai_log
    assert "long.part002.opus" in genai_log
    assert "long.part003.opus" in genai_log
    assert "USER_PROMPT\tThis audio is part 1/3 of a longer recording." in genai_log
    assert "This audio is part 2/3 of a longer recording." in genai_log
    assert "This audio is part 3/3 of a longer recording." in genai_log
    assert "Spurious continuation" not in genai_log


def test_script_resumes_chunked_transcription_from_durable_cache(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"
    cache_dir = tmp_path / "cache"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "long.opus"
    audio_path.write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")
    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["FAKE_GENAI_ERROR_FILES"] = "long.part003.opus"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["TRANSCRIBE_CALLS_CACHE_DIR"] = str(cache_dir)
    env.pop("GEMINI_API_KEY", None)

    first = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )
    assert first.returncode == 1
    assert "forced error for long.part003.opus" in first.stderr
    assert len(list(cache_dir.glob("chunk-*.json"))) == 3

    env.pop("FAKE_GENAI_ERROR_FILES")
    second = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )
    assert second.returncode == 0, second.stderr
    assert "tokens=150 cost=$0.000800 total_cost=$0.000800" in second.stdout
    genai_log = log_path.read_text(encoding="utf-8")
    audio_requests = [line for line in genai_log.splitlines() if line.startswith("AUDIO\t")]
    assert len(audio_requests) == 4
    assert sum("long.part001.opus" in line for line in audio_requests) == 1
    assert sum("long.part002.opus" in line for line in audio_requests) == 1
    assert sum("long.part003.opus" in line for line in audio_requests) == 2
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "Transcript for long.part001.opus line 1" in transcript
    assert "Transcript for long.part002.opus line 1" in transcript
    assert "Transcript for long.part003.opus line 1" in transcript


def test_legacy_cache_is_readable_with_unknown_historical_cost(tmp_path):
    module = load_module()
    cache = tmp_path / "chunk-legacy.json"
    cache.write_text('{"transcript": "**A**: [00:00] Cached words"}')
    result = module.read_cached_chunk(cache)
    assert result.transcript == "**A**: [00:00] Cached words"
    assert result.usage.total_tokens == 0
    assert module.read_chunk_state(cache)["attempts"] == [{"usage": None, "legacy": True}]


def test_script_auto_retries_and_resolves_invalid_chunk(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "long.opus"
    audio_path.write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    # A persistently invalid model response is retried once, then saved with a warning.
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["TRANSCRIBE_CALLS_CACHE_DIR"] = str(tmp_path / "cache")
    env["FAKE_GENAI_RESPONSE_BY_FILE"] = json.dumps(
        {"long.part002.opus": "It appears that you forgot to attach the audio file."}
    )
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1, result.stderr
    assert "WARNING long.opus: section 2/3: Model response contains no speaker lines" in result.stderr
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "Transcript for long.part001.opus line 1" in transcript
    assert "It appears that you forgot to attach the audio file." in transcript
    genai_log = log_path.read_text(encoding="utf-8")
    # part002 is transcribed twice: once in the main pass, once on the automatic retry.
    assert sum("long.part002.opus" in line for line in genai_log.splitlines() if line.startswith("AUDIO\t")) == 2


def test_script_patch_retranscribes_invalid_sections(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "long.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "long.md").write_text(
        "# long\n\n## Transcript\n\n"
        "**Speaker**: [00:01] first line\n"
        "**Speaker**: [00:02] first line\n"
        "**Speaker**: [00:03] first line\n"
        "**Speaker**: [00:04] first line\n"
        "**Speaker**: [00:05] first line\n"
        "\n\n---\n\n"
        "It appears that you forgot to attach the audio file.\n"
        "\n\n---\n\n"
        "It looks like you forgot to attach the raw transcript.\n",
        encoding="utf-8",
    )
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["FAKE_GENAI_RESPONSE_BY_FILE"] = json.dumps(
        {
            "long.part002.opus": "\n".join(
                f"**Speaker**: [00:0{index}] repaired second {index}"
                for index in range(1, 6)
            ),
            "long.part003.opus": "\n".join(
                f"**Speaker**: [00:0{index}] repaired third {index}"
                for index in range(1, 6)
            ),
        }
    )
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "30",
        "--patch",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "patched section(s) 2,3: long.md" in result.stdout
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "repaired second 1" in transcript
    assert "repaired third 1" in transcript
    assert "It appears that you forgot to attach the audio file." not in transcript
    assert "It looks like you forgot to attach the raw transcript." not in transcript
    genai_log = log_path.read_text(encoding="utf-8")
    assert "long.part001.opus" not in genai_log
    assert "long.part002.opus" in genai_log
    assert "long.part003.opus" in genai_log


def test_script_patch_reports_when_no_invalid_sections(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "call.md").write_text(
        "# call\n\n## Transcript\n\n"
        "**Speaker**: [00:01] line 1\n"
        "**Speaker**: [00:02] line 2\n"
        "**Speaker**: [00:03] line 3\n"
        "**Speaker**: [00:04] line 4\n"
        "**Speaker**: [00:05] line 5\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, audio_path, "--out", output_dir, "--patch", env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "No invalid transcript sections found in call.md" in result.stdout


def test_script_dry_run_reports_duration_and_chunks_without_side_effects(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    ffmpeg_log_path = tmp_path / "ffmpeg.log"
    genai_log_path = tmp_path / "genai.log"
    existing_note = "# long\n\n## Notes\n\nNeeds transcript\n"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "long.opus"
    audio_path.write_bytes(b"audio")
    (output_dir / "long.md").write_text(existing_note, encoding="utf-8")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_FFMPEG_LOG"] = str(ffmpeg_log_path)
    env["FAKE_GENAI_LOG"] = str(genai_log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--dry-run",
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "duration=3900.0s chunks=3" in result.stdout
    assert "dry-run update long.opus -> long.md" in result.stdout
    assert (output_dir / "long.md").read_text(encoding="utf-8") == existing_note
    assert not ffmpeg_log_path.exists()
    assert not genai_log_path.exists()


def test_load_google_pricing_caches_successful_fetch(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    source_prices_path = tmp_path / "source-prices.json"
    cache_path = tmp_path / "cache" / "google-prices.json"
    write_fake_google_prices(source_prices_path)
    monkeypatch.setenv("TRANSCRIBE_CALLS_PRICES_URL", source_prices_path.as_uri())
    monkeypatch.setenv("TRANSCRIBE_CALLS_PRICES_CACHE", str(cache_path))

    pricing = module.load_google_pricing()

    assert "gemini-3-flash-preview" in pricing
    assert cache_path.is_file()
    assert json.loads(cache_path.read_text(encoding="utf-8"))["models"]


def test_load_google_pricing_falls_back_to_cache_on_fetch_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    module = load_module()
    cache_path = tmp_path / "cache" / "google-prices.json"
    cache_path.parent.mkdir(parents=True)
    write_fake_google_prices(cache_path)
    os.utime(cache_path, (0, 0))
    monkeypatch.setenv("TRANSCRIBE_CALLS_PRICES_URL", (tmp_path / "does-not-exist.json").as_uri())
    monkeypatch.setenv("TRANSCRIBE_CALLS_PRICES_CACHE", str(cache_path))

    pricing = module.load_google_pricing()

    assert "gemini-3-flash-preview" in pricing
    assert "using cached copy" in capsys.readouterr().err


def test_load_google_pricing_raises_when_fetch_fails_without_cache(
    tmp_path: Path, monkeypatch
) -> None:
    module = load_module()
    monkeypatch.setenv("TRANSCRIBE_CALLS_PRICES_URL", (tmp_path / "does-not-exist.json").as_uri())
    monkeypatch.setenv("TRANSCRIBE_CALLS_PRICES_CACHE", str(tmp_path / "cache" / "google-prices.json"))

    try:
        module.load_google_pricing()
    except RuntimeError as exc:
        assert "Failed to load Google pricing data" in str(exc)
    else:
        raise AssertionError("Expected a fetch failure with no cache to raise")


def test_script_rejects_chunk_size_at_or_below_overlap(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "call"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "tiny.opus"
    audio_path.write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        audio_path,
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        "--chunk",
        "0.01",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert "greater than 1/60 minute" in result.stderr


def test_split_transcript_preserves_empty_final_chunk() -> None:
    module = load_module()
    assert module.split_transcript_parts("first" + module.TRANSCRIPT_PART_SEPARATOR) == ["first", ""]


def test_trim_global_chunk_timestamps_without_removing_real_audio() -> None:
    module = load_module()
    transcript = "\n".join([
        "**Speaker**: [20:00] Current audio starts here",
        "**Speaker**: [35:54] Current audio ends here",
        "**Speaker**: [36:00] Spurious continuation",
    ])
    assert module.normalize_chunk(transcript, (1199, 956.748583))[0] == (
        "**Speaker**: [00:01] Current audio starts here\n"
        "**Speaker**: [15:55] Current audio ends here"
    )
    # Local timestamps and unrelated out-of-range continuations retain the existing rule.
    assert module.normalize_chunk("**Speaker**: [00:03] Local", (1199, 956))[0] == "**Speaker**: [00:03] Local"
    preserved, warning = module.normalize_chunk("**Speaker**: [25:00] Ambiguous", (1199, 956))
    assert preserved == "**Speaker**: [25:00] Ambiguous" and "Ambiguous" in warning


@pytest.mark.parametrize("bad", ["Not a transcript"])
def test_retry_final_chunk_before_joining_and_cache_recovery(tmp_path, monkeypatch, capsys, bad) -> None:
    module = load_module()
    audio = tmp_path / "call.opus"
    audio.write_bytes(b"audio")
    valid = "\n".join(f"**Speaker**: [00:0{i}] line {i}" for i in range(5))
    responses = iter([valid, bad, valid])
    requests = []
    def transcribe(path, **kwargs):
        requests.append(kwargs["user_prompt"])
        return module.TranscriptionResult(next(responses), module.UsageCost(1, 1, 2, 0.1))
    monkeypatch.setattr(module, "transcribe_single_audio", transcribe)
    monkeypatch.setattr(module, "split_audio_chunks", lambda *args, **kwargs: [audio, audio])
    kwargs = dict(system_prompt="Transcribe", user_prompt=None, model="test", client=object(),
                  pricing={}, chunk_minutes=20, windows=[(0, 1200), (1199, 956)], cache_dir=tmp_path / "cache")
    result = module.transcribe_audio(audio, **kwargs)
    assert module.split_transcript_parts(result.transcript) == [valid, module.render_chunk_timestamps(valid, 1199)]
    assert not result.warnings
    assert result.usage.total_tokens == 6
    assert result.usage.cost_usd == pytest.approx(0.3)
    assert requests[1] == requests[2]  # Retry keeps prior chunk context.
    assert "retrying section 2/2" in capsys.readouterr().err
    resumed = module.transcribe_audio(audio, **kwargs)
    assert resumed.transcript == result.transcript
    assert resumed.usage.total_tokens == 0
    assert len(requests) == 3


def test_empty_gemini_output_reports_finish_reason_and_action(monkeypatch) -> None:
    module = load_module()
    response = SimpleNamespace(text=None, candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")], prompt_feedback=None)
    client = SimpleNamespace(files=SimpleNamespace(upload=lambda **kw: "file"),
        chats=SimpleNamespace(create=lambda **kw: SimpleNamespace(send_message=lambda contents: response)))
    monkeypatch.setattr(module, "load_genai", lambda: SimpleNamespace(
        types=SimpleNamespace(GenerateContentConfig=lambda **kw: None), errors=SimpleNamespace(APIError=RuntimeError)))
    monkeypatch.setattr(module, "calculate_usage_cost", lambda *a, **kw: module.UsageCost(0, 0, 0, 0))
    result = module.transcribe_single_audio(Path("audio.opus"), "Transcribe", None, "model", client, {})
    assert "MAX_TOKENS" in result.error and "reduce --chunk" in result.error
    assert result.usage.cost_usd == 0


@pytest.mark.parametrize("failure, action", [
    (PermissionError(13, "Permission denied", "/locked/note.md"), "Grant write/read access to /locked/note.md"),
    (OSError(30, "Read-only file system", "/locked/cache.json"), "Check filesystem access/free space"),
    (IndexError("list assignment index out of range"), "Save this traceback and the command and report the bug"),
])
def test_unhandled_failure_reports_cause_and_action(monkeypatch, failure, action) -> None:
    from typer.testing import CliRunner

    module = load_module()
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(module, "process_audio", fail)
    result = CliRunner().invoke(module.app, ["example"])
    assert result.exit_code == 1
    assert str(failure) in result.output
    assert action in result.output
    if isinstance(failure, IndexError):
        assert "Traceback" in result.output


def test_corrupt_cache_reports_exact_file_to_repair(tmp_path) -> None:
    module = load_module()
    cache = tmp_path / "chunk-bad.json"
    cache.write_text('{"transcript": []}')
    with pytest.raises(RuntimeError, match="Invalid chunk cache.*chunk-bad.json.*Move this file aside"):
        module.read_cached_chunk(cache)


def test_persistently_empty_final_chunk_remains_patchable(tmp_path, monkeypatch) -> None:
    module = load_module()
    audio = tmp_path / "call.opus"
    audio.write_bytes(b"audio")
    valid = "\n".join(f"**Speaker**: [00:0{i}] line {i}" for i in range(5))
    responses = iter([valid, "**Speaker**: [25:00] Bad", "**Speaker**: [25:00] Bad"])
    monkeypatch.setattr(module, "transcribe_single_audio", lambda *a, **kw: module.TranscriptionResult(
        next(responses), module.UsageCost(1, 1, 2, 0.1)))
    monkeypatch.setattr(module, "split_audio_chunks", lambda *a, **kw: [audio, audio])
    result = module.transcribe_audio(audio, "Transcribe", None, "test", object(), {}, 20,
        windows=[(0, 1200), (1199, 956)], cache_dir=tmp_path / "cache")
    note = module.render_new_document("Call", result.transcript, "Transcribe")
    assert [warning.section_index for warning in result.warnings] == [2]
    assert "**Speaker**: [25:00] Bad" in note
    assert len(list((tmp_path / "cache").glob("*.json"))) == 2
    repaired = module.patch_transcript_section(note, 2, valid)
    assert module.find_invalid_transcript_sections(repaired) == []


@pytest.fixture
def revision_case(tmp_path):
    """Run the real CLI against deterministic model responses and isolated state."""
    audio = tmp_path / "meeting.opus"
    audio.write_bytes(b"audio")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Transcribe every turn")
    packages = tmp_path / "pydeps"
    write_fake_google_genai(packages)
    bins = tmp_path / "bin"
    write_fake_ffmpeg_tools(bins)
    prices = tmp_path / "prices.json"
    write_fake_google_prices(prices)
    env = os.environ.copy()
    env.update(PYTHONPATH=str(packages), PATH=f"{bins}:{env['PATH']}", GEMINI_API_KEY="test",
        FAKE_GENAI_LOG=str(tmp_path / "requests.log"), FAKE_FFPROBE_DURATION="2400",
        TRANSCRIBE_CALLS_PRICES_URL=prices.as_uri(), TRANSCRIBE_CALLS_CACHE_DIR=str(tmp_path / "cache"))
    output = tmp_path / "notes"
    def run(*args):
        return run_script(Path(__file__).resolve().parents[1] / "call", audio,
            "--out", output, "--system-prompt", prompt, *args, env=env, cwd=tmp_path)
    return SimpleNamespace(root=tmp_path, audio=audio, output=output, note=output / "meeting.md", env=env, run=run)


def test_revision_dry_run_prompt_update_never_writes(revision_case):
    c = revision_case
    c.output.mkdir()
    c.note.write_text('---\nprompt: old\n---\n\n## Transcript\n\n**A**: [00:00] Existing words\n')
    before = {p: p.read_bytes() for p in c.root.rglob('*') if p.is_file()}
    result = c.run('--dry-run', '--prompt', 'new')
    assert result.returncode == 0, result.stderr
    assert {p: p.read_bytes() for p in c.root.rglob('*') if p.is_file() and 'runs' not in p.parts} == before


def test_revision_short_transcript_cumulative_and_cached(revision_case):
    c = revision_case
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = '**A**: [00:03] Hello\n**B**: [00:08] Bye'
    first = c.run()
    assert first.returncode == 0, first.stderr
    note = c.note.read_text()
    assert '**A**: [20:02] Hello' in note
    assert 'transcription_status: complete' in note
    c.note.unlink()
    second = c.run()
    assert second.returncode == 0, second.stderr
    requests = (c.root / 'requests.log').read_text().splitlines()
    assert sum(line.startswith('AUDIO\t') for line in requests) == 2
    assert 'tokens=0' in second.stdout
    assert c.note.read_text() == note


def test_revision_fenced_transcript_repaired_without_paid_retry(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = '```markdown\n**A**: [00:00] One turn\n```'
    result = c.run()
    assert result.returncode == 0, result.stderr
    assert '```' not in c.note.read_text()
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 1
    assert len(list((c.root / 'cache').glob('chunk-*.json'))) == 1


def test_revision_failed_resume_keeps_paid_attempts_and_pending_note(revision_case):
    c = revision_case
    c.env['FAKE_GENAI_ERROR_FILES'] = 'meeting.part002.opus'
    first = c.run()
    assert first.returncode == 1
    assert c.note.exists()
    assert 'transcription_status: incomplete' in c.note.read_text()
    records = [json.loads(line) for line in (c.root / 'cache' / 'run.jsonl').read_text().splitlines()]
    assert any(row['event'] == 'attempt' and row.get('usage', {}).get('total_tokens') == 150 for row in records)
    assert any(row['event'] == 'attempt_error' and row['usage'] is None for row in records)
    for cache in (c.root / 'cache').glob('chunk-*.json'):
        os.utime(cache, (100, 100))
    c.env.pop('FAKE_GENAI_ERROR_FILES')
    resumed = c.run()
    assert resumed.returncode == 0, resumed.stderr
    assert 'transcription_status: complete' in c.note.read_text()
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 3
    assert 'cost: unknown' in c.note.read_text()  # Failed request billing cannot be inferred.


def test_revision_ambiguous_timestamps_preserve_text_without_retry(revision_case):
    c = revision_case
    c.env['FAKE_GENAI_RESPONSE_BY_FILE'] = json.dumps({'meeting.part002.opus':
        '**A**: [26:38] First utterance after a long silence\n**B**: [35:50] Last utterance'})
    result = c.run()
    assert result.returncode == 1
    assert 'First utterance after a long silence' in c.note.read_text()
    assert 'timestamp' in result.stderr.lower()
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 2
    assert 'transcription_status: incomplete' in c.note.read_text()


def test_revision_preflight_output_failure_makes_no_paid_request(revision_case, monkeypatch):
    from typer.testing import CliRunner
    c = revision_case
    module = load_module()
    monkeypatch.setattr(module, 'plan_audio_chunks', lambda *a, **kw: (20, [(0, 20)]))
    monkeypatch.setenv('TRANSCRIBE_CALLS_CACHE_DIR', str(c.root / 'cache'))
    def denied(*args, **kwargs):
        raise PermissionError(13, 'Permission denied', str(c.note))
    monkeypatch.setattr(module, 'preflight_write', denied)
    monkeypatch.setattr(module, 'build_client', lambda: pytest.fail('Paid client created before preflight'))
    result = CliRunner().invoke(module.app, [str(c.audio), '--out', str(c.output)])
    assert result.exit_code == 1
    assert 'Permission denied' in result.output


def test_revision_mixed_modality_cost_with_cached_audio():
    module = load_module()
    response = SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=1100, cached_content_token_count=200, candidates_token_count=100,
        thoughts_token_count=50, total_token_count=1250,
        prompt_tokens_details=[SimpleNamespace(modality='AUDIO', token_count=1000), SimpleNamespace(modality='TEXT', token_count=100)],
        cache_tokens_details=[SimpleNamespace(modality='AUDIO', token_count=200)]))
    price = {'test': {'input': .5, 'input_audio': 1., 'input_cached': .05, 'input_cached_audio': .1, 'output': 3.}}
    usage = module.calculate_usage_cost(response, 'test', price)
    assert usage.cost_usd == pytest.approx((800 + 50 + 20 + 450) / 1e6)


def test_revision_known_local_timestamp_shift_ignores_inference_guard():
    module = load_module()
    assert module.render_chunk_timestamps('**A**: [20:00] Late first speech', 1499) == '**A**: [44:59] Late first speech'
    assert module.render_chunk_timestamps('**A**: [00:02 - 00:04] Range', 59) == '**A**: [01:01 - 01:03] Range'


def test_revision_atomic_save_failure_preserves_existing_note(tmp_path, monkeypatch):
    module = load_module()
    note = tmp_path / 'note.md'
    note.write_text('Original notes')
    def fail(*args, **kwargs):
        raise OSError('replace failed')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError, match='replace failed'):
        module.atomic_write(note, 'New notes')
    assert note.read_text() == 'Original notes'
    assert list(tmp_path.iterdir()) == [note]


def test_revision_silent_chunks_are_complete_and_never_retried(revision_case):
    c = revision_case
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = '[Silence]'
    result = c.run()
    assert result.returncode == 0, result.stderr
    assert 'transcription_status: complete' in c.note.read_text()
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 2


def test_revision_empty_response_keeps_paid_usage_and_does_not_retry(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = ''
    failed = c.run()
    assert failed.returncode == 1
    assert 'Gemini returned empty output' in failed.stderr
    assert 'cost: 0.000800' in c.note.read_text()
    state = json.loads(next((c.root / 'cache').glob('chunk-*.json')).read_text())
    assert state['raw_transcript'] == '' and state['status'] == 'failed'
    assert state['attempts'][0]['usage']['total_tokens'] == 150
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 1
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = '**A**: [00:01] Recovered'
    assert c.run().returncode == 0
    assert 'cost: 0.001600' in c.note.read_text()


def test_revision_force_replacement_cost_excludes_previous_generation(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    assert c.run('--force').returncode == 0
    assert 'cost: 0.000800' in c.note.read_text()
    ledger = [json.loads(line) for line in (c.root / 'cache' / 'run.jsonl').read_text().splitlines()]
    assert sum(row['event'] == 'attempt' for row in ledger) == 2


def test_revision_failed_force_preserves_previous_complete_note(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    original = c.note.read_bytes()
    c.env['FAKE_GENAI_ERROR_FILES'] = 'meeting.opus'
    failed = c.run('--force')
    assert failed.returncode == 1
    assert c.note.read_bytes() == original
    assert 'transcription_status: incomplete' in c.note.with_suffix('.incomplete.md').read_text()


def test_revision_patch_shifts_once_and_preserves_other_sections(revision_case):
    c = revision_case
    c.env['FAKE_GENAI_RESPONSE_BY_FILE'] = json.dumps({'meeting.part002.opus': 'Not a transcript'})
    assert c.run().returncode == 1
    module = load_module()
    before = module.TRANSCRIPT_SECTION_RE.search(c.note.read_text())['body']
    first = module.split_transcript_parts(before)[0]
    c.env['FAKE_GENAI_RESPONSE_BY_FILE'] = json.dumps({'meeting.part002.opus': '**B**: [00:03] Repaired'})
    patched = c.run('--patch')
    assert patched.returncode == 0, patched.stderr
    after = module.split_transcript_parts(module.TRANSCRIPT_SECTION_RE.search(c.note.read_text())['body'])
    assert after == [first, '**B**: [20:02] Repaired']
    assert 'cost: 0.003200' in c.note.read_text()  # One first chunk, two failed responses, one patch.
    requests_before = (c.root / 'requests.log').read_text()
    assert c.run('--patch').returncode == 0
    assert (c.root / 'requests.log').read_text() == requests_before


def test_revision_global_timestamp_response_is_not_shifted_twice(revision_case):
    c = revision_case
    c.env["FAKE_FFPROBE_DURATION"] = "2155"
    c.env['FAKE_GENAI_RESPONSE_BY_FILE'] = json.dumps({'meeting.part002.opus': '**B**: [20:00] Globally timestamped'})
    result = c.run()
    assert result.returncode == 0, result.stderr
    assert '**B**: [20:00] Globally timestamped' in c.note.read_text()
    assert '[39:59]' not in c.note.read_text()


def test_revision_custom_short_chunks_use_exact_window_starts(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '62'
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = '**A**: [00:01] Speech'
    result = c.run('--chunk', '1')
    assert result.returncode == 0, result.stderr
    assert '**A**: [01:00] Speech' in c.note.read_text()
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 2


def test_revision_source_change_invalidates_single_chunk_cache(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    c.audio.write_bytes(b'new recording')
    assert c.run().returncode == 0
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 2


def test_revision_local_processing_failure_resumes_raw_response_without_api(tmp_path, monkeypatch):
    module = load_module()
    audio = tmp_path / 'short.opus'
    audio.write_bytes(b'audio')
    requests = []
    def response(*args, **kwargs):
        requests.append(1)
        return module.TranscriptionResult('**A**: [00:01] Durable raw words', module.UsageCost(1, 1, 2, .1))
    monkeypatch.setattr(module, 'transcribe_single_audio', response)
    normalize = module.normalize_chunk
    def broken(*args):
        raise RuntimeError('Local processing failure')
    monkeypatch.setattr(module, 'normalize_chunk', broken)
    kwargs = dict(system_prompt='Transcribe', user_prompt=None, model='test', client=object(), pricing={},
        chunk_minutes=30, windows=[(0, 20)], cache_dir=tmp_path / 'cache')
    with pytest.raises(RuntimeError, match='Local processing failure'):
        module.transcribe_audio(audio, **kwargs)
    state = json.loads(next((tmp_path / 'cache').glob('chunk-*.json')).read_text())
    assert state['status'] == 'received' and state['raw_transcript'].endswith('Durable raw words')
    monkeypatch.setattr(module, 'normalize_chunk', normalize)
    resumed = module.transcribe_audio(audio, **kwargs)
    assert len(requests) == 1 and resumed.usage.total_tokens == 0
    assert resumed.saved_cost_usd == .1


def test_revision_unknown_usage_is_not_reported_as_free():
    module = load_module()
    usage = module.calculate_usage_cost(SimpleNamespace(usage_metadata=None), 'test', {})
    assert usage.cost_usd is None
    assert module.combine_usage_costs([usage, module.UsageCost(1, 1, 2, .1)]).cost_usd is None


def test_revision_local_and_global_timestamp_origins_that_both_fit_require_review():
    module = load_module()
    raw = '**A**: [20:00] Speech after twenty minutes of silence'
    text, warning = module.normalize_chunk(raw, (1199, 1201))
    assert text == raw
    assert 'origin' in warning.lower()


def test_revision_refusal_is_not_automatically_retried(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = 'I cannot transcribe this audio.'
    result = c.run()
    assert result.returncode == 1
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 1
    assert 'I cannot transcribe this audio.' in c.note.read_text()


def test_revision_missing_timestamp_helper_fails_before_any_request(revision_case):
    c = revision_case
    script = c.root / 'standalone-call.py'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'call', script)
    result = subprocess.run(['uv', 'run', str(script), str(c.audio), '--out', str(c.output),
        '--system-prompt', str(c.root / 'prompt.md')], cwd=c.root, env=c.env, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'Install timestamp.py next to call' in result.stderr
    assert not (c.root / 'requests.log').exists()


def test_revision_failed_force_resumes_and_promotes_candidate(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    c.env['FAKE_GENAI_ERROR_FILES'] = 'meeting.opus'
    assert c.run('--force').returncode == 1
    candidate = c.note.with_suffix('.incomplete.md')
    assert 'replacement_for:' in candidate.read_text()
    del c.env['FAKE_GENAI_ERROR_FILES']
    assert c.run().returncode == 0
    assert not candidate.exists()
    assert 'transcription_status: complete' in c.note.read_text()


def test_revision_force_protects_unrelated_candidate_before_request(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    candidate = c.note.with_suffix('.incomplete.md')
    candidate.write_text('Personal working notes')
    before = (c.root / 'requests.log').read_bytes()
    result = c.run('--force')
    assert result.returncode == 1
    assert 'Move or rename' in result.stderr
    assert (c.root / 'requests.log').read_bytes() == before
    assert candidate.read_text() == 'Personal working notes'


def test_revision_successful_force_leaves_stale_candidate_without_blocking(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    c.env['FAKE_GENAI_ERROR_FILES'] = 'meeting.opus'
    assert c.run('--force').returncode == 1
    del c.env['FAKE_GENAI_ERROR_FILES']
    assert c.run('--force').returncode == 0
    assert c.run().returncode == 0
    assert c.note.with_suffix('.incomplete.md').exists()


def test_revision_model_separator_does_not_create_extra_chunks():
    module = load_module()
    raw = '**A**: [00:01] First\n\n---\n\n**A**: [00:02] Second'
    cleaned, warning = module.normalize_chunk(raw, (0, 20))
    assert warning is None
    assert len(module.split_transcript_parts(cleaned)) == 1
    assert 'First' in cleaned and 'Second' in cleaned


def test_revision_patch_save_failure_reuses_paid_response_and_cost(revision_case, monkeypatch):
    c = revision_case
    module = load_module()
    monkeypatch.setattr(module, 'plan_audio_chunks', lambda *a, **kw: (20, [(0, 20)]))
    monkeypatch.setenv('TRANSCRIBE_CALLS_CACHE_DIR', str(c.root / 'cache'))
    monkeypatch.setattr(module, 'build_client', lambda: object())
    monkeypatch.setattr(module, 'load_google_pricing', lambda: {})
    responses = ['Not a transcript', 'Still not a transcript', '**A**: [00:01] Repaired']
    requests = []
    def response(*args, **kwargs):
        requests.append(1)
        return module.TranscriptionResult(responses.pop(0), module.UsageCost(1, 1, 2, .1))
    monkeypatch.setattr(module, 'transcribe_single_audio', response)
    kwargs = dict(audio=str(c.audio), user_prompt=None, force=False, patch=False,
        model='test', chunk_minutes=30, out_dir=c.output, system_prompt_file=c.root / 'prompt.md', dry_run=False)
    with pytest.raises(RuntimeError, match='Saved incomplete'):
        module.process_audio(**kwargs)
    original = c.note.read_bytes()
    atomic = module.atomic_write
    def fail_note(path, text):
        if path == c.note:
            raise OSError('note publish failed')
        atomic(path, text)
    monkeypatch.setattr(module, 'atomic_write', fail_note)
    kwargs['patch'] = True
    with pytest.raises(OSError, match='note publish failed'):
        module.process_audio(**kwargs)
    assert c.note.read_bytes() == original
    monkeypatch.setattr(module, 'atomic_write', atomic)
    module.process_audio(**kwargs)
    assert len(requests) == 3
    assert 'cost: 0.300000' in c.note.read_text()
    assert 'transcription_status: complete' in c.note.read_text()


def test_revision_patch_rejects_misaligned_cost_metadata_before_request(revision_case):
    c = revision_case
    c.env['FAKE_GENAI_RESPONSE_BY_FILE'] = json.dumps({'meeting.part002.opus': 'Not a transcript'})
    assert c.run().returncode == 1
    c.note.write_text(load_module().set_frontmatter_fields(c.note.read_text(), {'chunk_costs': '[]'}, prepend=False))
    before = (c.root / 'requests.log').read_bytes()
    result = c.run('--patch')
    assert result.returncode == 1
    assert 'chunk_costs' in result.stderr and 'no API request made' in result.stderr
    assert (c.root / 'requests.log').read_bytes() == before


def test_run_logs_success_cache_skip_and_failure_with_separate_ids(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    assert c.run().returncode == 0
    c.env['FAKE_GENAI_ERROR_FILES'] = 'meeting.opus'
    assert c.run('--force').returncode == 1
    runs = sorted((c.root / 'cache' / 'runs').iterdir())
    assert len(runs) == 3
    summaries = [json.loads((run / 'summary.json').read_text()) for run in runs]
    assert [row['exit_code'] for row in summaries] == [0, 0, 1]
    assert [row['new_cost_usd'] for row in summaries] == [.0008, 0, None]
    assert [row['api_attempts'] for row in summaries] == [1, 0, 1]
    assert len({row['run_id'] for row in summaries}) == 3
    assert all(row['elapsed_seconds'] >= 0 and row['code_sha256'] and row['python'] for row in summaries)
    assert 'Already transcribed' in (runs[1] / 'console.log').read_text()
    assert 'forced error' in (runs[2] / 'console.log').read_text()
    events = [json.loads(line) for line in (runs[0] / 'events.jsonl').read_text().splitlines()]
    assert all(row['run_id'] == summaries[0]['run_id'] for row in events)
    response = next(row for row in events if row['event'] == 'response')
    assert response['elapsed_seconds'] >= 0 and 'finish_reasons' in response
    assert response['usage']['total_tokens'] == 150
    receipt = json.loads(next(runs[0].glob('chunk-*-attempt1-*.json')).read_text())
    assert receipt['status'] == 'received' and receipt['raw_transcript']
    assert not any('GEMINI_API_KEY' in (run / 'summary.json').read_text() for run in runs)


def test_run_logs_argument_errors_and_dry_run_without_api(revision_case):
    c = revision_case
    assert c.run('--bogus').returncode != 0
    assert c.run('--dry-run').returncode == 0
    runs = sorted((c.root / 'cache' / 'runs').iterdir())
    assert len(runs) == 2
    assert json.loads((runs[0] / 'summary.json').read_text())['exit_code'] == 2
    assert 'No such option' in (runs[0] / 'console.log').read_text()
    assert 'dry-run' in (runs[1] / 'console.log').read_text()
    assert not (c.root / 'requests.log').exists()


def test_thinking_config_invalidates_cache_and_reaches_sdk(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    assert c.run().returncode == 0
    c.note.unlink()
    c.env['TRANSCRIBE_CALLS_THINKING'] = 'minimal'
    assert c.run().returncode == 0
    assert len(list((c.root / 'cache').glob('chunk-*.json'))) == 2
    assert 'THINKING\tminimal' in (c.root / 'requests.log').read_text()


def test_invalid_thinking_setting_fails_before_request(revision_case):
    c = revision_case
    c.env['TRANSCRIBE_CALLS_THINKING'] = 'invalid'
    result = c.run()
    assert result.returncode == 1
    assert 'TRANSCRIBE_CALLS_THINKING' in result.stderr
    assert not (c.root / 'requests.log').exists()


def test_context_limits_bound_prior_prompt_and_allow_no_context(monkeypatch):
    module = load_module()
    text = '\n'.join(f'**A**: [00:{i:02}] Turn {i}' for i in range(10))
    monkeypatch.setenv('TRANSCRIBE_CALLS_CONTEXT_LINES', '2')
    context = module.build_prior_chunk_context([text])
    assert 'Turn 9' in context and 'Turn 8' in context and 'Turn 7' not in context
    monkeypatch.setenv('TRANSCRIBE_CALLS_CONTEXT_LINES', '0')
    assert module.build_prior_chunk_context([text]) is None


def test_invalid_context_limit_fails_before_request(revision_case):
    c = revision_case
    c.env['TRANSCRIBE_CALLS_CONTEXT_LINES'] = '-1'
    result = c.run()
    assert result.returncode == 1 and 'TRANSCRIBE_CALLS_CONTEXT' in result.stderr
    assert not (c.root / 'requests.log').exists()


def test_run_logging_permission_failure_prevents_api(revision_case):
    c = revision_case
    blocked = c.root / 'blocked-cache'
    blocked.write_text('not a directory')
    c.env['TRANSCRIBE_CALLS_CACHE_DIR'] = str(blocked)
    result = c.run()
    assert result.returncode == 1
    assert 'cannot create diagnostic logs' in result.stderr and 'no API request made' in result.stderr
    assert not (c.root / 'requests.log').exists()


def test_run_logging_interrupt_keeps_diagnostic_summary(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setenv('TRANSCRIBE_CALLS_CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(sys, 'argv', ['call', 'meeting'])
    def interrupted():
        raise KeyboardInterrupt()
    monkeypatch.setattr(module, 'app', interrupted)
    with pytest.raises(KeyboardInterrupt):
        module.run_cli()
    run = next((tmp_path / 'runs').iterdir())
    assert json.loads((run / 'summary.json').read_text())['exit_code'] == 130
    assert 'KeyboardInterrupt' in (run / 'console.log').read_text()


def test_inline_timestamps_preserve_valid_prefix_without_paid_retry(revision_case):
    c = revision_case
    c.env['FAKE_FFPROBE_DURATION'] = '20'
    c.env['FAKE_GENAI_TRANSCRIPT_TEXT'] = '**A**: [00:01] Real words [00:15] More words [00:25] Spurious continuation'
    result = c.run()
    assert result.returncode == 0, result.stderr
    assert 'Real words' in c.note.read_text() and 'More words' in c.note.read_text()
    assert 'Spurious continuation' not in c.note.read_text()
    assert (c.root / 'requests.log').read_text().count('AUDIO\t') == 1
    state = json.loads(next((c.root / 'cache').glob('chunk-*.json')).read_text())
    assert 'Spurious continuation' in state['raw_transcript']
