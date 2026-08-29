"""
auction_service.py — CRUD des adjudications, création hebdomadaire en lot,
pagination, et génération automatique des tâches liées. Toute la logique de
date passe par business_days.py et task_service.py — rien n'est recalculé
ici en dehors des règles propres aux adjudications.

Mapping de génération (round 20, remplace en totalité l'ancienne section 2.3
du blueprint — 5 règles génériques) : arbre de décision par pays et par type
d'adjudication (Bills/Bond), fourni explicitement par Augustin, voir
_expected_task_specs() ci-dessous. Le champ NCO de l'adjudication n'influence
plus aucune règle (round 20, demande explicite) — reste un champ purement
informatif.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import business_days
import task_service
from constants import (
    COUNTRIES,
    COUNTRY_CODES,
    AUCTION_TYPES,
    AUCTIONS_FILE,
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


def get_upcoming_auctions() -> list[Auction]:
    """Adjudications dont la date est aujourd'hui ou plus tard — jamais dans
    le passé. Round 18 : peuple le filtre "par adjudication" de la vue
    Tâches (tui/app.py) — une adjudication déjà passée n'a plus vocation à
    servir de filtre (comparaison lexicale de chaînes "YYYY-MM-DD", valide
    car équivalente à l'ordre chronologique, déjà le pattern utilisé
    ailleurs dans ce module)."""
    today = date.today().strftime(DATE_FMT)
    return [a for a in list_auctions_sorted() if a.date >= today]


def format_auction_short_label(auction: Auction) -> str:
    """Étiquette compacte "<code pays> <jour>/<mois>" (sans année), ex.
    "DE 15/09" — round 18, réutilisée à la fois par le filtre "par
    adjudication" de la vue Tâches et par l'indicateur de provenance d'une
    tâche (TaskDetailModal). `constants.COUNTRY_CODES` est la même table que
    celle utilisée depuis le round 11 pour la colonne "Détails" de la vue
    Tâches — même convention de code, un seul endroit où elle est définie."""
    code = COUNTRY_CODES.get(auction.country, auction.country)
    _, month, day = auction.date.split("-")
    return f"{code} {day}/{month}"


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
# Génération automatique des tâches — round 20, mapping par pays × type
# (Bills/Bond) redéfini en totalité par Augustin, remplace l'ancienne
# section 2.3 du blueprint (5 règles génériques). Le champ NCO n'intervient
# plus jamais dans ces règles (demande explicite d'Augustin) — il reste un
# champ purement informatif de l'adjudication.
# ---------------------------------------------------------------------------

# Décalage (jours ouvrés, T+n) + heure de la tâche "NCO Historisation", par
# pays et par type d'adjudication. Un pays absent de cette table (Allemagne,
# ou tout pays hors des 6 listés explicitement par Augustin — Cas 7 "autre
# pays") n'a simplement pas de NCO Historisation générée. France a d'abord
# été formulée par Augustin sans "ouvré" (lendemain calendaire) au round 20,
# puis explicitement corrigée en "lendemain ouvré" au round 21 — alignée ici
# sur Italie/Portugal (T+1 jour ouvré, 17:30), plus de cas particulier.
_NCO_HISTORISATION_BUSINESS_DAYS: dict[str, dict[str, tuple[int, str]]] = {
    "France": {"Bills": (1, "17:30"), "Bond": (1, "17:30")},
    "Italie": {"Bills": (1, "17:30"), "Bond": (1, "17:30")},
    "Espagne": {"Bills": (2, "15:30"), "Bond": (2, "15:30")},
    "Belgique": {"Bills": (2, "15:30"), "Bond": (3, "15:30")},
    "Portugal": {"Bills": (1, "17:30"), "Bond": (1, "17:30")},
}


def _friday_before(d: date) -> date:
    """Premier vendredi strictement avant `d` (jour calendaire, sans lien
    avec business_days — vendredi est toujours un jour ouvré). Utilisé pour
    "NCO Estimate" (France / Bond) : "le vendredi avant à 11:30 (donc si
    jeudi 7, vendredi 1)" — toujours le vendredi de la semaine précédente,
    y compris si `d` est lui-même un vendredi."""
    cur = d - timedelta(days=1)
    while cur.weekday() != 4:
        cur -= timedelta(days=1)
    return cur


def _nco_historisation_rule(country: str, auction_type: Optional[str]) -> Optional[tuple[int, str]]:
    """Retourne (n, heure) — décalage en jours ouvrés (T+n) — pour la tâche
    "NCO Historisation" de ce pays/type, ou None si ce pays n'en génère pas
    (Allemagne, Cas 7 "autre pays"). Round 21 : la France, qui utilisait un
    décalage calendaire au round 20, a été alignée sur les autres pays (jour
    ouvré, table _NCO_HISTORISATION_BUSINESS_DAYS ci-dessus), confirmé par
    Augustin."""
    by_type = _NCO_HISTORISATION_BUSINESS_DAYS.get(country)
    if by_type is None:
        return None
    return by_type.get(auction_type)


def _expected_task_specs(auction: Auction) -> tuple[list[tuple[str, date, str]], list[str]]:
    """Calcule le mapping de tâches attendu (round 20, arbre de décision par
    pays × Bills/Bond fourni par Augustin) sans aucun effet de bord —
    retourne les (nom, date, heure) attendus pour cette adjudication, plus
    les avertissements associés (règles calées sur l'heure de l'adjudication,
    qui ne s'appliquent pas si elle est absente). Factorisé pour être
    partagé entre generate_tasks_for_auction (création initiale,
    inconditionnelle) et ensure_tasks_for_auction (réparation : ne crée que
    ce qui manque, round 14)."""
    specs: list[tuple[str, date, str]] = []
    warnings: list[str] = []

    a_date = task_service.parse_date(auction.date)
    has_time = bool(auction.time) and task_service.is_valid_time(auction.time)
    a_datetime = task_service.occurrence_datetime(a_date, auction.time) if has_time else None
    country = auction.country
    is_bills = auction.type == "Bills"
    is_bond = auction.type == "Bond"

    # Universel (tous pays, Bills et Bond) : 4h après l'adjudication ->
    # Bond Historisation.
    if a_datetime:
        dt = a_datetime + timedelta(hours=4)
        specs.append(("Bond Historisation", dt.date(), dt.strftime(TIME_FMT)))
    else:
        warnings.append(
            "Bond Historisation non générée : l'adjudication n'a pas d'heure renseignée."
        )

    # Tous pays, Bills uniquement : le jour même à 8:30 -> Pre-Bills Report.
    if is_bills:
        specs.append(("Pre-Bills Report", a_date, "08:30"))

    # France / Bond uniquement : NCO Estimate (vendredi précédent, 11:30) et
    # NCO Calculation (30 min après l'adjudication).
    if country == "France" and is_bond:
        specs.append(("NCO Estimate", _friday_before(a_date), "11:30"))
        if a_datetime:
            dtc = a_datetime + timedelta(minutes=30)
            specs.append(("NCO Calculation", dtc.date(), dtc.strftime(TIME_FMT)))
        else:
            warnings.append(
                "NCO Calculation non générée : l'adjudication n'a pas d'heure renseignée."
            )

    # Italie / Bond uniquement : Italian Fees, même décalage
    # que Bond Historisation (4h après l'adjudication).
    if country == "Italie" and is_bond:
        if a_datetime:
            dtf = a_datetime + timedelta(hours=4)
            specs.append(("Italian Fees", dtf.date(), dtf.strftime(TIME_FMT)))
        else:
            warnings.append(
                "Italian Fees non générée : l'adjudication n'a pas d'heure renseignée."
            )

    # NCO Historisation : dépend du pays (et, pour la Belgique, du type) —
    # absente pour l'Allemagne et tout pays hors de la table (Cas 7).
    nco_rule = _nco_historisation_rule(country, auction.type)
    if nco_rule is not None:
        n, when_time = nco_rule
        d = business_days.add_business_days(a_date, n)
        specs.append(("NCO Historisation", d, when_time))

    return specs, warnings


def generate_tasks_for_auction(auction: Auction) -> tuple[list[Task], list[str]]:
    """Applique le mapping de génération (round 20, par pays × type) et crée
    toutes les tâches correspondantes sans condition. Utilisé uniquement à
    la création d'une adjudication (add_auction) ou lors d'une régénération complète
    (update_auction(..., regenerate_tasks=True), qui supprime d'abord toutes
    les tâches liées existantes) : dans les deux cas, aucune tâche liée ne
    peut déjà exister au moment de l'appel. Pour réparer un lien sans tout
    recréer, voir ensure_tasks_for_auction ci-dessous."""
    specs, warnings = _expected_task_specs(auction)
    details = {"pays": auction.country, "type": auction.type}
    created = [
        task_service.add_task(
            name=name,
            time=when_time,
            recurrence=RECURRENCE_ONCE,
            recurrence_date=when.strftime(DATE_FMT),
            source="auto",
            auction_id=auction.id,
            details=dict(details),
        )
        for name, when, when_time in specs
    ]
    return created, warnings


def ensure_tasks_for_auction(auction: Auction) -> tuple[list[Task], list[str]]:
    """Vérifie que toutes les tâches attendues pour cette adjudication (mapping
    de génération round 20, par pays × type) sont bien présentes, et
    ne crée que celles qui manquent — contrairement à generate_tasks_for_auction
    (inconditionnel) ou à la régénération complète (update_auction(...,
    regenerate_tasks=True), qui supprime puis recrée tout). Une tâche liée
    déjà existante n'est jamais touchée : sa note, son statut fait/pas fait,
    ou une récurrence modifiée à la main restent intacts.

    "Existe déjà" est déterminé par le nom de la tâche parmi les tâches liées
    à cette adjudication (task_service.list_tasks_for_auction), pas par la
    date : si une tâche auto-générée a été repassée en récurrente (édition
    manuelle depuis TaskDetailModal), sa date d'origine (recurrence_date)
    devient None — comparer sur la date la ferait passer à tort pour absente
    et créerait un doublon. Comparer sur le nom seul suffit ici : les 5
    règles ne peuvent jamais produire deux fois le même nom pour une seule
    adjudication."""
    specs, warnings = _expected_task_specs(auction)
    existing_names = {t.name for t in task_service.list_tasks_for_auction(auction.id)}
    details = {"pays": auction.country, "type": auction.type}

    created: list[Task] = []
    for name, when, when_time in specs:
        if name in existing_names:
            continue
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
    return created, warnings


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def add_auction(
    country: str,
    date: str,
    time: Optional[str] = None,
    type: Optional[str] = None,
    maturity: Optional[str] = None,
    volume: Optional[float] = None,
    nco: Optional[bool] = None,
    note: Optional[str] = None,
) -> tuple[Auction, list[str]]:
    time = _clean_optional(time)
    type = _clean_optional(type)
    maturity = _clean_optional(maturity)
    volume = _clean_optional(volume)
    note = _clean_optional(note)

    _validate_fields(country, date, time, type, maturity, volume)

    auction = Auction(
        country=country,
        date=date,
        time=time,
        type=type,
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
        maturity = _clean_optional(fields.get("maturity", a.maturity))
        volume = _clean_optional(fields.get("volume", a.volume))
        nco = fields.get("nco", a.nco)
        note = _clean_optional(fields.get("note", a.note))

        _validate_fields(country, date, time, type, maturity, volume)

        a.country = country
        a.date = date
        a.time = time
        a.type = type
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
