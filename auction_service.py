"""
auction_service.py — CRUD des adjudications, création hebdomadaire en lot,
pagination, et génération automatique des tâches liées (section 2.3 du
blueprint). Toute la logique de date passe par business_days.py et
task_service.py — rien n'est recalculé ici en dehors des règles propres aux
adjudications (offsets +1h/+2h/J-1/J-2 par rapport à l'adjudication).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import business_days
import task_service
from constants import (
    COUNTRIES,
    AUCTION_TYPES,
    AUCTIONS_FILE,
    AUTO_TASK_DEFAULT_TIME,
    RECURRENCE_ONCE,
)
from models import Auction, Task
from storage import load_json, save_json

DATE_FMT = task_service.DATE_FMT
TIME_FMT = task_service.TIME_FMT


class AuctionServiceError(ValueError):
    """Erreur métier : donnée invalide, adjudication introuvable, etc."""


DEFAULT_PAGE_SIZE = 10


def get_countries() -> list[str]:
    return list(COUNTRIES)


def get_auction_types() -> list[str]:
    return list(AUCTION_TYPES)


# ---------------------------------------------------------------------------
# Persistance
# ---------------------------------------------------------------------------

def _load_auctions() -> list[Auction]:
    raw = load_json(AUCTIONS_FILE, [])
    return [Auction.from_dict(d) for d in raw]


def _save_auctions(auctions: list[Auction]) -> None:
    save_json(AUCTIONS_FILE, [a.to_dict() for a in auctions])


def list_auctions_sorted() -> list[Auction]:
    auctions = _load_auctions()
    auctions.sort(key=lambda a: (a.date, a.time or "99:99"))
    return auctions


def get_auction(auction_id: str) -> Optional[Auction]:
    for a in _load_auctions():
        if a.id == auction_id:
            return a
    return None


def paginate(items: list, page: int, page_size: int = DEFAULT_PAGE_SIZE) -> tuple[list, int]:
    """Retourne (éléments de la page, nombre total de pages). `page` est 1-indexé
    et automatiquement borné à [1, total_pages]."""
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    return items[start:start + page_size], total_pages


def get_auctions_in_range(start: date, end: date) -> list[Auction]:
    """Adjudications dont la date tombe dans [start, end] (incluses), triées
    comme list_auctions_sorted(). Alimente la vue globale du navigateur
    jour/semaine (tui/app.py), qui remplace la pagination fixe."""
    auctions = list_auctions_sorted()
    return [a for a in auctions if start <= task_service.parse_date(a.date) <= end]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_fields(
    country: str,
    date: str,
    time: Optional[str],
    type: Optional[str],
    maturity: Optional[str],
    volume: Optional[float],
) -> None:
    if country not in COUNTRIES:
        raise AuctionServiceError(f"Pays invalide : {country!r}")
    if not task_service.is_valid_date(date):
        raise AuctionServiceError(f"Date invalide : {date!r} (attendu YYYY-MM-DD)")
    if time is not None and time != "" and not task_service.is_valid_time(time):
        raise AuctionServiceError(f"Heure invalide : {time!r} (attendu HH:MM)")
    if type is not None and type != "" and type not in AUCTION_TYPES:
        raise AuctionServiceError(f"Type invalide : {type!r}")
    if maturity is not None and maturity != "" and not task_service.is_valid_date(maturity):
        raise AuctionServiceError(f"Date de maturité invalide : {maturity!r}")
    if volume is not None and volume != "":
        try:
            float(volume)
        except (TypeError, ValueError):
            raise AuctionServiceError(f"Volume invalide : {volume!r} (nombre attendu)")


def _clean_optional(value):
    """Normalise une chaîne vide envoyée par un formulaire en None."""
    if value == "":
        return None
    return value


# ---------------------------------------------------------------------------
# Génération automatique des tâches (section 2.3 du blueprint)
# ---------------------------------------------------------------------------

def generate_tasks_for_auction(auction: Auction) -> tuple[list[Task], list[str]]:
    """Applique les 5 règles de génération et retourne (tâches créées, avertissements).
    Un avertissement apparaît quand une règle nécessitant l'heure de l'adjudication
    (règles 2 et 4) ne peut pas s'appliquer faute d'heure renseignée."""
    created: list[Task] = []
    warnings: list[str] = []

    a_date = task_service.parse_date(auction.date)
    has_time = bool(auction.time) and task_service.is_valid_time(auction.time)
    a_datetime = task_service.occurrence_datetime(a_date, auction.time) if has_time else None
    details = {"pays": auction.country, "type": auction.type}

    def _add(name: str, when, when_time: str) -> None:
        created.append(
            task_service.add_task(
                name=name,
                time=when_time,
                recurrence=RECURRENCE_ONCE,
                recurrence_date=when.strftime(DATE_FMT),
                source="auto",
                auction_id=auction.id,
                details=dict(details),
            )
        )

    # 1. J-2 jours ouvrés avant l'adjudication -> Bond Definition
    d1 = business_days.add_business_days(a_date, -2)
    _add("Bond Definition", d1, AUTO_TASK_DEFAULT_TIME)

    # 2. 1h après l'heure de l'adjudication -> Bond Historisation
    if a_datetime:
        dt2 = a_datetime + timedelta(hours=1)
        _add("Bond Historisation", dt2.date(), dt2.strftime(TIME_FMT))
    else:
        warnings.append(
            "Bond Historisation non générée : l'adjudication n'a pas d'heure renseignée."
        )

    # 3. J-1 jour ouvré avant, si type = Bills -> Pre-Auction Bills Report
    if auction.type == "Bills":
        d3 = business_days.add_business_days(a_date, -1)
        _add("Pre-Auction Bills Report", d3, AUTO_TASK_DEFAULT_TIME)

    # 4. 2h après, si NCO = Oui et type = Bond -> NCO Estimate
    if auction.nco and auction.type == "Bond":
        if a_datetime:
            dt4 = a_datetime + timedelta(hours=2)
            _add("NCO Estimate", dt4.date(), dt4.strftime(TIME_FMT))
        else:
            warnings.append(
                "NCO Estimate non générée : l'adjudication n'a pas d'heure renseignée."
            )

    # 5. Le jour même, si pays = Italie -> Italian Fees
    if auction.country == "Italie":
        _add("Italian Fees", a_date, AUTO_TASK_DEFAULT_TIME)

    return created, warnings


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def add_auction(
    country: str,
    date: str,
    time: Optional[str] = None,
    type: Optional[str] = None,
    instrument: Optional[str] = None,
    maturity: Optional[str] = None,
    volume: Optional[float] = None,
    nco: Optional[bool] = None,
    note: Optional[str] = None,
) -> tuple[Auction, list[str]]:
    time = _clean_optional(time)
    type = _clean_optional(type)
    instrument = _clean_optional(instrument)
    maturity = _clean_optional(maturity)
    volume = _clean_optional(volume)
    note = _clean_optional(note)

    _validate_fields(country, date, time, type, maturity, volume)

    auction = Auction(
        country=country,
        date=date,
        time=time,
        type=type,
        instrument=instrument,
        maturity=maturity,
        volume=float(volume) if volume is not None else None,
        nco=bool(nco) if nco is not None else None,
        note=note,
    )
    auctions = _load_auctions()
    auctions.append(auction)
    _save_auctions(auctions)

    _, warnings = generate_tasks_for_auction(auction)
    return auction, warnings


def add_weekly_auctions(fields: dict, count: int) -> list[tuple[Auction, list[str]]]:
    """Crée `count` adjudications espacées d'une semaine, à partir de fields["date"]
    (incluse), en réutilisant les mêmes champs pour chacune."""
    if count < 1:
        raise AuctionServiceError("Le nombre d'occurrences doit être >= 1.")
    base_date = task_service.parse_date(fields["date"])
    results = []
    for i in range(count):
        occurrence_fields = dict(fields)
        occurrence_fields["date"] = (base_date + timedelta(weeks=i)).strftime(DATE_FMT)
        results.append(add_auction(**occurrence_fields))
    return results


def update_auction(auction_id: str, fields: dict, regenerate_tasks: bool = False) -> tuple[Auction, list[str]]:
    auctions = _load_auctions()
    for idx, a in enumerate(auctions):
        if a.id != auction_id:
            continue

        country = fields.get("country", a.country)
        date = fields.get("date", a.date)
        time = _clean_optional(fields.get("time", a.time))
        type = _clean_optional(fields.get("type", a.type))
        instrument = _clean_optional(fields.get("instrument", a.instrument))
        maturity = _clean_optional(fields.get("maturity", a.maturity))
        volume = _clean_optional(fields.get("volume", a.volume))
        nco = fields.get("nco", a.nco)
        note = _clean_optional(fields.get("note", a.note))

        _validate_fields(country, date, time, type, maturity, volume)

        a.country = country
        a.date = date
        a.time = time
        a.type = type
        a.instrument = instrument
        a.maturity = maturity
        a.volume = float(volume) if volume is not None else None
        a.nco = bool(nco) if nco is not None else None
        a.note = note

        auctions[idx] = a
        _save_auctions(auctions)

        warnings: list[str] = []
        if regenerate_tasks:
            task_service.delete_tasks_for_auction(auction_id)
            _, warnings = generate_tasks_for_auction(a)
        return a, warnings

    raise AuctionServiceError(f"Adjudication introuvable : {auction_id!r}")


def delete_auction(auction_id: str, cascade: bool = False) -> bool:
    auctions = _load_auctions()
    for idx, a in enumerate(auctions):
        if a.id == auction_id:
            del auctions[idx]
            _save_auctions(auctions)
            if cascade:
                task_service.delete_tasks_for_auction(auction_id)
            return True
    return False
