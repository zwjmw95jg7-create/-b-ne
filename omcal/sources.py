"""Récupération des matchs (fixtur.es) et des diffuseurs TV (Foot Mercato)."""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

FIXTURES_URL = "https://fixtur.es/en/team/olympique-marseille"
FOOTMERCATO_TV_URL = "https://www.footmercato.net/programme-tv/club/om"
FOOTMERCATO_BASE = "https://www.footmercato.net"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class Fixture:
    """Un match tel que publié par fixtur.es."""

    source_id: str
    home: str
    away: str
    competition: str  # ex. "Ligue 1 2026-2027"
    start: datetime  # aware
    end: datetime | None
    time_known: bool
    venue: str = ""
    status: str = "scheduled"  # scheduled | postponed | cancelled
    score: str = ""


@dataclass
class Broadcast:
    """Un match du programme TV Foot Mercato."""

    home: str
    away: str
    start: datetime  # aware
    channels: list[str] = field(default_factory=list)
    url: str = ""


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# fixtur.es
# --------------------------------------------------------------------------- #

_TAG_RE = re.compile(r"\s*\[[^\]]+\]")
_SCORE_RE = re.compile(r"\s*\(([^)]*\d[^)]*)\)\s*$")

_STATUS = {
    "EventPostponed": "postponed",
    "EventCancelled": "cancelled",
    "EventRescheduled": "scheduled",
    "EventScheduled": "scheduled",
}


def parse_fixtures(html: str) -> list[Fixture]:
    soup = BeautifulSoup(html, "html.parser")
    fixtures: list[Fixture] = []
    for div in soup.find_all("div", id=re.compile(r"^fi_event_\d+$")):
        script = div.find("script", type="application/ld+json")
        if script is None or not script.string:
            continue
        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            continue
        if data.get("@type") != "SportsEvent":
            continue

        name = data.get("name", "")
        score_match = _SCORE_RE.search(name)
        score = score_match.group(1) if score_match else ""

        home = (data.get("homeTeam") or {}).get("name", "").strip()
        away = (data.get("awayTeam") or {}).get("name", "").strip()
        if not home or not away:
            clean = _SCORE_RE.sub("", _TAG_RE.sub("", name))
            if " - " not in clean:
                continue
            home, away = (part.strip() for part in clean.split(" - ", 1))

        start = datetime.fromisoformat(data["startDate"])
        end = datetime.fromisoformat(data["endDate"]) if data.get("endDate") else None
        time_tag = div.find("time")
        time_known = not (time_tag is not None and time_tag.get("data-time-known") == "0")

        status_key = str(data.get("eventStatus", "")).rsplit("/", 1)[-1]
        fixtures.append(
            Fixture(
                source_id=div["id"].removeprefix("fi_event_"),
                home=home,
                away=away,
                competition=data.get("description", "").strip(),
                start=start,
                end=end,
                time_known=time_known,
                venue=((data.get("location") or {}).get("name") or "").strip(),
                status=_STATUS.get(status_key, "scheduled"),
                score=score,
            )
        )
    return fixtures


# --------------------------------------------------------------------------- #
# Foot Mercato
# --------------------------------------------------------------------------- #


def parse_footmercato(html: str) -> list[Broadcast]:
    soup = BeautifulSoup(html, "html.parser")
    broadcasts: list[Broadcast] = []
    for match in soup.select("div.matchFull"):
        teams = [t.get_text(strip=True) for t in match.select(".matchTeam__name")]
        time_tag = match.select_one("time[datetime]")
        if len(teams) < 2 or time_tag is None:
            continue
        channels = []
        for img in match.select("img.matchFull__broadcastImage"):
            alt = (img.get("alt") or "").strip()
            alt = re.sub(r"^Logo\s+", "", alt)
            if alt and alt not in channels:
                channels.append(alt)
        link = match.select_one("a[href]")
        href = link["href"] if link else ""
        if href.startswith("/"):
            href = FOOTMERCATO_BASE + href
        broadcasts.append(
            Broadcast(
                home=teams[0],
                away=teams[1],
                start=datetime.fromisoformat(time_tag["datetime"]),
                channels=channels,
                url=href,
            )
        )
    return broadcasts


# --------------------------------------------------------------------------- #
# Rapprochement fixtur.es <-> Foot Mercato
# --------------------------------------------------------------------------- #

_STOPWORDS = {
    "fc", "sc", "ac", "as", "rc", "cf", "afc", "ogc", "sco", "pfc", "fk", "sk",
    "club", "de", "du", "la", "le", "les", "olympique", "stade", "real", "sporting",
    "racing", "union", "athletic", "atletico", "1", "29", "vs",
}
_MARSEILLE = {"marseille", "om"}


def _tokens(name: str) -> set[str]:
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", norm.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1} or set(words)


def _is_om(name: str) -> bool:
    return bool(_tokens(name) & _MARSEILLE)


def _opponent(home: str, away: str) -> tuple[str, bool]:
    """Renvoie (adversaire, om_a_domicile)."""
    if _is_om(home):
        return away, True
    return home, False


def match_broadcast(
    fixture: Fixture, broadcasts: list[Broadcast], max_days: int = 4
) -> Broadcast | None:
    """Trouve le match Foot Mercato correspondant à un match fixtur.es."""
    opp, om_home = _opponent(fixture.home, fixture.away)
    opp_tokens = _tokens(opp)
    best: tuple[float, Broadcast] | None = None
    for b in broadcasts:
        delta = abs(b.start - fixture.start)
        if delta > timedelta(days=max_days):
            continue
        b_opp, b_om_home = _opponent(b.home, b.away)
        # Les adversaires sont aussi présents dans le slug de l'URL Foot Mercato
        b_tokens = _tokens(b_opp) | _tokens(b.url.rsplit("/", 1)[-1].replace("-", " "))
        b_tokens -= _MARSEILLE
        overlap = len(opp_tokens & b_tokens)
        same_day = delta < timedelta(hours=12)
        if overlap == 0 and not (same_day and b_om_home == om_home):
            continue
        score = overlap * 2 + (1 if b_om_home == om_home else 0) - delta.total_seconds() / 86400
        if best is None or score > best[0]:
            best = (score, b)
    return best[1] if best else None
