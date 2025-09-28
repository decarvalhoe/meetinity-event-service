"""Utility helpers for exposing calendar feeds (iCal/ICS)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Mapping

__all__ = ["generate_ics_feed"]


def generate_ics_feed(events: Iterable[Mapping], *, calendar_name: str = "Meetinity Events") -> str:
    """Generate a minimal ICS document for the provided events."""

    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Meetinity//Event Service//FR",
        f"X-WR-CALNAME:{_escape(calendar_name)}",
        "CALSCALE:GREGORIAN",
    ]

    for event in events:
        event_id = event.get("id")
        title = event.get("title") or "Event"
        description = event.get("description") or ""
        event_date = event.get("date") or event.get("event_date")
        if not isinstance(event_date, str):
            continue
        dtstart = event_date.replace("-", "")
        dtend = (datetime.strptime(event_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y%m%d")
        location = event.get("location") or ""
        share = event.get("share") if isinstance(event.get("share"), Mapping) else None
        url = share.get("url") if share else None
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:event-{event_id}@meetinity",
                f"DTSTAMP:{now}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"DTEND;VALUE=DATE:{dtend}",
                f"SUMMARY:{_escape(title)}",
                f"DESCRIPTION:{_escape(description)}",
                f"LOCATION:{_escape(location)}",
            ]
        )
        if url:
            lines.append(f"URL:{_escape(url)}")
        tags = event.get("tags")
        if isinstance(tags, Iterable):
            tag_values = []
            for tag in tags:
                name = tag.get("name") if isinstance(tag, Mapping) else tag
                if isinstance(name, str):
                    tag_values.append(name)
            if tag_values:
                lines.append(f"CATEGORIES:{_escape(','.join(tag_values))}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )
