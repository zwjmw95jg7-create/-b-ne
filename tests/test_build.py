from datetime import datetime, timezone
from pathlib import Path

from omcal import ics
from omcal.build import update
from omcal.sources import parse_fixtures, parse_footmercato

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def load():
    fixtures = parse_fixtures((FIXTURES / "fixtures.html").read_text())
    broadcasts = parse_footmercato((FIXTURES / "footmercato.html").read_text())
    return fixtures, broadcasts


def test_parse_sources():
    fixtures, broadcasts = load()
    assert len(fixtures) == 6
    assert fixtures[1].score == "2-5"
    assert fixtures[4].time_known is False
    assert broadcasts[1].channels == ["Canal + Foot", "Canal +"]


def test_competitions_filtered_and_titles():
    fixtures, broadcasts = load()
    state = update({}, fixtures, broadcasts, NOW)
    assert "205818" not in state  # match amical exclu
    assert state["188140"]["summary"] == "OM - Le Havre · DAZN"
    assert state["211249"]["summary"] == "OM - PFC Levski Sofia · Canal + Foot / Canal +"
    assert state["300001"]["summary"] == "Trélissac - OM · chaîne à venir"
    assert "Chaîne TV : à venir" in state["300001"]["description"]
    assert "Compétition : Coupe de France (2026-2027)" in state["300001"]["description"]
    # match passé sans diffuseur connu : pas de mention « à venir »
    assert state["188127"]["summary"] == "Angers SCO - OM"
    assert "Score : 2-5" in state["188127"]["description"]


def test_reschedule_keeps_uid_and_bumps_sequence():
    fixtures, broadcasts = load()
    state = update({}, fixtures, broadcasts, NOW)
    uid = state["300001"]["uid"]

    html = (FIXTURES / "fixtures.html").read_text().replace(
        "2027-01-09T18:00:00+01:00", "2027-01-10T21:00:00+01:00"
    )
    later = NOW.replace(day=22)
    new = update(state, parse_fixtures(html), broadcasts, later)
    assert new["300001"]["uid"] == uid
    assert new["300001"]["start"] == "2027-01-10T20:00:00+00:00"
    assert new["300001"]["sequence"] == 1
    assert new["300001"]["last_modified"] == later.isoformat()
    # les autres matchs sont inchangés
    assert new["188140"]["sequence"] == 0
    assert new["188140"]["last_modified"] == NOW.isoformat()


def test_new_source_id_reuses_uid():
    fixtures, broadcasts = load()
    state = update({}, fixtures, broadcasts, NOW)
    html = (FIXTURES / "fixtures.html").read_text().replace("fi_event_300001", "fi_event_300099")
    new = update(state, parse_fixtures(html), broadcasts, NOW)
    assert "300001" not in new
    assert new["300099"]["uid"] == state["300001"]["uid"]


def test_channel_kept_when_footmercato_unavailable():
    fixtures, broadcasts = load()
    state = update({}, fixtures, broadcasts, NOW)
    new = update(state, fixtures, None, NOW)
    assert new["188140"]["summary"] == "OM - Le Havre · DAZN"


def test_source_failure_keeps_previous_events():
    fixtures, broadcasts = load()
    state = update({}, fixtures, broadcasts, NOW)
    assert update(state, None, broadcasts, NOW) == state


def test_unknown_time_uses_footmercato_or_all_day():
    fixtures, broadcasts = load()
    state = update({}, fixtures, broadcasts, NOW)
    nice = state["188183"]
    assert nice["time_known"] is False
    text = ics.build_calendar(list(state.values()), "OM", "test")
    assert "DTSTART;VALUE=DATE:20261205" in text


def test_ics_output():
    fixtures, broadcasts = load()
    state = update({}, fixtures, broadcasts, NOW)
    text = ics.build_calendar(sorted(state.values(), key=lambda r: r["start"]), "OM", "test")
    assert text.startswith("BEGIN:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == 5
    assert "UID:om-188140@" in text
    assert "DTSTART:20261025T161500Z" in text
    assert text.count("TRIGGER:-PT30M") == 4  # pas d'alarme sur l'événement « journée entière »
    for line in text.split("\r\n"):
        assert len(line.encode()) <= 75
