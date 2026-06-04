# simulations
Simulations of complex engineering and life science concepts, processes and systems for easy understanding.

---

## Pre-World Cup Friendly Matches Highlight Video Pipeline

An automated pipeline that:
1. **Fetches** upcoming international friendly matches before the World Cup via a football data API.
2. **Downloads** highlight videos from YouTube using `yt-dlp`.
3. **Extracts** the most interesting moments (goals, near-misses, crowd spikes) using FFmpeg.
4. **Compiles** the clips into a polished highlight reel with title cards and optional background music.
5. **Uploads** the final video to both **Twitter/X** and **YouTube**.

---

### Project Structure

```
simulations/
├── config.yaml          # All configuration (API keys, paths, settings)
├── main.py              # Orchestrator / CLI entry point
├── match_fetcher.py     # Fetch friendly matches → SQLite DB
├── video_collector.py   # Download highlight videos via yt-dlp
├── moment_extractor.py  # Detect & extract interesting moments via FFmpeg
├── video_compiler.py    # Compile moments into final highlight reel
├── uploader.py          # Upload to Twitter and YouTube
└── requirements.txt     # Python dependencies
```

---

### Prerequisites

| Dependency | Install |
|------------|---------|
| Python 3.10+ | [python.org](https://www.python.org/) |
| FFmpeg | `sudo apt install ffmpeg` / `brew install ffmpeg` |
| Python packages | `pip install -r requirements.txt` |

---

### Configuration

Copy `config.yaml` and fill in your credentials:

```yaml
football_api:
  provider: "api_football"      # or "football_data" / "thesportsdb"
  api_football_key: "YOUR_KEY"

worldcup:
  start_date: "2026-06-11"
  lookback_days: 90             # Fetch friendlies within 90 days before WC

twitter:
  api_key: "..."
  api_secret: "..."
  access_token: "..."
  access_token_secret: "..."
  bearer_token: "..."

youtube:
  client_secrets_file: "client_secrets.json"
```

For YouTube, download your `client_secrets.json` from the
[Google Cloud Console](https://console.cloud.google.com/) and place it next to `config.yaml`.

---

### Running the Pipeline

**Full pipeline (fetch → download → extract → compile → upload):**
```bash
python main.py
```

**Run a single stage:**
```bash
python main.py --stage fetch      # Query football API
python main.py --stage collect    # Download videos
python main.py --stage extract    # Extract moments
python main.py --stage compile    # Compile reel
python main.py --stage upload --video output/final/highlights.mp4
```

**Scheduled mode (runs daily at 23:00 UTC by default):**
```bash
# Enable in config.yaml: scheduler.enabled: true
python main.py --schedule
```

**Custom config file:**
```bash
python main.py --config /path/to/my_config.yaml
```

---

### Output

All output is written to the `output/` directory (configurable):

```
output/
├── matches.db          # SQLite database of fetched matches
├── pipeline.log        # Pipeline run log
├── videos/             # Downloaded raw highlight videos
│   └── TeamA_vs_TeamB_YYYY-MM-DD/
├── moments/            # Extracted moment clips
│   └── TeamA_vs_TeamB_YYYY-MM-DD/
└── final/              # Final compiled highlight reel(s)
    └── highlights_YYYYMMDD_HHMMSS.mp4
```

---

### Football API Providers

| Provider | Free tier | Docs |
|----------|-----------|------|
| API-Football | 100 req/day | [api-football.com](https://www.api-football.com/) |
| football-data.org | 10 req/min | [football-data.org](https://www.football-data.org/) |
| TheSportsDB | Yes (limited) | [thesportsdb.com](https://www.thesportsdb.com/) |

---

### Twitter / X Notes

- Video upload requires **Elevated access** in the Twitter Developer Portal.
- Maximum video size: **512 MB** (Twitter limit).
- Video must be MP4, H.264, ≤ 2:20 minutes for standard tweets.

### YouTube Notes

- On first run, a browser window will open for OAuth 2.0 authorisation.
- The token is cached to `youtube_token.json` for subsequent runs.
- Uploaded videos use the privacy status set in `config.yaml` (`public` / `private` / `unlisted`).
