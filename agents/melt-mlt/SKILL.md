---
name: melt-mlt
description: Workflows for melt, the MLT Framework CLI video editor, to edit, transcode, composite, stream, or automate video/audio. Covers multitrack composition, color grading, batch processing, encoding, streaming, and server-side pipelines.
metadata:
  source: https://claude.ai/chat/76cc4aad-4e37-4486-8b82-ed2a3829174a
---

# Melt / MLT Framework — Expert Skill

## Mental Model: What Melt Actually Is

Melt is not a wrapper around ffmpeg — it is a **non-linear compositor** with a pipeline model. Understanding the pipeline is the difference between fighting the tool and mastering it.

```
Producers → [Filters] → Tractor/Multitrack → [Transitions] → Consumer
```

- **Producer**: Any input — file, device, color, text, image sequence, XML composition
- **Filter**: Modifies frames 1-to-1 (always outputs same count it receives)
- **Transition**: Combines two tracks; outputs one composited frame per pair
- **Consumer**: Render target — display (sdl2), file (avformat), stream, or XML

**Command line order is sacred.** Melt parses left-to-right; a filter placed before a `-track` affects a different scope than one placed after. Misplaced flags silently do wrong things — no error is raised.

---

## Workflow 1: MLT XML as the Primary Authoring Format (High Impact)

**The #1 beginner mistake**: building everything on the command line. Experts author in MLT XML for anything beyond trivial edits. XML is composable, version-controllable, debuggable, and reusable.

### Preview command → save as XML → render from XML

```bash
# Step 1: Prototype interactively (renders to screen)
melt clip_a.mp4 out=149 clip_b.mp4 out=299 -mix 25 -mixer luma -mixer mix:-1

# Step 2: Serialize to XML instead of re-typing
melt clip_a.mp4 out=149 clip_b.mp4 out=299 -mix 25 -mixer luma -mixer mix:-1 \
     -consumer xml:project.mlt

# Step 3: Render from XML — much cleaner
melt project.mlt -consumer avformat:output.mp4 vcodec=libx264 acodec=aac \
     real_time=-2 progress=1
```

### MLT XML multitrack template (use as starting point)

```xml
<?xml version="1.0" encoding="utf-8"?>
<mlt version="7" title="My Project" LC_NUMERIC="C">

  <!-- Declare producers without in/out — set those in the playlist -->
  <producer id="v1" in="0" out="9999">
    <property name="resource">/path/to/main.mp4</property>
  </producer>
  <producer id="music" in="0" out="9999">
    <property name="resource">/path/to/music.aiff</property>
  </producer>
  <producer id="logo" in="0" out="9999">
    <property name="resource">/path/to/logo.png</property>
  </producer>

  <!-- Video track (track 0, bottom) -->
  <playlist id="track_video">
    <entry producer="v1" in="0" out="599"/>
    <blank length="25"/>
    <entry producer="v1" in="700" out="1199"/>
  </playlist>

  <!-- Music track (track 1, audio-only) -->
  <playlist id="track_audio" hide="video">
    <entry producer="music" in="0" out="1799"/>
  </playlist>

  <!-- Tractor combines everything -->
  <tractor id="main" in="0" out="1799">
    <multitrack>
      <track producer="track_video"/>
      <track producer="track_audio"/>
    </multitrack>

    <!-- Watermark/logo composited across ALL tracks (attached to tractor) -->
    <filter id="logo_overlay" mlt_service="watermark">
      <property name="resource">/path/to/logo.png</property>
      <property name="geometry">0%/0%:15%x15%:100</property>
      <property name="distort">0</property>
    </filter>
  </tractor>

</mlt>
```

> **Expert note**: Filters attached to the `<tractor>` apply to the composited output, not individual tracks. This is the only way to globally affect all tracks. The command-line equivalent requires a two-pass invocation.

---

## Workflow 2: High-Quality Encoding (Most Commonly Botched)

### Baseline H.264 render (proxy-safe, not upload-safe)

```bash
melt project.mlt \
  -consumer avformat:output.mp4 \
  vcodec=libx264 acodec=aac \
  ab=192k crf=18 preset=slow \
  real_time=-2 progress=1
```

### Broadcast-safe H.264 (for Vimeo/YouTube delivery)

```bash
melt project.mlt \
  -consumer avformat:output.mp4 \
  vcodec=libx264 acodec=aac \
  crf=17 preset=slow bf=2 \
  g=30 keyint_min=1 \
  movflags=+faststart \
  pix_fmt=yuv420p \
  ab=320k ar=48000 \
  real_time=-2 threads=0 progress=1
```

