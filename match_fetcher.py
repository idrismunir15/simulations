"""
match_fetcher.py
~~~~~~~~~~~~~~~~
Fetch upcoming friendly international matches before the World Cup
using a configurable football data API, and persist them to SQLite.

Supported API providers:
  - api_football   (https://www.api-football.com/)
  - football_data  (https://www.football-data.org/)
  - thesportsdb    (https://www.thesportsdb.com/)
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Create the matches table if it does not exist and return a connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS matches (
            id              TEXT PRIMARY KEY,
            home_team       TEXT NOT NULL,
            away_team       TEXT NOT NULL,
            match_date      TEXT NOT NULL,
            competition     TEXT,
            status          TEXT,
            source          TEXT,
            video_path      TEXT,
            highlights_json TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    return conn


def upsert_match(conn: sqlite3.Connection, match: dict) -> None:
    """Insert or replace a match record."""
    conn.execute(
        """
        INSERT OR REPLACE INTO matches
            (id, home_team, away_team, match_date, competition, status, source)
        VALUES
            (:id, :home_team, :away_team, :match_date, :competition, :status, :source)
        """,
        match,
    )
    conn.commit()


def get_all_matches(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all stored matches ordered by date."""
    return conn.execute(
        "SELECT * FROM matches ORDER BY match_date ASC"
    ).fetchall()


def update_match_video_path(conn: sqlite3.Connection, match_id: str, path: str) -> None:
    conn.execute(
        "UPDATE matches SET video_path = ? WHERE id = ?", (path, match_id)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# API adapters
# ---------------------------------------------------------------------------

class ApiFootballFetcher:
    """
    Fetches friendly matches via api-football.com (RapidAPI wrapper).
    Docs: https://www.api-football.com/documentation-v3
    """

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str):
        self.headers = {
            "x-apisports-key": api_key,
        }

    def fetch_friendlies(self, from_date: str, to_date: str) -> list[dict]:
        """
        Return a list of normalised match dicts for International Friendlies
        (league_id=10) between from_date and to_date (YYYY-MM-DD).
        """
        params = {
            "league": 10,  # FIFA Internationals / Friendlies
            "from": from_date,
            "to": to_date,
            "season": datetime.strptime(from_date, "%Y-%m-%d").year,
        }
        response = requests.get(
            f"{self.BASE_URL}/fixtures",
            headers=self.headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        matches = []
        for fixture in data.get("response", []):
            f = fixture.get("fixture", {})
            teams = fixture.get("teams", {})
            league = fixture.get("league", {})
            matches.append(
                {
                    "id": f"apif_{f['id']}",
                    "home_team": teams.get("home", {}).get("name", "Unknown"),
                    "away_team": teams.get("away", {}).get("name", "Unknown"),
                    "match_date": f.get("date", "")[:10],
                    "competition": league.get("name", "Friendly"),
                    "status": f.get("status", {}).get("short", "NS"),
                    "source": "api_football",
                }
            )
        return matches


class FootballDataFetcher:
    """
    Fetches friendly matches via football-data.org API.
    Docs: https://www.football-data.org/documentation/quickstart
    """

    BASE_URL = "https://api.football-data.org/v4"
    # Competition code for International Friendlies
    COMPETITION = "FL1"  # placeholder; football-data.org doesn't expose a direct friendly competition

    def __init__(self, api_key: str):
        self.headers = {"X-Auth-Token": api_key}

    def fetch_friendlies(self, from_date: str, to_date: str) -> list[dict]:
        params = {
            "dateFrom": from_date,
            "dateTo": to_date,
        }
        response = requests.get(
            f"{self.BASE_URL}/matches",
            headers=self.headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        matches = []
        for m in data.get("matches", []):
            competition = m.get("competition", {})
            if "friend" not in competition.get("name", "").lower():
                continue
            home = m.get("homeTeam", {}).get("name", "Unknown")
            away = m.get("awayTeam", {}).get("name", "Unknown")
            matches.append(
                {
                    "id": f"fd_{m['id']}",
                    "home_team": home,
                    "away_team": away,
                    "match_date": m.get("utcDate", "")[:10],
                    "competition": competition.get("name", "Friendly"),
                    "status": m.get("status", "SCHEDULED"),
                    "source": "football_data",
                }
            )
        return matches


class TheSportsDBFetcher:
    """
    Fetches events via TheSportsDB free API (no auth required for free tier).
    Docs: https://www.thesportsdb.com/api.php
    """

    BASE_URL = "https://www.thesportsdb.com/api/v1/json"

    def __init__(self, api_key: str = "3"):
        self.api_key = api_key  # "3" is the free public key

    def fetch_friendlies(self, from_date: str, to_date: str) -> list[dict]:
        """
        TheSportsDB free tier doesn't support date ranges natively.
        We query the "Soccer – International" league (id 4479) for the
        next events and filter by date.
        """
        league_id = "4479"
        response = requests.get(
            f"{self.BASE_URL}/{self.api_key}/eventsnextleague.php",
            params={"id": league_id},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
        to_dt = datetime.strptime(to_date, "%Y-%m-%d")
        matches = []
        for event in data.get("events") or []:
            event_date_str = event.get("dateEvent", "")
            try:
                event_dt = datetime.strptime(event_date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if not (from_dt <= event_dt <= to_dt):
                continue
            matches.append(
                {
                    "id": f"tsdb_{event['idEvent']}",
                    "home_team": event.get("strHomeTeam", "Unknown"),
                    "away_team": event.get("strAwayTeam", "Unknown"),
                    "match_date": event_date_str,
                    "competition": event.get("strLeague", "Friendly"),
                    "status": event.get("strStatus", "Not Started"),
                    "source": "thesportsdb",
                }
            )
        return matches


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def fetch_and_store_matches(config: dict) -> list[dict]:
    """
    Main entry point: fetch friendly matches and persist to SQLite.

    Returns the list of match dicts that were stored.
    """
    wc_cfg = config["worldcup"]
    worldcup_date = datetime.strptime(wc_cfg["start_date"], "%Y-%m-%d")
    lookback = int(wc_cfg["lookback_days"])
    from_date = (worldcup_date - timedelta(days=lookback)).strftime("%Y-%m-%d")
    to_date = (worldcup_date - timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info("Fetching friendlies from %s to %s", from_date, to_date)

    api_cfg = config["football_api"]
    provider = api_cfg["provider"]

    if provider == "api_football":
        fetcher = ApiFootballFetcher(api_cfg["api_football_key"])
    elif provider == "football_data":
        fetcher = FootballDataFetcher(api_cfg["football_data_key"])
    elif provider == "thesportsdb":
        fetcher = TheSportsDBFetcher(api_cfg.get("thesportsdb_key", "3"))
    else:
        raise ValueError(f"Unknown API provider: {provider!r}")

    matches = fetcher.fetch_friendlies(from_date, to_date)
    logger.info("Found %d friendly match(es)", len(matches))

    db_path = config["compilation"]["database_path"]
    conn = init_db(db_path)
    for match in matches:
        upsert_match(conn, match)
        logger.debug(
            "Stored: %s vs %s on %s",
            match["home_team"],
            match["away_team"],
            match["match_date"],
        )
    conn.close()
    return matches


def load_matches_from_db(config: dict) -> list[dict]:
    """Load all previously stored matches from the database."""
    db_path = config["compilation"]["database_path"]
    conn = init_db(db_path)
    rows = get_all_matches(conn)
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import sys
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    os.makedirs(cfg["compilation"]["output_dir"], exist_ok=True)
    stored = fetch_and_store_matches(cfg)
    print(f"Fetched and stored {len(stored)} match(es).")
