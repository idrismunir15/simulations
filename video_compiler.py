"""
video_compiler.py
~~~~~~~~~~~~~~~~~
Compile extracted moment clips into a final highlight reel video.

Steps:
  1. For each match, prepend a title card (team names + date).
  2. Concatenate: intro → [title card + moments]* → outro.
  3. Optionally mix in background music at a low volume.
  4. Export the final MP4 to the configured output directory.

All video processing uses FFmpeg via subprocess to avoid large
in-memory dependencies.
"""

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _probe_resolution(video_path: str) -> tuple[int, int]:
    """Return (width, height) of a video file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    w, h = result.stdout.strip().split(",")
    return int(w), int(h)


def _generate_title_card(
    text_line1: str,
    text_line2: str,
    output_path: str,
    resolution: str = "1280x720",
    duration: int = 3,
    fps: int = 30,
) -> bool:
    """
    Generate a solid-black title card with two lines of text using FFmpeg.
    Returns True on success.
    """
    w, h = resolution.split("x")
    # Escape special characters for FFmpeg drawtext
    def _esc(s: str) -> str:
        return s.replace("'", "\\'").replace(":", "\\:")

    vf = (
        f"color=black:s={resolution}:d={duration},"
        f"drawtext=text='{_esc(text_line1)}':fontcolor=white:fontsize=48:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-30:font='Liberation Sans',"
        f"drawtext=text='{_esc(text_line2)}':fontcolor=yellow:fontsize=36:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+30:font='Liberation Sans'"
    )
    # Add a silent audio stream so title card clips can be concatenated
    # with audio-bearing clips without format mismatch.
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", vf,
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-t", str(duration),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error("Title card generation failed: %s", result.stderr.decode())
        return False
    return True


def _normalise_clip(
    input_path: str,
    output_path: str,
    resolution: str,
    fps: int,
) -> bool:
    """
    Re-encode a clip to a common resolution, fps, and audio format so all
    clips can be concatenated without compatibility issues.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", f"scale={resolution},setsar=1",
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error("Normalise clip failed for %s: %s", input_path, result.stderr.decode())
        return False
    return True


def _concat_clips(clip_paths: list[str], output_path: str) -> bool:
    """
    Concatenate a list of video files using the FFmpeg concat demuxer.
    All clips must have the same codec, resolution, fps, and audio format.
    """
    if not clip_paths:
        logger.error("No clips to concatenate.")
        return False

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as flist:
        for path in clip_paths:
            flist.write(f"file '{os.path.abspath(path)}'\n")
        flist_path = flist.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", flist_path,
            "-c", "copy",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            logger.error("Concat failed: %s", result.stderr.decode())
            return False
    finally:
        os.unlink(flist_path)

    return True


