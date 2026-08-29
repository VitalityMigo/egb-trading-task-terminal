"""
task_service.py — toute la logique métier des tâches : création, édition,
suppression (occurrence ou série), génération d'occurrences par période, et
calcul du statut de couleur (urgent / fait / neutre).

Aucune interface (CLI v1 ou TUI Textual) ne doit dupliquer une règle définie
ici — elles ne font qu'appeler ces fonctions et afficher le résultat.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from typing import Optional

from constants import (
    TASK_CATALOG,
    RECURRENCE_ONCE,
    RECURRENCE_BUSINESS_DAILY,
    RECURRENCE_DAILY,
    RECURRENCE_WEEKLY,
    RECURRENCE_TYPES,
    STATUS_URGENT,
    STATUS_DONE,
    STATUS_NEUTRAL,
    URGENCY_WINDOW_MINUTES,
    TASKS_FILE,
    WEEKDAY_LABELS,
)
from models import Task, Occurrence
from storage import load_json, save_json
import business_days

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"


class TaskServiceError(ValueError):
    """Erreur métier : donnée invalide, tâche introuvable, etc."""


# ---------------------------------------------------------------------------
# Aides de format / validation
# ---------------------------------------------------------------------------

def get_catalog() -> list[str]:
    return list(TASK_CATALOG)


def get_recurrence_types() -> list[str]:
    return list(RECURRENCE_TYPES)


def weekday_label(idx: int) -> str:
    return WEEKDAY_LABELS[idx]


def is_valid_time(value: str) -> bool:
    try:
        datetime.strptime(value, TIME_FMT)
        return True
    except (ValueError, TypeError):
        return False


def has_time(value: Optional[str]) -> bool:
    """Une tâche peut ne pas avoir d'heure (None ou "" — widget d'ajout,
    l'heure y est optionnelle). Même convention que Auction.time
    (auction_service.py, déjà optionnelle) : une valeur vide/absente est
    valide, simplement traitée comme "pas d'heure" plutôt que rejetée."""
    return bool(value) and is_valid_time(value)


def parse_time(value: str) -> dtime:
    if not is_valid_time(value):
        raise TaskServiceError(f"Heure invalide : {value!r} (attendu HH:MM)")
    return datetime.strptime(value, TIME_FMT).time()


def is_valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, DATE_FMT)
        return True
    except (ValueError, TypeError):
        return False


def parse_date(value: str) -> date:
    if not is_valid_date(value):
        raise TaskServiceError(f"Date invalide : {value!r} (attendu YYYY-MM-DD)")
    return datetime.strptime(value, DATE_FMT).date()


def occurrence_datetime(occ_date: date, time_str: str) -> datetime:
    return datetime.combine(occ_date, parse_time(time_str))


def compute_status(
    dt: datetime, done: bool, now: Optional[datetime] = None, has_time: bool = True
) -> str:
    """Règle de couleur (section 2.1 du blueprint) :
    - "done"    -> vert, si la tâche a été marquée faite (prioritaire sur tout).
    - "urgent"  -> rouge, dès que l'heure prévue est à <=30 min ou déjà passée,
                   et ce indéfiniment tant que la tâche n'est pas faite.
    - "neutral" -> sinon.

    has_time=False (tâche sans heure renseignée) désactive la règle "urgent" :
    sans heure prévue, il n'y a rien par rapport à quoi être en retard — la
    tâche reste "neutral" jusqu'à être marquée faite.
    """
    if done:
        return STATUS_DONE
    if not has_time:
        return STATUS_NEUTRAL
    now = now or datetime.now()
    if now >= dt - timedelta(minutes=URGENCY_WINDOW_MINUTES):
        return STATUS_URGENT
    return STATUS_NEUTRAL


def day_range(anchor: date) -> tuple[date, date]:
    """Une seule journée : (anchor, anchor) — utilisé par le navigateur
    jour/semaine global (bandeau supérieur), en mode "jour"."""
    return anchor, anchor


def week_range(anchor: date) -> tuple[date, date]:
    """Semaine calendaire (lundi -> dimanche) contenant `anchor` — utilisé
    par le navigateur jour/semaine global, en mode "semaine"."""
    monday = anchor - timedelta(days=anchor.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def nav_range(mode: str, anchor: date) -> tuple[date, date]:
    """Point d'entrée unique pour le navigateur global (tui/app.py) :
    "day" -> day_range(anchor), "week" -> week_range(anchor)."""
    if mode == "week":
        return week_range(anchor)
    if mode == "day":
        return day_range(anchor)
    raise TaskServiceError(f"Mode de navigation inconnu : {mode!r}")


# ---------------------------------------------------------------------------
# Persistance
# ---------------------------------------------------------------------------

def _load_tasks() -> list[Task]:
    raw = load_json(TASKS_FILE, [])
    return [Task.from_dict(d) for d in raw]


def _save_tasks(tasks: list[Task]) -> None:
    save_json(TASKS_FILE, [t.to_dict() for t in tasks])


def list_tasks() -> list[Task]:
    """Toutes les tâches brutes (pas des occurrences) — utile pour l'admin
    et pour auction_service (retrouver les tâches liées à une adjudication)."""
    return _load_tasks()


def get_task(task_id: str) -> Optional[Task]:
    for t in _load_tasks():
        if t.id == task_id:
            return t
    return None


def list_tasks_for_auction(auction_id: str) -> list[Task]:
    return [t for t in _load_tasks() if t.source == "auto" and t.auction_id == auction_id]


def delete_tasks_for_auction(auction_id: str) -> int:
    """Supprime toutes les tâches auto-générées liées à une adjudication
    (utilisé pour la cascade suppression / régénération)."""
    tasks = _load_tasks()
    remaining = [t for t in tasks if not (t.source == "auto" and t.auction_id == auction_id)]
    removed = len(tasks) - len(remaining)
    if removed:
        _save_tasks(remaining)
    return removed


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------

def _validate_recurrence(
    recurrence: str,
    recurrence_date: Optional[str],
    recurrence_weekday: Optional[int],
) -> None:
    if recurrence not in RECURRENCE_TYPES:
        raise TaskServiceError(f"Récurrence inconnue : {recurrence!r}")
    if recurrence == RECURRENCE_ONCE:
        if not recurrence_date or not is_valid_date(recurrence_date):
            raise TaskServiceError("Une tâche 'une fois' requiert une date valide (YYYY-MM-DD).")
    if recurrence == RECURRENCE_WEEKLY:
        if recurrence_weekday is None or not (0 <= int(recurrence_weekday) <= 6):
            raise TaskServiceError("Une tâche hebdomadaire requiert un jour de semaine (0=lundi..6=dimanche).")


def add_task(
    name: str,
    time: Optional[str],
    recurrence: str,
    recurrence_date: Optional[str] = None,
    recurrence_weekday: Optional[int] = None,
    source: str = "manual",
    auction_id: Optional[str] = None,
    details: Optional[dict] = None,
    created_date: Optional[str] = None,
    note: Optional[str] = None,
) -> Task:
    if name not in TASK_CATALOG:
        raise TaskServiceError(f"Nom de tâche hors catalogue : {name!r}")
    # L'heure est optionnelle (None/"" -> pas d'heure) : seule une valeur non
    # vide doit respecter le format HH:MM, même convention que Auction.time.
    time = time or None
    if time is not None and not is_valid_time(time):
        raise TaskServiceError(f"Heure invalide : {time!r} (attendu HH:MM)")
    _validate_recurrence(recurrence, recurrence_date, recurrence_weekday)

    task = Task(
        name=name,
        time=time,
        recurrence=recurrence,
        recurrence_date=recurrence_date,
        recurrence_weekday=recurrence_weekday,
        source=source,
        auction_id=auction_id,
        details=details or {},
        note=note or None,
    )
    if created_date:
        task.created_date = created_date

    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)
    return task


def update_task(task_id: str, **fields) -> Task:
    tasks = _load_tasks()
    for idx, t in enumerate(tasks):
        if t.id == task_id:
            name = fields.get("name", t.name)
            time_ = fields.get("time", t.time)
            time_ = time_ or None
            recurrence = fields.get("recurrence", t.recurrence)
            recurrence_date = fields.get("recurrence_date", t.recurrence_date)
            recurrence_weekday = fields.get("recurrence_weekday", t.recurrence_weekday)

            if name not in TASK_CATALOG:
                raise TaskServiceError(f"Nom de tâche hors catalogue : {name!r}")
            if time_ is not None and not is_valid_time(time_):
                raise TaskServiceError(f"Heure invalide : {time_!r} (attendu HH:MM)")
            _validate_recurrence(recurrence, recurrence_date, recurrence_weekday)

            t.name = name
            t.time = time_
            t.recurrence = recurrence
            t.recurrence_date = recurrence_date
            t.recurrence_weekday = recurrence_weekday
            if "details" in fields:
                t.details = fields["details"] or {}
            if "note" in fields:
                t.note = fields["note"] or None

            tasks[idx] = t
            _save_tasks(tasks)
            return t
    raise TaskServiceError(f"Tâche introuvable : {task_id!r}")


def mark_done(task_id: str, occurrence_date: date) -> Task:
    tasks = _load_tasks()
    for idx, t in enumerate(tasks):
        if t.id == task_id:
            ds = occurrence_date.strftime(DATE_FMT)
            if ds not in t.done_dates:
                t.done_dates.append(ds)
            tasks[idx] = t
            _save_tasks(tasks)
            return t
    raise TaskServiceError(f"Tâche introuvable : {task_id!r}")


def mark_undone(task_id: str, occurrence_date: date) -> Task:
    """Inverse de mark_done : retire occurrence_date de done_dates si elle y
    est (pas d'erreur si elle n'y était pas — idempotent, même logique de
    tolérance que mark_done)."""
    tasks = _load_tasks()
    for idx, t in enumerate(tasks):
        if t.id == task_id:
            ds = occurrence_date.strftime(DATE_FMT)
            if ds in t.done_dates:
                t.done_dates.remove(ds)
            tasks[idx] = t
            _save_tasks(tasks)
            return t
    raise TaskServiceError(f"Tâche introuvable : {task_id!r}")


def delete_task(task_id: str, scope: str = "series", occurrence_date: Optional[date] = None) -> bool:
    """scope="series"    -> supprime toute la tâche (toutes les occurrences).
    scope="occurrence" -> pour une tâche récurrente, exclut uniquement la
                           date donnée (la série continue d'exister)."""
    tasks = _load_tasks()
    for idx, t in enumerate(tasks):
        if t.id != task_id:
            continue
        if scope == "occurrence" and t.recurrence != RECURRENCE_ONCE:
            if occurrence_date is None:
                raise TaskServiceError("occurrence_date requis pour scope='occurrence'.")
            ds = occurrence_date.strftime(DATE_FMT)
            if ds not in t.excluded_dates:
                t.excluded_dates.append(ds)
            tasks[idx] = t
            _save_tasks(tasks)
            return True
        # scope="series", ou tâche "once" (une occurrence = toute la série)
        del tasks[idx]
        _save_tasks(tasks)
        return True
    return False


# ---------------------------------------------------------------------------
# Génération d'occurrences pour une période
# ---------------------------------------------------------------------------

def _dates_in_range(
    task: Task, start: date, end: date
) -> list[date]:
    # Une tâche "once" ne dépend jamais de created_date (elle a sa propre
    # date explicite) : ce cas doit être tranché avant tout calcul de plancher,
    # sinon une tâche créée aujourd'hui pour une date hors de la plage
    # [start, end] par rapport à created_date pouvait disparaître à tort.
    if task.recurrence == RECURRENCE_ONCE:
        d = parse_date(task.recurrence_date)
        return [d] if start <= d <= end else []

    created = parse_date(task.created_date) if task.created_date else start
    lower = max(start, created)
    if lower > end:
        return []

    dates: list[date] = []
    cur = lower
    while cur <= end:
        if task.recurrence == RECURRENCE_DAILY:
            dates.append(cur)
        elif task.recurrence == RECURRENCE_BUSINESS_DAILY:
            if business_days.is_business_day(cur):
                dates.append(cur)
        elif task.recurrence == RECURRENCE_WEEKLY:
            if cur.weekday() == task.recurrence_weekday:
                dates.append(cur)
        cur += timedelta(days=1)
    return dates


def get_occurrences(
    start: date, end: date, now: Optional[datetime] = None
) -> list[Occurrence]:
    """Toutes les occurrences de tâches dont la date tombe dans [start, end],
    triées par date+heure. Le statut (urgent/fait/neutre) est recalculé à
    chaque appel à partir de l'heure actuelle : rien n'est mis en cache, donc
    rouvrir l'app après une longue absence donne toujours un état à jour."""
    now = now or datetime.now()
    tasks = _load_tasks()
    occurrences: list[Occurrence] = []

    for t in tasks:
        excluded = set(t.excluded_dates)
        done = set(t.done_dates)
        for d in _dates_in_range(t, start, end):
            ds = d.strftime(DATE_FMT)
            if ds in excluded:
                continue
            t_has_time = has_time(t.time)
            # Sans heure : dt porte une heure factice (minuit), jamais utilisée
            # pour trier ni pour l'urgence (voir tri et compute_status
            # ci-dessous) — seulement là où le type datetime est requis pour
            # des besoins insensibles à l'heure (ex. TaskDetailModal, .weekday()).
            dt = occurrence_datetime(d, t.time) if t_has_time else datetime.combine(d, dtime.min)
            occurrences.append(
                Occurrence(
                    task_id=t.id,
                    name=t.name,
                    date=ds,
                    time=t.time,
                    has_time=t_has_time,
                    dt=dt,
                    status=compute_status(dt, ds in done, now, has_time=t_has_time),
                    is_recurring=t.recurrence != RECURRENCE_ONCE,
                    source=t.source,
                    details=dict(t.details),
                    auction_id=t.auction_id,
                    note=t.note,
                )
            )

    # Tri par date, puis par heure au sein d'une même journée — les
    # occurrences sans heure passent en dernier ce jour-là (flag has_time
    # d'abord, "" trie de toute façon après toute heure "HH:MM" valide au
    # besoin) plutôt que par o.dt (qui porterait sinon la fausse heure minuit
    # et les ferait remonter en tête, à l'opposé de ce qui est demandé).
    occurrences.sort(key=lambda o: (o.date, 0 if o.has_time else 1, o.time or ""))
    return occurrences


def count_by_status(occurrences: list[Occurrence]) -> dict[str, int]:
    counts = {STATUS_URGENT: 0, STATUS_DONE: 0, STATUS_NEUTRAL: 0}
    for o in occurrences:
        counts[o.status] += 1
    return counts