> **Why `pix_fmt=yuv420p`**: Many MLT internal operations produce yuv422 or rgba. Forgetting this means your upload plays fine in VLC but breaks in browsers and iPhone playback.

> **Why `movflags=+faststart`**: Moves the moov atom to the front of the file so web players can begin buffering before the full file downloads.

> **Why `real_time=-2`**: Negative values = processing threads without frame-dropping. The number sets how many extra threads run ahead. `-2` is usually the sweet spot for encoding — more threads, no dropped frames.

### 10-bit HDR passthrough (MLT 7.30+)

```bash
# Requires FFmpeg producers, avfilter filters only, and avformat consumer
melt 'file:hdr_input.mp4\?hwaccel=vaapi' \
  -consumer avformat:hdr_output.mp4 \
  vcodec=libx265 pix_fmt=yuv420p10le \
  color_trc=smpte2084 color_primaries=bt2020 colorspace=bt2020nc \
  crf=18 preset=slow \
  acodec=aac ab=320k \
  real_time=-2 progress=1
```

### ProRes output (for post-production handoff)

```bash
melt project.mlt \
  -consumer avformat:output.mov \
  vcodec=prores_ks profile=3 \
  acodec=pcm_s24le \
  real_time=-4 progress=1
```

### Check what codecs/formats are available

```bash
melt -query formats        # container formats
melt -query video_codecs   # video codecs
melt -query audio_codecs   # audio codecs
melt -query filters        # all available filters
melt -query filter=avfilter.lut3d  # inspect a specific filter's properties
```

---

## Workflow 3: Color Grading via avfilter (Non-Obvious Power)

MLT exposes the entire FFmpeg filter graph via `avfilter.*`. This is dramatically more powerful than native MLT filters for color work, and beginners miss it entirely.

### Apply a .cube LUT

```bash
melt input.mp4 \
  -filter avfilter.lut3d file=/path/to/look.cube interp=trilinear \
  -consumer avformat:graded.mp4 vcodec=libx264 crf=18 real_time=-2
```

### Manual color correction (lift/gamma/gain equivalent)

```bash
melt input.mp4 \
  -filter avfilter.colorbalance rs=0.05 gs=0.0 bs=-0.05 \
  -filter avfilter.curves master="0/0 0.5/0.55 1/1" \
  -consumer avformat:corrected.mp4 vcodec=libx264 crf=18 real_time=-2
```

### Secondary color correction with HSL

```bash
# MLT 7.30+ ships hslprimaries and hslrange filters natively
melt input.mp4 \
  -filter hslrange hue_start=90 hue_end=150 saturation=1.3 lightness=1.0 \
  -consumer avformat:output.mp4 vcodec=libx264 crf=18 real_time=-2
```

### In XML for a full color pipeline

```xml
<filter mlt_service="avfilter.lut3d">
  <property name="file">/path/to/look.cube</property>
  <property name="interp">trilinear</property>
</filter>
<filter mlt_service="avfilter.unsharp">
  <property name="luma_msize_x">5</property>
  <property name="luma_msize_y">5</property>
  <property name="luma_amount">0.8</property>
</filter>
```

---

## Workflow 4: Multitrack Compositing (Where Most Editors Get Stuck)

### Key rule: track 0 = bottom, highest track = visible on top

```
Track 2 (highest): overlay/title  → shown when non-blank
Track 1:           B-roll          → shown when non-blank AND track 2 is blank
Track 0 (lowest):  main video      → fallback
```

### Picture-in-picture with affine transition

```bash
melt main.mp4 out=599 \
  -track pip.mp4 out=599 \
  -transition affine in=0 out=599 a_track=0 b_track=1 \
    geometry="640/360:640x360:90" distort=0 \
  -consumer avformat:pip_output.mp4 vcodec=libx264 crf=18 real_time=-2 progress=1
```

> `geometry` format is `x/y:WxH:opacity`. Coordinates are in pixels or %. Opacity 0–100.

### Lower-thirds text overlay

```bash
# pango producer renders text with Pango markup
melt main.mp4 out=599 \
  -track colour:0x00000000 out=599 \
  -transition affine in=0 out=599 a_track=0 b_track=1 geometry="0%/85%:100%x15%:80" \
  -attach-track pango markup="<span font='Arial Bold 36' foreground='white'>John Smith\nDirector</span>" \
    valign=center halign=left pad=30 \
  -consumer avformat:lower_thirds.mp4 vcodec=libx264 crf=18 real_time=-2
```

### Stacking multiple overlays via XML (use this for >2 tracks)

