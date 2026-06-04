"""
main.py
~~~~~~~
Orchestrator for the Pre-World Cup Friendly Matches Highlight Video Pipeline.

Usage
-----
Run the full pipeline once:
    python main.py

Run with a custom config file:
    python main.py --config path/to/config.yaml

Enable the background scheduler (runs daily at the time set in config.yaml):
    python main.py --schedule

Run only a specific stage:
    python main.py --stage fetch
    python main.py --stage collect
    python main.py --stage extract
    python main.py --stage compile
    python main.py --stage upload --video output/final/highlights.mp4

Stages
------
  fetch    → Query football API for upcoming friendlies and store in DB.
  collect  → Download highlight videos for each match via yt-dlp.
  extract  → Detect and extract interesting moment clips from each video.
  compile  → Compile all moments into one final highlight reel MP4.
  upload   → Upload the compiled reel to Twitter and YouTube.
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    log_file = log_cfg.get("log_file", "output/pipeline.log")

    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def stage_fetch(config: dict) -> list[dict]:
    """Fetch friendly matches and store in SQLite."""
    from match_fetcher import fetch_and_store_matches
    logger = logging.getLogger("stage.fetch")
    logger.info("=== Stage: Fetch Matches ===")
    matches = fetch_and_store_matches(config)
    logger.info("Fetched %d match(es).", len(matches))
    return matches


def stage_collect(config: dict) -> None:
    """Download highlight videos for all stored matches."""
    from video_collector import collect_videos
    logger = logging.getLogger("stage.collect")
    logger.info("=== Stage: Collect Videos ===")
    collect_videos(config)
    logger.info("Video collection complete.")


def stage_extract(config: dict) -> dict:
    """Extract interesting moments from all downloaded videos."""
    from moment_extractor import extract_all_moments
    logger = logging.getLogger("stage.extract")
    logger.info("=== Stage: Extract Moments ===")
    all_moments = extract_all_moments(config)
    total = sum(len(v) for v in all_moments.values())
    logger.info(
        "Extracted %d moment(s) across %d match(es).",
        total, len(all_moments),
    )
    return all_moments


def stage_compile(config: dict, all_moments: dict) -> Optional[str]:
    """Compile moments into the final highlight reel."""
    from video_compiler import compile_all
    logger = logging.getLogger("stage.compile")
    logger.info("=== Stage: Compile Video ===")
    final_video = compile_all(config, all_moments)
    if final_video:
        logger.info("Highlight reel: %s", final_video)
    else:
        logger.warning("Compilation produced no output.")
    return final_video


def stage_upload(
    config: dict,
    video_path: str,
    match: Optional[dict] = None,
) -> dict:
    """Upload the final video to Twitter and YouTube."""
    from uploader import upload_highlight_reel
    logger = logging.getLogger("stage.upload")
    logger.info("=== Stage: Upload ===")
    results = upload_highlight_reel(video_path, match, config)
    logger.info("Twitter: %s", results.get("twitter") or "FAILED")
    logger.info("YouTube: %s", results.get("youtube") or "FAILED")
    return results


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(config: dict) -> None:
    """Execute all pipeline stages sequentially."""
    logger = logging.getLogger("pipeline")
    logger.info("Pipeline started at %s", datetime.now().isoformat())

    # Ensure output directories exist
    comp = config["compilation"]
    for key in ("output_dir", "videos_dir", "moments_dir", "final_dir"):
        os.makedirs(comp[key], exist_ok=True)

    stage_fetch(config)
    stage_collect(config)
    all_moments = stage_extract(config)
    final_video = stage_compile(config, all_moments)

    if final_video and os.path.exists(final_video):
        stage_upload(config, final_video)
    else:
        logger.warning("No final video to upload.")

    logger.info("Pipeline finished at %s", datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def start_scheduler(config: dict) -> None:
    """Start APScheduler to run the pipeline on a cron schedule."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        print(
            "APScheduler is not installed. Run: pip install apscheduler\n"
            "Then retry with --schedule."
        )
        sys.exit(1)

    sched_cfg = config.get("scheduler", {})
    cron_expr = sched_cfg.get("cron", "0 23 * * *")
    timezone = sched_cfg.get("timezone", "UTC")
    fields = cron_expr.split()
    if len(fields) != 5:
        print(f"Invalid cron expression in config: {cron_expr!r}")
        sys.exit(1)

    minute, hour, day, month, day_of_week = fields
    trigger = CronTrigger(
        minute=minute, hour=hour, day=day, month=month,
        day_of_week=day_of_week, timezone=timezone,
    )

    scheduler = BlockingScheduler(timezone=timezone)
    scheduler.add_job(run_pipeline, trigger=trigger, args=[config])
    print(
        f"Scheduler started. Pipeline will run with cron '{cron_expr}' "
        f"(timezone: {timezone}). Press Ctrl+C to stop."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-World Cup Friendly Matches Highlight Video Pipeline"
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--stage",
        choices=["fetch", "collect", "extract", "compile", "upload"],
        help="Run only a specific pipeline stage (default: run all stages)",
    )
    parser.add_argument(
        "--video",
        help="Path to video file for the 'upload' stage (required when --stage=upload)",
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Run the pipeline on the schedule defined in config.yaml",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not os.path.exists(args.config):
        print(f"Config file not found: {args.config}")
        sys.exit(1)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    # Ensure base output directory exists before logging to it
    os.makedirs(config["compilation"]["output_dir"], exist_ok=True)
    setup_logging(config)
    logger = logging.getLogger("main")

    if args.schedule:
        if not config.get("scheduler", {}).get("enabled", False):
            logger.warning(
                "scheduler.enabled is false in config.yaml. "
                "Starting scheduler anyway because --schedule was passed."
            )
        start_scheduler(config)
        return

    if args.stage is None:
        run_pipeline(config)
        return

    # Single-stage execution
    if args.stage == "fetch":
        stage_fetch(config)

    elif args.stage == "collect":
        stage_collect(config)

    elif args.stage == "extract":
        stage_extract(config)

    elif args.stage == "compile":
        all_moments = stage_extract(config)
        stage_compile(config, all_moments)

    elif args.stage == "upload":
        if not args.video:
            print("--video <path> is required when using --stage=upload")
            sys.exit(1)
        if not os.path.exists(args.video):
            print(f"Video file not found: {args.video}")
            sys.exit(1)
        stage_upload(config, args.video)

    else:
        logger.error("Unknown stage: %s", args.stage)
        sys.exit(1)


if __name__ == "__main__":
    main()
