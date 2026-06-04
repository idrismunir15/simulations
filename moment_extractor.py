"""
moment_extractor.py
~~~~~~~~~~~~~~~~~~~
Detect and extract interesting moments from a downloaded match highlight video.

Detection methods:
  1. Scene-change detection via FFmpeg `select` filter (visual cuts).
  2. Audio spike detection via FFmpeg `astats` + `volumedetect` (crowd noise,
     commentary excitement).

Each detected moment is trimmed to [timestamp - padding, timestamp + padding]
and written to an output clips directory.
"""

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

def _make_match_slug(match: dict) -> str:
    """Return a filesystem-safe slug for a match."""
    raw = f"{match['home_team']}_vs_{match['away_team']}_{match['match_date']}"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)



    timestamp: float          # seconds from start of video
    duration: float           # clip duration in seconds
    clip_path: str            # path to the extracted clip file
    score: float = 0.0        # higher = more interesting
    method: str = "scene"     # "scene" | "audio"


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _run_ffprobe_duration(video_path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def detect_scene_changes(video_path: str, threshold: float = 0.4) -> list[float]:
    """
    Use FFmpeg scene detection to find timestamps (seconds) where abrupt
    visual changes occur (e.g., goal celebrations, card close-ups).

    Returns a sorted list of timestamps.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    # showinfo writes to stderr
    timestamps = []
    for line in result.stderr.splitlines():
        # pts_time:XX.XXXXXX
        match = re.search(r"pts_time:([\d.]+)", line)
        if match:
            timestamps.append(float(match.group(1)))
    return sorted(set(timestamps))


def detect_audio_spikes(video_path: str, spike_db: float = -20.0) -> list[float]:
    """
    Detect timestamps where audio level exceeds *spike_db* dBFS.
    Uses FFmpeg's `astats` filter with a short window to sample audio energy.

    Returns a sorted list of timestamps.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    timestamps = []
    current_time: Optional[float] = None
    for line in result.stderr.splitlines():
        t_match = re.search(r"pts_time:([\d.]+)", line)
        if t_match:
            current_time = float(t_match.group(1))
        db_match = re.search(r"lavfi\.astats\.Overall\.RMS_level=([-\d.]+)", line)
        if db_match and current_time is not None:
            rms = float(db_match.group(1))
            if rms > spike_db:
                timestamps.append(current_time)
                current_time = None
    return sorted(set(timestamps))


def _deduplicate_timestamps(timestamps: list[float], min_gap: float = 30.0) -> list[float]:
    """
    Merge timestamps that are closer than *min_gap* seconds,
    keeping only the first in each cluster.
    """
    if not timestamps:
        return []
    deduped = [timestamps[0]]
    for ts in timestamps[1:]:
        if ts - deduped[-1] >= min_gap:
            deduped.append(ts)
    return deduped


def extract_clip(
    video_path: str,
    timestamp: float,
    padding: float,
    output_path: str,
    video_duration: float,
) -> bool:
    """
    Extract a clip from *video_path* centred on *timestamp* with *padding*
    seconds on each side. Writes to *output_path*.

    Returns True on success.
    """
    start = max(0.0, timestamp - padding)
    end = min(video_duration, timestamp + padding)
    duration = end - start

    if duration <= 0:
        logger.warning("Skipping zero-duration clip at %.2fs", timestamp)
        return False

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-crf", "23",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        logger.error(
            "ffmpeg clip extraction failed for %s at %.2fs: %s",
            video_path, timestamp, result.stderr.decode()
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_moments(
    video_path: str,
    output_dir: str,
    match: dict,
    config: dict,
) -> list[Moment]:
    """
    Detect and extract interesting moments from *video_path*.

    Returns a list of :class:`Moment` objects for successfully extracted clips.
    """
    ext_cfg = config["moment_extraction"]
    scene_threshold = float(ext_cfg.get("scene_threshold", 0.4))
    audio_spike_db = float(ext_cfg.get("audio_spike_db", -20))
    padding = float(ext_cfg.get("clip_padding_seconds", 10))
    min_gap = float(ext_cfg.get("min_gap_seconds", 30))
    max_moments = int(ext_cfg.get("max_moments_per_match", 10))

    os.makedirs(output_dir, exist_ok=True)

    try:
        video_duration = _run_ffprobe_duration(video_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not probe duration of %s: %s", video_path, exc)
        return []

    logger.info(
        "Detecting moments in %s (duration=%.1fs)", video_path, video_duration
    )

    # Collect timestamps from both methods
    scene_ts = []
    audio_ts = []
    try:
        scene_ts = detect_scene_changes(video_path, threshold=scene_threshold)
        logger.info("Scene changes detected: %d", len(scene_ts))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scene detection failed: %s", exc)

    try:
        audio_ts = detect_audio_spikes(video_path, spike_db=audio_spike_db)
        logger.info("Audio spikes detected: %d", len(audio_ts))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Audio spike detection failed: %s", exc)

    # Tag each timestamp with its source method
    tagged: list[tuple[float, str]] = (
        [(ts, "scene") for ts in scene_ts] + [(ts, "audio") for ts in audio_ts]
    )
    tagged.sort(key=lambda x: x[0])

    # Deduplicate
    all_ts = _deduplicate_timestamps([ts for ts, _ in tagged], min_gap=min_gap)
    all_ts = all_ts[:max_moments]

    moments: list[Moment] = []
    match_slug = _make_match_slug(match)

    for idx, ts in enumerate(all_ts):
        method = next((m for t, m in tagged if abs(t - ts) < 1.0), "scene")
        clip_filename = f"{match_slug}_moment_{idx + 1:03d}.mp4"
        clip_path = os.path.join(output_dir, clip_filename)

        success = extract_clip(
            video_path=video_path,
            timestamp=ts,
            padding=padding,
            output_path=clip_path,
            video_duration=video_duration,
        )
        if success:
            moment = Moment(
                timestamp=ts,
                duration=padding * 2,
                clip_path=clip_path,
                method=method,
            )
            moments.append(moment)
            logger.info("Extracted moment %d at %.2fs -> %s", idx + 1, ts, clip_path)

    logger.info(
        "Extracted %d moment(s) for %s vs %s",
        len(moments),
        match["home_team"],
        match["away_team"],
    )
    return moments


def extract_all_moments(config: dict) -> dict[str, list[Moment]]:
    """
    Iterate all matches with a downloaded video and extract moments.

    Returns {match_id: [Moment, ...]}
    """
    from match_fetcher import init_db, get_all_matches

    compilation = config["compilation"]
    moments_dir = compilation["moments_dir"]
    db_path = compilation["database_path"]

    conn = init_db(db_path)
    rows = get_all_matches(conn)
    conn.close()

    all_moments: dict[str, list[Moment]] = {}
    for row in rows:
        match = dict(row)
        video_path = match.get("video_path")
        if not video_path or not os.path.exists(video_path):
            logger.info(
                "No video for %s vs %s, skipping moment extraction.",
                match["home_team"],
                match["away_team"],
            )
            continue

        match_moments_dir = os.path.join(moments_dir, _make_match_slug(match))
        moments = extract_moments(
            video_path=video_path,
            output_dir=match_moments_dir,
            match=match,
            config=config,
        )
        all_moments[match["id"]] = moments

    return all_moments


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    results = extract_all_moments(cfg)
    total = sum(len(v) for v in results.values())
    print(f"Extracted {total} moment clip(s) across {len(results)} match(es).")
