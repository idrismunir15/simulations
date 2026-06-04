"""
uploader.py
~~~~~~~~~~~
Upload the compiled highlight reel to Twitter/X and YouTube.

Twitter upload
--------------
Uses Tweepy v4+ with the Twitter API v2 media upload endpoint.
Requires: API key, API secret, Access token, Access token secret.
Note: video upload requires a Twitter Developer account with elevated access.

YouTube upload
--------------
Uses the YouTube Data API v3 via google-api-python-client.
Requires OAuth 2.0 credentials (client_secrets.json).
On first run the user will be prompted to authorise in a browser;
subsequent runs reuse the cached token file.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Twitter / X uploader
# ---------------------------------------------------------------------------

def upload_to_twitter(
    video_path: str,
    caption: str,
    config: dict,
) -> Optional[str]:
    """
    Upload *video_path* to Twitter with *caption*.

    Returns the URL of the created tweet, or None on failure.
    """
    try:
        import tweepy
    except ImportError:
        logger.error("tweepy is not installed. Run: pip install tweepy")
        return None

    tw = config["twitter"]
    max_size_mb = float(tw.get("max_video_size_mb", 512))
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if file_size_mb > max_size_mb:
        logger.error(
            "Video size %.1f MB exceeds Twitter's %.0f MB limit.",
            file_size_mb, max_size_mb,
        )
        return None

    # Auth
    auth = tweepy.OAuth1UserHandler(
        consumer_key=tw["api_key"],
        consumer_secret=tw["api_secret"],
        access_token=tw["access_token"],
        access_token_secret=tw["access_token_secret"],
    )
    api_v1 = tweepy.API(auth)

    # Upload video via chunked media upload (v1.1 endpoint)
    logger.info("Uploading video to Twitter (%s)...", video_path)
    try:
        media = api_v1.chunked_upload(
            filename=video_path,
            media_category="tweet_video",
        )
        media_id = media.media_id_string

        # Wait for processing
        for _ in range(30):
            status = api_v1.get_media_upload_status(media_id)
            processing = getattr(status, "processing_info", None)
            if processing:
                state = processing.get("state")
                if state == "succeeded":
                    break
                if state == "failed":
                    logger.error("Twitter video processing failed.")
                    return None
                wait = processing.get("check_after_secs", 5)
                logger.info("Waiting %ds for Twitter video processing...", wait)
                time.sleep(wait)
            else:
                break

        # Post tweet using v2 client
        client_v2 = tweepy.Client(
            bearer_token=tw.get("bearer_token"),
            consumer_key=tw["api_key"],
            consumer_secret=tw["api_secret"],
            access_token=tw["access_token"],
            access_token_secret=tw["access_token_secret"],
        )
        response = client_v2.create_tweet(
            text=caption,
            media_ids=[media_id],
        )
        tweet_id = response.data["id"]
        tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
        logger.info("Tweet posted: %s", tweet_url)
        return tweet_url

    except tweepy.errors.TweepyException as exc:
        logger.error("Twitter upload error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# YouTube uploader
# ---------------------------------------------------------------------------

def _get_youtube_service(config: dict):
    """
    Authenticate with YouTube Data API v3 and return a service resource.
    Caches the OAuth token to disk for reuse.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error(
            "google-api-python-client / google-auth-oauthlib not installed. "
            "Run: pip install google-api-python-client google-auth-oauthlib"
        )
        return None

    yt_cfg = config["youtube"]
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    token_file = yt_cfg.get("token_file", "youtube_token.json")
    oauth_file = yt_cfg.get("client_secrets_file", "client_secrets.json")

    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(oauth_file):
                logger.error(
                    "YouTube OAuth credentials file not found: %s", oauth_file
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(oauth_file, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    config: dict,
) -> Optional[str]:
    """
    Upload *video_path* to YouTube.

    Returns the YouTube video URL, or None on failure.
    """
    try:
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
    except ImportError:
        logger.error(
            "google-api-python-client not installed. "
            "Run: pip install google-api-python-client"
        )
        return None

    yt_cfg = config["youtube"]
    service = _get_youtube_service(config)
    if service is None:
        return None

    tags = yt_cfg.get("tags", [])
    category_id = yt_cfg.get("category_id", "17")
    privacy_status = yt_cfg.get("privacy_status", "public")

    body = {
        "snippet": {
            "title": title[:100],   # YouTube title limit
            "description": description[:5000],
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 10,  # 10 MB chunks
    )

    logger.info("Uploading video to YouTube: %s", video_path)
    try:
        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info("YouTube upload progress: %d%%", progress)

        video_id = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("YouTube upload complete: %s", video_url)
        return video_url

    except Exception as exc:  # noqa: BLE001
        logger.error("YouTube upload error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Convenience: build captions/titles from match data
# ---------------------------------------------------------------------------

def _format_teams(match: dict) -> str:
    return f"{match['home_team']} vs {match['away_team']}"


def _build_twitter_caption(match: dict, config: dict) -> str:
    template = config["twitter"].get(
        "tweet_template",
        "🏟️ Pre-World Cup Friendly Highlights: {teams} ({date})\n#WorldCup2026 #Football #Friendlies",
    )
    return template.format(
        teams=_format_teams(match),
        date=match["match_date"],
        home=match["home_team"],
        away=match["away_team"],
    )


def _build_youtube_title(match: dict, config: dict) -> str:
    template = config["youtube"].get(
        "title_template",
        "Pre-World Cup Friendly Highlights: {teams} ({date})",
    )
    return template.format(
        teams=_format_teams(match),
        date=match["match_date"],
        home=match["home_team"],
        away=match["away_team"],
    )


def _build_youtube_description(match: dict, config: dict) -> str:
    template = config["youtube"].get(
        "description_template",
        "Highlights from the pre-World Cup 2026 friendly: {home} vs {away} on {date}.",
    )
    return template.format(
        teams=_format_teams(match),
        date=match["match_date"],
        home=match["home_team"],
        away=match["away_team"],
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def upload_highlight_reel(
    video_path: str,
    match: Optional[dict],
    config: dict,
) -> dict[str, Optional[str]]:
    """
    Upload *video_path* to both Twitter and YouTube.

    *match* is used to build captions/titles; pass None to use generic text.

    Returns {"twitter": url_or_none, "youtube": url_or_none}.
    """
    if match:
        twitter_caption = _build_twitter_caption(match, config)
        youtube_title = _build_youtube_title(match, config)
        youtube_desc = _build_youtube_description(match, config)
    else:
        twitter_caption = (
            "🏟️ Pre-World Cup 2026 Friendly Highlights Reel\n"
            "#WorldCup2026 #Football #Friendlies"
        )
        youtube_title = "Pre-World Cup 2026 Friendly Highlights Reel"
        youtube_desc = (
            "Best moments from pre-World Cup 2026 international friendly matches.\n"
            "#WorldCup2026 #Football #Friendlies"
        )

    twitter_url = upload_to_twitter(video_path, twitter_caption, config)
    youtube_url = upload_to_youtube(video_path, youtube_title, youtube_desc, config)

    return {"twitter": twitter_url, "youtube": youtube_url}


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    if len(sys.argv) < 3:
        print("Usage: python uploader.py [config.yaml] <video_path>")
        sys.exit(1)

    video = sys.argv[2]
    results = upload_highlight_reel(video, None, cfg)
    print("Upload results:", results)