```xml
<tractor id="main">
  <multitrack>
    <track producer="playlist_main"/>     <!-- track 0: main video -->
    <track producer="playlist_broll"/>    <!-- track 1: B-roll -->
    <track producer="playlist_titles" hide="audio"/>  <!-- track 2: titles only -->
  </multitrack>

  <!-- Composite track 1 over track 0 -->
  <transition mlt_service="qtblend" in="0" out="599" a_track="0" b_track="1">
    <property name="rect">0 0 1920 1080 1</property>
  </transition>

  <!-- Composite track 2 over composite of 0+1 -->
  <transition mlt_service="qtblend" in="0" out="599" a_track="1" b_track="2">
    <property name="rect">0 810 1920 270 0.8</property>
  </transition>
</tractor>
```

> **Expert note**: `qtblend` respects alpha channel and is the modern replacement for `affine` in most cases. Use `affine` when you need non-rectangular transforms (rotation, skew).

---

## Workflow 5: Audio Workflows

### Normalize audio with SOX (two-pass analysis)

```bash
# Pass 1: analyze and write normalized MLT XML
melt input.mp4 -filter sox:analysis -consumer xml:analyzed.mlt video_off=1 all=1

# Pass 2: render using the gain from analysis
melt analyzed.mlt -consumer avformat:normalized.mp4 vcodec=libx264 crf=18 acodec=aac
```

### Mix two audio tracks at different levels

```bash
melt main.mp4 \
  -track music.mp3 \
  -transition mix in=0 out=999 a_track=0 b_track=1 start=-3 end=-3 \
  -consumer avformat:mixed.mp4 vcodec=libx264 crf=18 acodec=aac ab=320k
```

> `start`/`end` values for `mix` transition are in dB. `-3` = 3dB reduction of the B track.

### Ducking: lower music under speech automatically

```bash
# Use avfilter.sidechaincompress or duckaudio via XML
# Simpler approach: set the mix transition level explicitly per section
melt speech.mp4 \
  -track music.mp3 \
  -transition mix in=0 out=149 a_track=0 b_track=1 start=0 end=-12 \
  -transition mix in=150 out=600 a_track=0 b_track=1 start=0 end=-6 \
  -consumer avformat:ducked.mp4 vcodec=libx264 crf=18 acodec=aac
```

### Replace audio track entirely

```bash
melt input.mp4 audio_index=-1 \
  -track new_audio.aac \
  -consumer avformat:resynced.mp4 vcodec=libx264 crf=18 acodec=aac ab=320k \
  real_time=-2 progress=1
```

---

## Workflow 6: Batch Processing & Automation

### Process a folder of clips (shell loop)

```bash
for f in /footage/*.mp4; do
  base=$(basename "$f" .mp4)
  melt "$f" \
    -filter avfilter.lut3d file=look.cube interp=trilinear \
    -consumer avformat:"output/${base}_graded.mp4" \
    vcodec=libx264 crf=18 acodec=aac real_time=-2 progress=1
done
```

### Template-based rendering (swap clip into XML template)

```bash
#!/bin/bash
# render_template.sh <input_clip> <title_text> <output_file>
INPUT="$1"
TITLE="$2"
OUTPUT="$3"

# Generate XML from template, substituting clip path and title
sed "s|__INPUT__|${INPUT}|g; s|__TITLE__|${TITLE}|g" template.mlt > /tmp/render_job.mlt

melt /tmp/render_job.mlt \
  -consumer avformat:"$OUTPUT" \
  vcodec=libx264 crf=18 acodec=aac movflags=+faststart \
  real_time=-2 progress=1
```

### Thumbnail extraction at multiple points

```bash
# Extract a thumbnail at frame 150
melt input.mp4 in=150 out=150 \
  -consumer avformat:thumb.jpg vframes=1 video_off=0 real_time=-1

# Extract every 100 frames as a contact sheet
melt input.mp4 -filter avfilter.fps fps=0.5 \
  -consumer avformat:"thumbs/%04d.jpg" real_time=-1
```

### Check project metadata without opening a GUI

```bash
# Inspect media properties (resolution, codec, frame rate, channels, etc.)
melt input.mp4 -consumer xml | grep "meta.media"

# Get total frame count, fps, duration
melt -query producer=avformat
```

---

## Workflow 7: Streaming & Live Output

### Multicast UDP transport stream

```bash
melt -profile hdv_720_25p source.mp4 eof=loop \
  -consumer avformat:"udp://224.224.224.224:1234?pkt_size=1316&reuse=1" \
  real_time=1 terminate_on_pause=0 \
  f=mpegts vcodec=libx264 b=4000k acodec=aac ab=192k
```

### RTMP stream (YouTube Live / Twitch)

