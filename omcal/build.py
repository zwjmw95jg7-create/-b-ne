"""Construit le calendrier .ics de l'OM à partir des sources et de l'état précédent."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import ics
from .sources import (
    FIXTURES_URL,
    FOOTMERCATO_TV_URL,
    Broadcast,
    Fixture,
    fetch,
    match_broadcast,
    parse_fixtures,
    parse_footmercato,
)

PARIS = ZoneInfo("Europe/Paris")

SEASON_START = datetime(2026, 7, 1, tzinfo=PARIS)
SEASON_END = datetime(2027, 7, 1, tzinfo=PARIS)

# Compétitions retenues (sous-chaîne de la description fixtur.es) -> libellé français.
# Ajoutez par exemple ("Trophée des Champions", "Trophée des Champions") si besoin.
COMPETITIONS = [
    ("Ligue 1", "Ligue 1"),
    ("Champions League", "Ligue des champions"),
    ("Europa League", "Ligue Europa"),
    ("Conference League", "Ligue Europa Conférence"),
    ("Coupe de France", "Coupe de France"),
]

TEAM_SHORT_NAMES = {"Olympique Marseille": "OM"}
DEFAULT_DURATION = timedelta(minutes=105)
UID_DOMAIN = "om-calendar.github.io"
CHANNEL_SEPARATOR = " / "
TBA = "chaîne à venir"

CALENDAR_NAME = "OM 2026-2027"
CALENDAR_DESC = (
    "Matchs de l'Olympique de Marseille 2026-2027 (Ligue 1, coupes d'Europe, "
    "Coupe de France) avec la chaîne TV française."
)


def competition_fr(competition: str) -> str | None:
    for needle, label in COMPETITIONS:
        if needle.lower() in competition.lower():
            return label
    return None


def short(team: str) -> str:
    return TEAM_SHORT_NAMES.get(team, team)


def _fingerprint(record: dict) -> str:
    keys = ("start", "end", "time_known", "summary", "description", "location", "url", "ics_status")
    payload = json.dumps({k: record.get(k) for k in keys}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _find_previous(fx: Fixture, state: dict, current_ids: set[str]) -> dict | None:
    """Retrouve l'événement déjà publié pour ce match.

    D'abord par identifiant fixtur.es ; sinon (si la source a recréé le match
    sous un autre identifiant) par affiche + compétition, pour conserver l'UID.
    """
    if fx.source_id in state:
        return state[fx.source_id]
    for sid, rec in state.items():
        if sid in current_ids:
            continue
        if (rec["home"], rec["away"], rec["competition"]) == (fx.home, fx.away, fx.competition):
            return rec
    return None


def build_record(
    fx: Fixture,
    broadcast: Broadcast | None,
    previous: dict | None,
    now: datetime,
) -> dict:
    duration = (fx.end - fx.start) if fx.end and fx.end > fx.start else DEFAULT_DURATION
    start, time_known = fx.start, fx.time_known
    if broadcast is not None:
        # Le programme TV français reflète les reprogrammations de la LFP/UEFA.
        start, time_known = broadcast.start, True
    end = start + duration

    channels: list[str] = []
    if broadcast is not None and broadcast.channels:
        channels = broadcast.channels
    elif previous is not None:
        channels = previous.get("channels", [])

    finished = end < now
    comp_label = competition_fr(fx.competition) or fx.competition
    season_match = re.search(r"\d{4}-\d{4}", fx.competition)
    season = f" ({season_match.group()})" if season_match else ""

    title = f"{short(fx.home)} - {short(fx.away)}"
    if channels:
        title += f" · {CHANNEL_SEPARATOR.join(channels)}"
    elif not finished:
        title += f" · {TBA}"
    if fx.status == "postponed":
        title = f"[Reporté] {title}"
    elif fx.status == "cancelled":
        title = f"[Annulé] {title}"

    channel_text = CHANNEL_SEPARATOR.join(channels) if channels else ("à venir" if not finished else "non renseignée")
    desc = [
        f"{fx.home} - {fx.away}",
        f"Compétition : {comp_label}{season}",
        f"Chaîne TV : {channel_text}",
    ]
    if fx.venue:
        desc.append(f"Lieu : {fx.venue}")
    if fx.score:
        desc.append(f"Score : {fx.score}")
    if not time_known:
        desc.append("Horaire à confirmer")
    desc.append("")
    desc.append(f"Sources : {FIXTURES_URL} · {FOOTMERCATO_TV_URL}")

    url = broadcast.url if broadcast is not None and broadcast.url else (
        previous.get("url") if previous else FIXTURES_URL
    )

    record = {
        "source_id": fx.source_id,
        "uid": previous["uid"] if previous else f"om-{fx.source_id}@{UID_DOMAIN}",
        "home": fx.home,
        "away": fx.away,
        "competition": fx.competition,
        "competition_fr": comp_label,
        "start": start.astimezone(timezone.utc).isoformat(),
        "end": end.astimezone(timezone.utc).isoformat(),
        "time_known": time_known,
        "channels": channels,
        "summary": title,
        "description": "\n".join(desc),
        "location": fx.venue,
        "url": url or FIXTURES_URL,
        "ics_status": {"cancelled": "CANCELLED", "postponed": "TENTATIVE"}.get(fx.status, "CONFIRMED"),
    }
    record["fingerprint"] = _fingerprint(record)

    if previous is None:
        record.update(sequence=0, created=now.isoformat(), last_modified=now.isoformat())
    elif previous.get("fingerprint") != record["fingerprint"]:
        seq = previous.get("sequence", 0)
        if previous.get("start") != record["start"] or previous.get("summary") != record["summary"]:
            seq += 1
        record.update(sequence=seq, created=previous["created"], last_modified=now.isoformat())
    else:
        record.update(
            sequence=previous.get("sequence", 0),
            created=previous["created"],
            last_modified=previous["last_modified"],
        )
    return record


def update(
    state: dict,
    fixtures: list[Fixture] | None,
    broadcasts: list[Broadcast] | None,
    now: datetime,
) -> dict:
    """Renvoie le nouvel état {source_id: record}."""
    new_state = dict(state)
    if fixtures is None:
        fixtures = []
    selected = [
        fx
        for fx in fixtures
        if competition_fr(fx.competition) and SEASON_START <= fx.start < SEASON_END
    ]
    current_ids = {fx.source_id for fx in selected}
    for fx in selected:
        previous = _find_previous(fx, state, current_ids)
        if previous is not None and previous["source_id"] != fx.source_id:
            new_state.pop(previous["source_id"], None)
        bc = match_broadcast(fx, broadcasts) if broadcasts else None
        new_state[fx.source_id] = build_record(fx, bc, previous, now)
    return new_state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default="data/state.json", type=Path)
    parser.add_argument("--output", default="public/om.ics", type=Path)
    parser.add_argument("--fixtures-html", type=Path, help="fichier local au lieu de fixtur.es")
    parser.add_argument("--footmercato-html", type=Path, help="fichier local au lieu de Foot Mercato")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    state = state.get("events", {})

    fixtures: list[Fixture] | None
    try:
        html = args.fixtures_html.read_text() if args.fixtures_html else fetch(FIXTURES_URL)
        fixtures = parse_fixtures(html)
        print(f"fixtur.es : {len(fixtures)} matchs trouvés")
        if not fixtures:
            raise ValueError("aucun match trouvé (structure de page modifiée ?)")
    except Exception as exc:  # on garde l'état précédent plutôt que de vider le calendrier
        print(f"::warning::fixtur.es indisponible : {exc}", file=sys.stderr)
        fixtures = None

    broadcasts: list[Broadcast] | None
    try:
        html = args.footmercato_html.read_text() if args.footmercato_html else fetch(FOOTMERCATO_TV_URL)
        broadcasts = parse_footmercato(html)
        print(f"Foot Mercato : {len(broadcasts)} matchs avec programme TV")
    except Exception as exc:
        print(f"::warning::Foot Mercato indisponible : {exc}", file=sys.stderr)
        broadcasts = None

    if fixtures is None and not state:
        print("::error::aucune donnée disponible, rien à publier", file=sys.stderr)
        return 1

    new_state = update(state, fixtures, broadcasts, now)
    events = sorted(new_state.values(), key=lambda r: r["start"])

    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(
        json.dumps({"events": dict(sorted(new_state.items()))}, indent=2, ensure_ascii=False) + "\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(ics.build_calendar(events, CALENDAR_NAME, CALENDAR_DESC).encode("utf-8"))

    changed = sum(1 for k, r in new_state.items() if state.get(k, {}).get("fingerprint") != r["fingerprint"])
    print(f"{len(events)} événements écrits dans {args.output} ({changed} nouveaux ou modifiés)")
    return 0