def _mix_background_music(
    video_path: str,
    music_path: str,
    output_path: str,
    music_volume: float = 0.15,
) -> bool:
    """
    Mix background music into the video at *music_volume* relative to the
    original audio track. The music is looped if shorter than the video.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", music_path,
        "-filter_complex",
        f"[1:a]volume={music_volume}[music];"
        "[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error("Background music mix failed: %s", result.stderr.decode())
        return False
    return True


# ---------------------------------------------------------------------------
# Intro / Outro generators
# ---------------------------------------------------------------------------

def _generate_intro(output_path: str, branding: str, resolution: str, fps: int, duration: int) -> bool:
    return _generate_title_card(
        text_line1=branding,
        text_line2="Pre-World Cup 2026 Friendlies",
        output_path=output_path,
        resolution=resolution,
        duration=duration,
        fps=fps,
    )


def _generate_outro(output_path: str, branding: str, resolution: str, fps: int, duration: int) -> bool:
    return _generate_title_card(
        text_line1="Thanks for watching!",
        text_line2=branding,
        output_path=output_path,
        resolution=resolution,
        duration=duration,
        fps=fps,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compile_highlight_reel(
    matches_with_moments: list[tuple[dict, list]],
    config: dict,
    output_filename: Optional[str] = None,
) -> Optional[str]:
    """
    Compile all moments from all matches into one final highlight reel.

    *matches_with_moments* is a list of (match_dict, [Moment, ...]) tuples.

    Returns the path to the final video file, or None on failure.
    """
    comp = config["compilation"]
    final_dir = comp["final_dir"]
    os.makedirs(final_dir, exist_ok=True)

    resolution = comp.get("resolution", "1280x720")
    fps = int(comp.get("fps", 30))
    title_card_duration = int(comp.get("title_card_duration", 3))
    intro_duration = int(comp.get("intro_duration", 5))
    outro_duration = int(comp.get("outro_duration", 5))
    branding = comp.get("branding_text", "World Cup 2026 Highlights")
    bg_music = comp.get("background_music", "")
    bg_volume = float(comp.get("background_music_volume", 0.15))

    output_filename = output_filename or "highlight_reel.mp4"
    raw_output = os.path.join(final_dir, f"_raw_{output_filename}")
    final_output = os.path.join(final_dir, output_filename)

    with tempfile.TemporaryDirectory() as tmp:
        segments: list[str] = []

        # --- Intro ---
        if intro_duration > 0:
            intro_path = os.path.join(tmp, "intro.mp4")
            if _generate_intro(intro_path, branding, resolution, fps, intro_duration):
                segments.append(intro_path)

        for match, moments in matches_with_moments:
            if not moments:
                continue

            home = match["home_team"]
            away = match["away_team"]
            date = match["match_date"]

            # Title card for this match
            tc_path = os.path.join(
                tmp,
                re.sub(r"[^a-zA-Z0-9_]", "_", f"title_{home}_vs_{away}.mp4"),
            )
            if _generate_title_card(
                text_line1=f"{home}  vs  {away}",
                text_line2=date,
                output_path=tc_path,
                resolution=resolution,
                duration=title_card_duration,
                fps=fps,
            ):
                segments.append(tc_path)

            # Normalise and append each moment clip
            for idx, moment in enumerate(moments):
                norm_path = os.path.join(
                    tmp,
                    re.sub(r"[^a-zA-Z0-9_]", "_", f"norm_{home}_{away}_{idx}.mp4"),
                )
                if _normalise_clip(moment.clip_path, norm_path, resolution, fps):
                    segments.append(norm_path)
                else:
                    logger.warning("Skipping unprocessable clip: %s", moment.clip_path)

        # --- Outro ---
        if outro_duration > 0:
            outro_path = os.path.join(tmp, "outro.mp4")
            if _generate_outro(outro_path, branding, resolution, fps, outro_duration):
                segments.append(outro_path)

        if not segments:
            logger.error("No segments to compile — aborting.")
            return None

        logger.info("Concatenating %d segment(s)...", len(segments))
        if not _concat_clips(segments, raw_output):
            return None

    # Mix background music if configured
    if bg_music and os.path.exists(bg_music):
        logger.info("Mixing background music: %s", bg_music)
        if _mix_background_music(raw_output, bg_music, final_output, music_volume=bg_volume):
            os.remove(raw_output)
        else:
            logger.warning("Music mix failed; using video without music.")
            os.rename(raw_output, final_output)
    else:
        os.rename(raw_output, final_output)

    logger.info("Final highlight reel saved to: %s", final_output)
    return final_output


def compile_all(config: dict, all_moments: dict) -> Optional[str]:
    """
    Load match data from DB, pair with moments, and compile the reel.

    *all_moments* is {match_id: [Moment, ...]} as returned by
    moment_extractor.extract_all_moments().
    """
    from match_fetcher import init_db, get_all_matches

    db_path = config["compilation"]["database_path"]
    conn = init_db(db_path)
    rows = get_all_matches(conn)
    conn.close()

    matches_with_moments = []
    for row in rows:
        match = dict(row)
        moments = all_moments.get(match["id"], [])
        if moments:
            matches_with_moments.append((match, moments))

    if not matches_with_moments:
        logger.warning("No matches with moments found — nothing to compile.")
        return None

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return compile_highlight_reel(
        matches_with_moments=matches_with_moments,
        config=config,
        output_filename=f"highlights_{timestamp}.mp4",
    )


if __name__ == "__main__":
    import sys
    from moment_extractor import extract_all_moments

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    all_moments = extract_all_moments(cfg)
    final = compile_all(cfg, all_moments)
    if final:
        print(f"Highlight reel compiled: {final}")
    else:
        print("Compilation failed or no moments available.")