```bash
RTMP_URL="rtmp://a.rtmp.youtube.com/live2/YOUR_STREAM_KEY"

melt -profile atsc_720p_30 source.mp4 eof=loop \
  -consumer avformat:"$RTMP_URL" \
  real_time=1 terminate_on_pause=0 \
  f=flv vcodec=libx264 b=4000k preset=veryfast \
  acodec=aac ab=128k ar=44100
```

### Loop indefinitely (broadcast playout)

```bash
# eof=loop MUST come before any producer/consumer/filter/track/transition
melt eof=loop -profile atsc_1080i_50 playlist.mlt \
  -consumer avformat:udp://... real_time=1 terminate_on_pause=0 f=mpegts
```

---

## Workflow 8: Reverse, Freeze, Speed Ramp

### Reverse a clip

```bash
# framebuffer producer handles reversal via seeking
melt "framebuffer:input.mp4?reverse=1" \
  -consumer avformat:reversed.mp4 vcodec=libx264 crf=18 real_time=-2
```

> Not all formats seek accurately enough for clean reversal. H.264 with frequent keyframes works best. AVCHD is unreliable.

### Freeze frame at a specific moment

```bash
# Freeze frame 240 for the entire clip
melt input.mp4 -filter freeze frame=240 freeze_after=1 \
  -consumer avformat:frozen.mp4 vcodec=libx264 crf=18
```

### Extend the first frame (hold on first frame for N frames)

```bash
melt input.mp4 out=0 -repeat 89 input.mp4 in=1 \
  -consumer avformat:held.mp4 vcodec=libx264 crf=18
```

### Speed ramp with avfilter

```bash
# 50% slow motion (requires high frame rate source)
melt input.mp4 -filter avfilter.setpts expr="2*PTS" \
  -filter avfilter.atempo speed=0.5 \
  -consumer avformat:slow.mp4 vcodec=libx264 crf=18 real_time=-2
```

---

## Workflow 9: Timecode Burn-in & QC Overlays

### Burn timecode into video (QC copy)

```bash
melt input.mp4 \
  meta.attr.titles=1 meta.attr.titles.markup="#timecode#" \
  -attach data_show dynamic=1 \
  -consumer avformat:qc_copy.mp4 vcodec=libx264 crf=23 real_time=-2
```

> Use `#frame#` instead of `#timecode#` for absolute frame numbers.

### Burn filename + timecode

```bash
melt input.mp4 \
  meta.attr.titles=1 "meta.attr.titles.markup=input.mp4  TC: #timecode#" \
  -attach data_show dynamic=1 \
  -consumer avformat:qc.mp4 vcodec=libx264 crf=23 real_time=-2
```

---

## Workflow 10: AVCHD / High-Performance Decoding

### AVCHD decoding optimization (multi-thread workaround)

```bash
# AVCHD can't multi-thread; skip filters for preview
melt -profile atsc_1080i_60 clip.MTS \
  skip_loop_filter=all skip_frame=bidir \
  -consumer sdl2

# For encoding (don't use skip flags — quality matters)
melt -profile atsc_1080i_60 clip.MTS \
  threads=4 \
  -consumer avformat:output.mp4 vcodec=libx264 crf=18 real_time=-4
```

### VA-API hardware decoding (where GPU offload helps)

```bash
# Only helps on older CPUs — memory transfer is the bottleneck on modern hardware
melt -verbose 'file:input.mp4\?hwaccel=vaapi' \
  -consumer avformat:output.mp4 vcodec=libx264 crf=18 real_time=-2

# Alternate device
melt 'file:input.mp4\?hwaccel=vaapi&hwaccel_device=/dev/dri/renderD129'
```

---

## Critical Gotchas Experts Know

### 1. `-attach` chains, not appends

```bash
# WRONG: both filters attach to each other, not to clip1
melt clip1.dv -attach watermark:logo.png -attach invert

# CORRECT: use -attach-cut to attach both to clip1
melt clip1.dv -attach-cut watermark:logo.png -attach-cut invert
```

### 2. `-group` properties bleed into filters

```bash
# WRONG: greyscale only applies to first 50 frames because -group bleeds
melt -group in=0 out=49 clip* -filter greyscale

# CORRECT: reset group before filter
melt -group in=0 out=49 clip* -group -filter greyscale
```

### 3. Profile must match first, or you get silent rescaling

```bash
# WRONG: default profile is PAL 576p — your 4K clip gets silently downscaled
melt 4k_input.mp4 -consumer avformat:output.mp4 ...

# CORRECT: declare profile first (before any producer)
melt -profile uhd_2160p_30 4k_input.mp4 -consumer avformat:output.mp4 ...

# List available profiles
melt -query profiles
```

