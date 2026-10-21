"""Écriture d'un fichier iCalendar (RFC 5545) sans dépendance externe."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Replie les lignes à 75 octets comme l'exige la RFC 5545."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    current = b""
    limit = 75
    for ch in line:
        enc = ch.encode("utf-8")
        if len(current) + len(enc) > limit:
            parts.append(current.decode("utf-8"))
            current = b""
            limit = 74  # la ligne de continuation commence par un espace
        current += enc
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fmt_date(d: date) -> str:
    return d.strftime("%Y%m%d")


def build_calendar(events: list[dict], name: str, description: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//om-calendar//Matchs OM//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape(name)}",
        f"X-WR-CALDESC:{escape(description)}",
        "X-WR-TIMEZONE:Europe/Paris",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    for ev in events:
        lines += _vevent(ev)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def _vevent(ev: dict) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{ev['uid']}",
        f"DTSTAMP:{fmt_utc(datetime.fromisoformat(ev['last_modified']))}",
        f"CREATED:{fmt_utc(datetime.fromisoformat(ev['created']))}",
        f"LAST-MODIFIED:{fmt_utc(datetime.fromisoformat(ev['last_modified']))}",
        f"SEQUENCE:{ev['sequence']}",
    ]
    start = datetime.fromisoformat(ev["start"])
    end = datetime.fromisoformat(ev["end"])
    if ev["time_known"]:
        lines += [f"DTSTART:{fmt_utc(start)}", f"DTEND:{fmt_utc(end)}"]
    else:
        day = start.astimezone(PARIS).date()
        lines += [
            f"DTSTART;VALUE=DATE:{fmt_date(day)}",
            f"DTEND;VALUE=DATE:{fmt_date(day + timedelta(days=1))}",
        ]
    lines += [
        f"SUMMARY:{escape(ev['summary'])}",
        f"DESCRIPTION:{escape(ev['description'])}",
    ]
    if ev.get("location"):
        lines.append(f"LOCATION:{escape(ev['location'])}")
    if ev.get("url"):
        lines.append(f"URL:{ev['url']}")
    lines += [
        f"STATUS:{ev['ics_status']}",
        "TRANSP:OPAQUE",
        f"CATEGORIES:{escape(ev['competition_fr'])}",
    ]
    if ev["time_known"]:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{escape(ev['summary'])}",
            "TRIGGER:-PT30M",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines
