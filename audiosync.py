#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer",
#     "librosa",
#     "numpy",
#     "scipy",
# ]
# ///

import subprocess
import typer
import numpy as np
import librosa
from scipy import signal
from pathlib import Path

app = typer.Typer(add_completion=False)

def get_duration(path: str) -> float:
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
           '-of', 'default=noprint_wrappers=1:nokey=1', path]
    return float(subprocess.check_output(cmd).strip())

@app.command()
def sync(
    video_path: Path = typer.Argument(..., help="Input video file"),
    audio_path: Path = typer.Argument(..., help="Input audio file"),
    output_path: Path = typer.Argument(..., help="Output MKV file"),
    sr: int = 8000
):
    """
    Syncs audio/video.
    STRATEGY: Copies Audio (Lossless) + Re-encodes Video (Frame-Perfect Sync).
    """
    typer.echo(f"🎧 Loading waveforms at {sr}Hz...")
    y_vid, _ = librosa.load(video_path, sr=sr, mono=True)
    y_aud, _ = librosa.load(audio_path, sr=sr, mono=True)

    typer.echo("🟰 Normalizing...")
    y_vid = (y_vid - np.mean(y_vid)) / (np.std(y_vid) + 1e-6)
    y_aud = (y_aud - np.mean(y_aud)) / (np.std(y_aud) + 1e-6)

    typer.echo("📉 Computing offset...")
    correlation = signal.fftconvolve(y_vid, y_aud[::-1], mode='full')
    offset = (np.argmax(correlation) - (len(y_aud) - 1)) / sr

    typer.echo(f"⏱  Offset: {offset:.4f}s")

    # Trim Logic
    vid_dur = get_duration(str(video_path))
    aud_dur = get_duration(str(audio_path))

    vid_seek = max(0, offset)
    aud_seek = max(0, -offset)
    end_rel_to_video = min(vid_dur, offset + aud_dur)
    duration = end_rel_to_video - vid_seek

    if duration <= 0:
        typer.echo("❌ Error: No overlap.", err=True)
        raise typer.Exit(1)

    typer.echo(f"✂️  Trimming: Vid +{vid_seek:.2f}s | Aud +{aud_seek:.2f}s | Dur {duration:.2f}s")

    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-ss', str(vid_seek), '-t', str(duration), '-i', str(video_path),
        '-ss', str(aud_seek), '-t', str(duration), '-i', str(audio_path),

        # --- VIDEO: Efficient Re-encode (Necessary for Sync) ---
        '-c:v', 'libx264',       # Standard H.264
        '-crf', '28',            # CRF 28 matches your original ~130kbps quality
        '-preset', 'veryfast',   # Fast encoding
        '-pix_fmt', 'yuv420p',   # Ensure compatibility

        # --- AUDIO: Stream Copy (The "Originals" Request) ---
        '-c:a', 'copy',          # <--- DIRECT COPY from 1.opus (No transcoding!)

        '-map', '0:v:0', '-map', '1:a:0',
        str(output_path)
    ]

    typer.echo("🚀 Rendering with Hybrid Copy/Encode...")
    subprocess.run(cmd, check=True)
    typer.echo(f"✅ Saved to {output_path}")

if __name__ == "__main__":
    app()