### 4. File paths with spaces require quoting at the right level

```bash
# WRONG
melt My Clip.mp4

# CORRECT
melt "My Clip.mp4"
# or for avformat producer with query strings:
melt 'file:My Clip.mp4\?hwaccel=vaapi'
```

### 5. Transition in/out points are global timeline positions, not clip-relative

```bash
# If clip_a is frames 0–49 and clip_b starts at frame 25 (overlapping):
melt clip_a.mp4 out=49 \
  -track -blank 24 clip_b.mp4 \
  -transition luma in=25 out=49 a_track=0 b_track=1
#                  ^^^^^^^^^^
#          These are GLOBAL timeline positions, not clip positions
```

### 6. The xml consumer is your best debugging tool

```bash
# Dump any command line as XML to see exactly what MLT is doing
melt complex_command... -consumer xml | less
```

### 7. Whitespace in property values

```bash
# Properties with spaces need quotes — the whole name=value pair
melt input.mp4 "meta.attr.titles.markup=My Title Here"
```

### 8. `real_time=0` = single-threaded (use for debugging, not production)

```bash
# For debugging a pipeline reliably (no thread race conditions)
melt input.mp4 -filter... -consumer avformat:out.mp4 vcodec=libx264 real_time=0

# For production: -2 or -4 (negative = no frame drop, number = extra threads)
real_time=-2   # 2 threads, no drops
real_time=-4   # 4 threads, no drops
```

---

## Useful Filter Reference (Non-Obvious Filters)

| Filter             | What it does     | Example                                   |
| ------------------ | ---------------- | ----------------------------------------- |
| `avfilter.lut3d`   | Apply .cube LUT  | `file=look.cube interp=trilinear`         |
| `avfilter.curves`  | Tone curve RGB   | `master="0/0 0.5/0.55 1/1"`               |
| `avfilter.unsharp` | Sharpen / blur   | `luma_amount=0.8 luma_msize_x=5`          |
| `avfilter.setpts`  | Speed ramp       | `expr="2*PTS"` (50% speed)                |
| `avfilter.fps`     | Retime to fps    | `fps=0.5` (one frame per 2s)              |
| `hslprimaries`     | Secondary color  | `hue_start=90 hue_end=150 saturation=1.3` |
| `hslrange`         | Range-based HSL  | `saturation=1.2 lightness=0.95`           |
| `sox:analysis`     | Replay gain scan | Use in two-pass audio normalize           |
| `freeze`           | Freeze a frame   | `frame=240 freeze_after=1`                |
| `data_show`        | Burn metadata    | `dynamic=1`                               |
| `watermark`        | Composite image  | `geometry="10/10:20%x20%:80"`             |
| `pango`            | Text rendering   | `markup=<span...>text</span>`             |
| `framebuffer`      | Reverse/retime   | `reverse=1`                               |
| `gradientmap`      | Color map        | Maps luma to gradient colors              |
| `audiolevelgraph`  | Audio meter      | Visual VU meter overlay                   |

---

## Encoding Presets Quick Reference

```bash
# Web delivery (H.264, broad compatibility)
-consumer avformat:out.mp4 vcodec=libx264 crf=18 preset=slow pix_fmt=yuv420p \
  movflags=+faststart acodec=aac ab=320k ar=48000

# Archive / Editing master (ProRes HQ)
-consumer avformat:out.mov vcodec=prores_ks profile=3 acodec=pcm_s24le

# Streaming / Low-latency (H.264 fast)
-consumer avformat:out.mp4 vcodec=libx264 b=4000k preset=veryfast \
  acodec=aac ab=192k real_time=1

# AV1 (modern web, smaller files)
-consumer avformat:out.mp4 vcodec=libsvtav1 crf=30 preset=6 \
  acodec=libopus ab=192k

# Proxy / offline edit
-consumer avformat:proxy.mp4 vcodec=libx264 crf=28 preset=ultrafast \
  s=1280x720 acodec=aac ab=128k real_time=-2

# GIF (short loops)
-consumer avformat:out.gif s=480x270 r=12 real_time=-2
```

---

## Discovering What's Available on Your Install

```bash
melt -query                  # all registered services
melt -query filters          # all filters
melt -query filter=avfilter.lut3d   # properties for a specific filter
melt -query transitions      # all transitions
melt -query producers        # all producers
melt -query consumers        # all consumers
melt -query profiles         # built-in profiles (resolutions/frame rates)
melt -query presets          # encoding presets

# Profile details
melt -query profile=atsc_1080p_30   # show a specific profile's settings
```
