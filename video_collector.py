"""
video_collector.py
~~~~~~~~~~~~~~~~~~
For each stored match, search YouTube for highlight videos and download
them using yt-dlp into a per-match sub-directory.

Strategy:
  1. Build a search query from the match's team names.
  2. Use the yt-dlp `ytsearch` feature to find candidate videos.
  3. Download the best matching video at the configured quality.
  4. Record the local file path back to the database.
"""

import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Optional

import yaml
import yt_dlp

from match_fetcher import init_db, update_match_video_path, get_all_matches

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise_filename(name: str) -> str:
    """Strip characters that are unsafe in directory/file names."""
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def _build_search_query(match: dict, query_template: str) -> str:
    home = match["home_team"]
    away = match["away_team"]
    return query_template.format(home=home, away=away)


def _ydl_format_selector(quality: str) -> str:
    """
    Return a yt-dlp format string for the requested quality.
    Falls back gracefully to the best available format.
    """
    quality_map = {
        "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "720p": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "480p": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
    }
    return quality_map.get(quality, quality_map["720p"])


# ---------------------------------------------------------------------------
# Core downloader
# ---------------------------------------------------------------------------

def download_highlights_for_match(
    match: dict,
    videos_dir: str,
    query_template: str,
    quality: str = "720p",
    max_results: int = 3,
) -> Optional[str]:
    """
    Search YouTube for highlights of *match* and download the first result.

    Returns the local file path of the downloaded video, or None on failure.
    """
    query = _build_search_query(match, query_template)
    match_slug = _sanitise_filename(
        f"{match['home_team']}_vs_{match['away_team']}_{match['match_date']}"
    )
    output_dir = os.path.join(videos_dir, match_slug)
    os.makedirs(output_dir, exist_ok=True)

    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")
    search_url = f"ytsearch{max_results}:{query}"

    ydl_opts = {
        "format": _ydl_format_selector(quality),
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        # Only download the first (most relevant) result
        "playlist_items": "1",
        # Embed subtitles if available
        "writesubtitles": False,
        # Restrict filename to avoid special-character issues
        "restrictfilenames": True,
    }

    logger.info(
        "Searching YouTube for: %s (match id=%s)", query, match["id"]
    )

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_url, download=True)
            if info and "entries" in info and info["entries"]:
                entry = info["entries"][0]
                # yt-dlp writes the filename; reconstruct it
                downloaded_path = ydl.prepare_filename(entry)
                # yt-dlp may have merged to .mp4
                if not os.path.exists(downloaded_path):
                    downloaded_path = os.path.splitext(downloaded_path)[0] + ".mp4"
                if os.path.exists(downloaded_path):
                    logger.info("Downloaded: %s", downloaded_path)
                    return downloaded_path
                # Fallback: find any mp4 in the output dir
                for fname in os.listdir(output_dir):
                    if fname.endswith(".mp4"):
                        return os.path.join(output_dir, fname)
    except yt_dlp.utils.DownloadError as exc:
        logger.warning("yt-dlp download error for match %s: %s", match["id"], exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error downloading match %s: %s", match["id"], exc)

    return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def collect_videos(config: dict) -> None:
    """
    Iterate all stored matches that lack a video_path and attempt to
    download their highlights.
    """
    compilation = config["compilation"]
    videos_dir = compilation["videos_dir"]
    os.makedirs(videos_dir, exist_ok=True)

    yt_cfg = config["youtube_search"]
    query_template = yt_cfg["query_template"]
    quality = yt_cfg.get("quality", "720p")
    max_results = int(yt_cfg.get("max_results", 3))

    db_path = compilation["database_path"]
    conn = init_db(db_path)
    rows = get_all_matches(conn)

    for row in rows:
        match = dict(row)
        if match.get("video_path") and os.path.exists(match["video_path"]):
            logger.info(
                "Video already exists for %s vs %s, skipping.",
                match["home_team"],
                match["away_team"],
            )
            continue

        video_path = download_highlights_for_match(
            match,
            videos_dir=videos_dir,
            query_template=query_template,
            quality=quality,
            max_results=max_results,
        )

        if video_path:
            update_match_video_path(conn, match["id"], video_path)
        else:
            logger.warning(
                "Could not download video for match %s vs %s",
                match["home_team"],
                match["away_team"],
            )

    conn.close()


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    collect_videos(cfg)
    print("Video collection complete.")
