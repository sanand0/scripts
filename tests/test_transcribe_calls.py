from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap


def load_module():
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    spec = importlib.util.spec_from_file_location("transcribe_calls", script_path)
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
                            {"input": 2.0, "output": 12.0, "input_cached": None}
                        ],
                    },
                    {
                        "id": "gemini-3-1-pro-preview",
                        "name": "Gemini 3.1 Pro <=200k",
                        "price_history": [
                            {"input": 2.0, "output": 12.0, "input_cached": None}
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


def test_looks_like_transcript_requires_five_matching_lines() -> None:
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


def test_script_creates_transcript_for_new_audio_file(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
        "--out",
        output_dir,
        "--system-prompt",
        prompt_file,
        env=env,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "created call-a.md" in result.stdout
    assert "tokens=150 cost=$0.000800 total_cost=$0.000800" in result.stdout

    log_text = log_path.read_text(encoding="utf-8")
    assert "APIKEY\ttest-key-from-dotenv" in log_text
    assert f"AUDIO\t{audio_path}" in log_text
    assert "SYSTEM_PROMPT\tUse this exact prompt" in log_text
    assert "USER_PROMPT\t" not in log_text

    call_a = (output_dir / "call-a.md").read_text(encoding="utf-8")
    assert call_a.startswith(
        "---\n"
        "model: gemini-3-flash-preview\n"
        "cost: 0.000800\n"
        "prompt: |-\n"
        "  Use this exact prompt\n"
        "---\n\n"
        "# call-a\n"
    )
    assert "## Transcript\n\n**Speaker**: [00:01] Transcript for call-a.opus line 1" in call_a

    second = run_script(
        script_path, audio_path, "--out", output_dir, "--system-prompt", prompt_file, env=env, cwd=tmp_path
    )
    assert second.returncode == 0, second.stderr
    assert log_path.read_text(encoding="utf-8") == log_text
    assert "Already transcribed: call-a.md" in second.stdout


def test_script_looks_up_audio_by_stem_in_default_input_dir(tmp_path: Path) -> None:
    source_script = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    script_path = tmp_path / "transcribe_calls.py"
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
    source_script = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    script_path = tmp_path / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"

    result = run_script(script_path, cwd=tmp_path)

    assert result.returncode != 0
    assert "Missing argument" in (result.stderr + result.stdout)


def test_script_reports_invalid_existing_markdown(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = tmp_path / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"

    shutil.copyfile(Path(__file__).resolve().parents[1] / "transcribe_calls.py", script_path)
    input_dir.mkdir()
    output_dir.mkdir()
    audio_path = input_dir / "call.opus"
    audio_path.write_bytes(b"audio")

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, audio_path, "--out", output_dir, env=env, cwd=tmp_path)

    assert result.returncode == 1
    assert "GEMINI_API_KEY is not set" in result.stderr


def test_script_sends_user_prompt_with_small_audio_file(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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


def test_script_chunks_long_audio_and_joins_chunk_transcripts(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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


def test_script_resumes_chunked_transcription_from_one_day_cache(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    assert len(list(cache_dir.glob("*.json"))) == 2

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


def test_cleanup_chunk_cache_removes_only_expired_chunk_json(tmp_path: Path) -> None:
    module = load_module()
    fresh = tmp_path / "chunk-fresh.json"
    expired = tmp_path / "chunk-expired.json"
    unrelated = tmp_path / "keep.txt"
    prices_cache = tmp_path / "google-prices.json"
    for path in (fresh, expired, unrelated, prices_cache):
        path.write_text("x", encoding="utf-8")
    os.utime(expired, (100, 100))
    os.utime(prices_cache, (100, 100))

    removed = module.cleanup_chunk_cache(tmp_path, now=module.CHUNK_CACHE_TTL_SECONDS + 101)

    assert removed == 1
    assert fresh.exists()
    assert not expired.exists()
    assert unrelated.exists()
    assert prices_cache.exists()


def test_script_auto_retries_and_resolves_invalid_chunk(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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

    # First call for long.part002.opus returns garbage; the fake client always returns the
    # same FAKE_GENAI_RESPONSE_BY_FILE entry, so simulate "the retry succeeds" by pointing
    # at a valid transcript for the retry and asserting it is used (retry bypasses the cache
    # so a fresh call is always made, which the fake honors identically either way here).
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

    assert result.returncode == 0, result.stderr
    assert "WARNING long.opus: section 2/3 still does not look like a transcript after retry" in result.stderr
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "Transcript for long.part001.opus line 1" in transcript
    assert "It appears that you forgot to attach the audio file." in transcript
    genai_log = log_path.read_text(encoding="utf-8")
    # part002 is transcribed twice: once in the main pass, once on the automatic retry.
    assert sum("long.part002.opus" in line for line in genai_log.splitlines() if line.startswith("AUDIO\t")) == 2


def test_script_patch_retranscribes_invalid_sections(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
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
