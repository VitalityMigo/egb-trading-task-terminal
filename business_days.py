"""
business_days.py — arithmétique en jours ouvrés (lundi-vendredi).

Pas de calendrier de jours fériés pour l'instant (non demandé dans le blueprint) :
"jour ouvré" = du lundi au vendredi. Si un calendrier de fériés est nécessaire un
jour, il suffira de brancher une fonction `is_holiday(date) -> bool` ici, sans
toucher aux appelants (task_service, auction_service).
"""

from __future__ import annotations

from datetime import date, timedelta

_WEEKEND = (5, 6)  # samedi, dimanche (date.weekday() : lundi=0 ... dimanche=6)


def is_business_day(d: date) -> bool:
    return d.weekday() not in _WEEKEND


def add_business_days(d: date, n: int) -> date:
    """Décale `d` de `n` jours ouvrés (n peut être négatif). `d` lui-même n'a
    pas besoin d'être un jour ouvré au départ ; seul le résultat l'est."""
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    current = d
    while remaining > 0:
        current += timedelta(days=step)
        if is_business_day(current):
            remaining -= 1
    return current


def next_business_day(d: date) -> date:
    """Premier jour ouvré strictement après `d`."""
    return add_business_days(d, 1)


def previous_business_day(d: date) -> date:
    """Premier jour ouvré strictement avant `d`."""
    return add_business_days(d, -1)
