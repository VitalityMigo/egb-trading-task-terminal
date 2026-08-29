"""
notification_service.py — toute la logique métier des notifications :
détection des tâches qui entrent en zone d'urgence, notifications générales
récapitulatives (matin/après-midi), déduplication (une fois par jour) et
journal des notifications réellement envoyées (page "Log" de la TUI).

Round 22 : remplace notify_daemon.py (process séparé, retiré). Le suivi
tourne désormais dans la boucle d'événements de la TUI (tui/app.py,
set_interval) — même principe de séparation métier/interface que
task_service.py / auction_service.py : tui/ n'appelle que les fonctions
ci-dessous, aucune règle n'est dupliquée côté interface.

Deux mécanismes de persistance distincts, volontairement séparés :
- NOTIFIED_FILE (data/notified.json) : déduplication pure, ne garde qu'un
  ensemble de clés "déjà notifié aujourd'hui", réinitialisé chaque jour.
- NOTIFICATIONS_LOG_FILE (data/notifications_log.json) : historique des
  notifications réellement envoyées (titre, message, horodatage, type), non
  réinitialisé — la page "Log" de la TUI filtre à l'affichage sur la journée
  en cours (voir get_today_log), le fichier lui-même garde une petite fenêtre
  glissante (_prune_log) pour ne pas grossir indéfiniment.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime, timedelta
from typing import Callable, Optional

import task_service
from constants import (
    GENERAL_NOTIFICATION_TIMES,
    NOTIFIED_FILE,
    NOTIFICATIONS_LOG_FILE,
    NOTIFY_APP_NAME,
    STATUS_DONE,
    STATUS_URGENT,
)
from models import new_id
from notifier import send_notification
from storage import load_json, save_json

KIND_URGENT = "urgent"
KIND_GENERAL = "general"
KIND_TEST = "test"

# Fenêtre de conservation du journal (data/notifications_log.json) — la page
# "Log" n'affiche que la journée en cours, donc pas besoin de garder plus ;
# quelques jours de marge en cas de besoin ponctuel de retrouver une
# notification récente.
LOG_RETENTION_DAYS = 7

DATE_FMT = "%Y-%m-%d"
SendFn = Callable[[str, str], bool]


# ---------------------------------------------------------------------------
# Déduplication (data/notified.json) — même fichier/format qu'avant round 22
# ---------------------------------------------------------------------------

def _load_dedup_state() -> dict:
    return load_json(NOTIFIED_FILE, {"date": "", "notified": []})


def _save_dedup_state(state: dict) -> None:
    save_json(NOTIFIED_FILE, state)


def _reset_if_new_day(state: dict, today: date) -> dict:
    today_str = today.strftime(DATE_FMT)
    if state.get("date") != today_str:
        return {"date": today_str, "notified": []}
    return state


def _task_key(occ) -> str:
    return f"{occ.task_id}|{occ.date}"


def _general_notification_key(time_label: str, today: date) -> str:
    # Préfixe distinct des clés de tâche (f"{task_id}|{date}", task_id étant
    # un hex uuid[:12]) : aucune collision possible.
    return f"GENERAL-{time_label.replace(':', '')}|{today.strftime(DATE_FMT)}"


# ---------------------------------------------------------------------------
# Journal des notifications envoyées (data/notifications_log.json)
# ---------------------------------------------------------------------------

def _load_log() -> list[dict]:
    return load_json(NOTIFICATIONS_LOG_FILE, [])


def _prune_log(entries: list[dict], today: date) -> list[dict]:
    floor = today - timedelta(days=LOG_RETENTION_DAYS)
    kept = []
    for e in entries:
        try:
            d = datetime.strptime(e["date"], DATE_FMT).date()
        except (KeyError, ValueError, TypeError):
            continue  # entrée corrompue : on l'élimine plutôt que de planter
        if d >= floor:
            kept.append(e)
    return kept


def _append_log_entry(kind: str, title: str, message: str, now: datetime) -> None:
    entries = _load_log()
    entries.append(
        {
            "id": new_id(),
            "kind": kind,
            "title": title,
            "message": message,
            "date": now.strftime(DATE_FMT),
            "sent_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    entries = _prune_log(entries, now.date())
    save_json(NOTIFICATIONS_LOG_FILE, entries)


def get_today_log(now: Optional[datetime] = None) -> list[dict]:
    """Notifications envoyées aujourd'hui, les plus récentes en premier —
    alimente la page "Log" de la TUI (tui/screens/log.py)."""
    now = now or datetime.now()
    today_str = now.strftime(DATE_FMT)
    entries = [e for e in _load_log() if e.get("date") == today_str]
    entries.sort(key=lambda e: e.get("sent_at", ""), reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Message des notifications par tâche (repris de l'ancien notify_daemon.py)
# ---------------------------------------------------------------------------

def _format_task_message(occ) -> str:
    parts = []
    if occ.details.get("pays"):
        parts.append(occ.details["pays"])
    if occ.details.get("type"):
        parts.append(occ.details["type"])
    suffix = f" ({' / '.join(parts)})" if parts else ""
    return f"Prévue à {occ.time}{suffix}"


# ---------------------------------------------------------------------------
# Vérification périodique — cœur testable, appelé par tui/app.py
# ---------------------------------------------------------------------------

def check_once(state: dict, now: datetime, send: SendFn = send_notification) -> dict:
    """Exécute une passe de vérification : notifications par tâche (urgentes,
    30 min avant l'heure prévue) + notifications générales (récapitulatif des
    tâches non faites, à heure fixe — constants.GENERAL_NOTIFICATION_TIMES).
    Retourne l'état de déduplication (potentiellement mis à jour). Chaque
    notification réellement envoyée est aussi journalisée (_append_log_entry)
    pour la page "Log". Séparée de l'appel périodique pour être testable —
    `send` est injectable (tests), par défaut notifier.send_notification."""
    today = now.date()
    state = _reset_if_new_day(state, today)
    notified = set(state["notified"])
    changed = False

    occurrences = task_service.get_occurrences(today, today, now=now)
    for occ in occurrences:
        if occ.status != STATUS_URGENT:
            continue
        key = _task_key(occ)
        if key in notified:
            continue
        title = f"{NOTIFY_APP_NAME} — {occ.name}"
        message = _format_task_message(occ)
        send(title, message)
        _append_log_entry(KIND_URGENT, title, message, now)
        notified.add(key)
        changed = True

    for time_label in GENERAL_NOTIFICATION_TIMES:
        key = _general_notification_key(time_label, today)
        if key in notified:
            continue
        target = datetime.combine(today, datetime.strptime(time_label, "%H:%M").time())
        if now < target:
            continue
        remaining = _remaining_today_count(today, now)
        title = f"{NOTIFY_APP_NAME} — Récapitulatif"
        if remaining == 0:
            message = "Aucune tâche restante aujourd'hui."
        elif remaining == 1:
            message = "1 tâche restante aujourd'hui."
        else:
            message = f"{remaining} tâches restantes aujourd'hui."
        send(title, message)
        _append_log_entry(KIND_GENERAL, title, message, now)
        notified.add(key)
        changed = True

    state["notified"] = sorted(notified)
    if changed:
        _save_dedup_state(state)
    return state


def _remaining_today_count(today: date, now: datetime) -> int:
    """Nombre de tâches du jour pas encore faites (urgentes incluses) — même
    définition que le compteur "à faire" du bandeau (tui/app.py,
    _refresh_header_counts)."""
    counts = task_service.count_by_status(
        task_service.get_occurrences(today, today, now=now)
    )
    return sum(counts.values()) - counts[STATUS_DONE]


def run_check(now: Optional[datetime] = None, send: SendFn = send_notification) -> None:
    """Point d'entrée appelé par la TUI (timer + vérification immédiate au
    lancement) : charge l'état de dédup, exécute une passe, sauvegarde."""
    now = now or datetime.now()
    state = _load_dedup_state()
    check_once(state, now, send=send)


# ---------------------------------------------------------------------------
# Notification de test (round 22, commande "NOTIF TEST")
# ---------------------------------------------------------------------------

def send_test_notification(now: Optional[datetime] = None, send: SendFn = send_notification) -> bool:
    """Envoie une notification de test immédiate, hors déduplication —
    utilisée par la commande NOTIF TEST (tui/app.py) pour vérifier que les
    notifications système fonctionnent bien sur le poste. Journalisée comme
    les autres (kind="test") pour apparaître dans la page Log."""
    now = now or datetime.now()
    title = f"{NOTIFY_APP_NAME} — Test"
    message = f"Notification de test envoyée à {now.strftime('%H:%M:%S')}."
    ok = send(title, message)
    _append_log_entry(KIND_TEST, title, message, now)
    return ok
