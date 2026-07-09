"""Human-readable airing schedule lines for anime detail views."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from shared.utils.broadcast_schedule import (
    latest_episode_label,
    next_episode_datetime,
    parse_broadcast,
)


def _resolve_status(
    *,
    status: Optional[str],
    date_from: Optional[int],
    date_to: Optional[int],
    episodes: Optional[int],
) -> str:
    if status is not None:
        normalized = str(status).strip().upper()
        if normalized == "UPDATE":
            return "UNKNOWN"
        if normalized:
            return normalized

    if date_from is None:
        return "UNKNOWN"

    now = datetime.now(timezone.utc)
    try:
        start = datetime.fromtimestamp(int(date_from), timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return "UNKNOWN"

    if start > now:
        return "UPCOMING"

    if date_to is None:
        return "FINISHED" if episodes == 1 else "AIRING"

    try:
        end = datetime.fromtimestamp(int(date_to), timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return "AIRING"

    return "AIRING" if end > now else "FINISHED"


def build_airing_lines(
    *,
    date_from: Optional[int] = None,
    date_to: Optional[int] = None,
    status: Optional[str] = None,
    broadcast: Optional[str] = None,
    episodes: Optional[int] = None,
) -> list[str]:
    """Return contextual airing text lines for an anime detail hero."""
    resolved = _resolve_status(
        status=status,
        date_from=date_from,
        date_to=date_to,
        episodes=episodes,
    )

    if resolved == "UNKNOWN" or date_from is None:
        return []

    try:
        datefrom = datetime.fromtimestamp(int(date_from), timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return []

    dateto: Optional[datetime] = None
    if date_to is not None:
        try:
            dateto = datetime.fromtimestamp(int(date_to), timezone.utc)
        except (OSError, OverflowError, TypeError, ValueError):
            dateto = None

    datetext: list[str] = []
    today = datetime.now(timezone.utc)
    delta = today - datefrom

    if resolved == "FINISHED":
        if dateto is None:
            datetext.append(f"Published on {datefrom.strftime('%d %b %Y')}")
        else:
            datetext.append(
                "From {} to {} ({} days)".format(
                    datefrom.strftime("%d %b %Y"),
                    dateto.strftime("%d %b %Y"),
                    delta.days,
                )
            )
    elif resolved == "AIRING":
        if delta.days == 0:
            datetext.append("Starts airing today!")
        else:
            datetext.append(
                "Since {} ({} days)".format(
                    datefrom.strftime("%d %b %Y"), delta.days
                )
            )

        slot = parse_broadcast(broadcast)
        if slot is not None:
            next_local = next_episode_datetime(slot, now=today)
            datetext.append(
                next_local.strftime("Next episode on %a %d at %H:%M")
            )
            datetext.append(f"Latest episode: {latest_episode_label(slot, now=today)}")
        else:
            days_since = (delta.days - 1) % 7
            date_obj = date.today() - timedelta(days=days_since)
            text = date_obj.strftime("Last episode on %a %d ({})")
            if days_since == 0:
                datetext.append(text.format("Today"))
            elif days_since == 1:
                datetext.append(text.format("Yesterday"))
            elif days_since > 1:
                datetext.append(text.format(f"{days_since} days ago"))
            else:
                datetext.append(text.format("uhh?"))
    elif resolved == "UPCOMING":
        datetext.append(
            "On {} ({} days left)".format(
                datefrom.strftime("%d %b %Y"), -delta.days
            )
        )

    return datetext


def build_airing_lines_from_anime(anime: Any) -> list[str]:
    """Build airing lines from a legacy ``Anime`` object or mapping."""
    if anime is None:
        return []

    def _read(name: str) -> Any:
        if isinstance(anime, dict):
            return anime.get(name)
        return getattr(anime, name, None)

    return build_airing_lines(
        date_from=_read("date_from"),
        date_to=_read("date_to"),
        status=_read("status"),
        broadcast=_read("broadcast"),
        episodes=_read("episodes"),
    )
