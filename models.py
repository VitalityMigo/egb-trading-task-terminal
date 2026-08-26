"""
models.py — structures de données partagées (tâches, adjudications, occurrences).

Ce module ne contient aucune logique métier (pas de calcul de date, pas de règle
d'urgence) : uniquement la forme des objets et leur (dé)sérialisation JSON.
La logique vit dans task_service.py / auction_service.py / business_days.py.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

from constants import RECURRENCE_ONCE


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Task:
    name: str
    time: str  # "HH:MM"
    recurrence: str = RECURRENCE_ONCE
    id: str = field(default_factory=new_id)
    # ONCE -> date précise (YYYY-MM-DD) ; WEEKLY -> jour de semaine 0=lundi..6=dimanche
    recurrence_date: Optional[str] = None
    recurrence_weekday: Optional[int] = None
    # Date de création (YYYY-MM-DD) : plancher en dessous duquel on ne génère
    # jamais d'occurrence pour les récurrences ouvertes (business_daily/daily/weekly).
    created_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    # Dates (YYYY-MM-DD) auxquelles cette tâche a été marquée faite. Pour une
    # tâche "once" il n'y a qu'une date pertinente (recurrence_date) ; pour une
    # tâche récurrente, chaque occurrence a sa propre date dans cette liste.
    done_dates: list[str] = field(default_factory=list)
    # Dates (YYYY-MM-DD) explicitement supprimées pour une tâche récurrente
    # ("supprimer uniquement l'occurrence du jour" plutôt que toute la série).
    excluded_dates: list[str] = field(default_factory=list)
    # "manual" (créée à la main) ou "auto" (générée depuis une adjudication).
    source: str = "manual"
    auction_id: Optional[str] = None
    # Champs portés depuis l'adjudication d'origine, ex. {"pays": "France", "type": "Bond"}.
    details: dict[str, Any] = field(default_factory=dict)
    # Note libre, optionnelle, saisie par l'utilisateur.
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        known = {f: data.get(f) for f in cls.__dataclass_fields__ if f in data}
        # valeurs par défaut robustes si le JSON provient d'une version antérieure
        known.setdefault("done_dates", data.get("done_dates", []))
        known.setdefault("excluded_dates", data.get("excluded_dates", []))
        known.setdefault("details", data.get("details", {}))
        return cls(**known)


@dataclass
class Auction:
    country: str
    date: str  # YYYY-MM-DD, obligatoire
    id: str = field(default_factory=new_id)
    time: Optional[str] = None          # "HH:MM"
    type: Optional[str] = None          # "Bills" | "Bond"
    instrument: Optional[str] = None
    maturity: Optional[str] = None      # YYYY-MM-DD
    volume: Optional[float] = None      # en millions
    nco: Optional[bool] = None
    # Note libre, optionnelle, saisie par l'utilisateur.
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Auction":
        known = {f: data.get(f) for f in cls.__dataclass_fields__ if f in data}
        return cls(**known)


@dataclass
class Occurrence:
    """Une instance concrète d'une tâche à une date donnée (calculée à la volée,
    jamais persistée telle quelle)."""

    task_id: str
    name: str
    date: str          # YYYY-MM-DD
    time: str           # "HH:MM"
    dt: datetime         # date+heure combinées, pour tri et calcul d'urgence
    status: str           # "urgent" | "done" | "neutral"
    is_recurring: bool
    source: str
    details: dict[str, Any] = field(default_factory=dict)
    auction_id: Optional[str] = None
    note: Optional[str] = None
