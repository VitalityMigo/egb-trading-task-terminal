"""
notify_daemon.py — process séparé qui surveille les tâches et déclenche une
notification système dès qu'une tâche entre en zone d'urgence (30 min avant
l'heure prévue, non faite). À lancer indépendamment du CLI/TUI (voir
start_notify_daemon.bat) : un crash de l'interface n'affecte pas les
notifications, et inversement.

Déduplication : chaque (tâche, date d'occurrence) n'est notifiée qu'une seule
fois par jour, persistée dans data/notified.json et réinitialisée
automatiquement au changement de jour.

Arrêt : Ctrl+C dans la fenêtre où tourne ce script.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import task_service
from constants import NOTIFIED_FILE, NOTIFY_CHECK_INTERVAL_SECONDS, STATUS_URGENT
from notifier import send_notification
from storage import load_json, save_json


def _load_state() -> dict:
    return load_json(NOTIFIED_FILE, {"date": "", "notified": []})


def _save_state(state: dict) -> None:
    save_json(NOTIFIED_FILE, state)


def _reset_if_new_day(state: dict, today: date) -> dict:
    today_str = today.isoformat()
    if state.get("date") != today_str:
        return {"date": today_str, "notified": []}
    return state


def _format_message(occ) -> str:
    parts = []
    if occ.details.get("pays"):
        parts.append(occ.details["pays"])
    if occ.details.get("type"):
        parts.append(occ.details["type"])
    suffix = f" ({' / '.join(parts)})" if parts else ""
    return f"Prévue à {occ.time}{suffix}"


def check_once(state: dict, now: datetime) -> dict:
    """Exécute une passe de vérification et retourne l'état (potentiellement
    mis à jour) de déduplication. Séparée de la boucle pour être testable."""
    today = now.date()
    state = _reset_if_new_day(state, today)
    notified = set(state["notified"])

    occurrences = task_service.get_occurrences(today, today, now=now)
    changed = False
    for occ in occurrences:
        if occ.status != STATUS_URGENT:
            continue
        key = f"{occ.task_id}|{occ.date}"
        if key in notified:
            continue
        send_notification(f"Desk CLI — {occ.name}", _format_message(occ))
        notified.add(key)
        changed = True

    state["notified"] = sorted(notified)
    if changed:
        _save_state(state)
    return state


def run_forever() -> None:
    print("notify_daemon — surveillance des tâches urgentes (Ctrl+C pour arrêter)")
    state = _load_state()
    try:
        while True:
            state = check_once(state, datetime.now())
            time.sleep(NOTIFY_CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("notify_daemon — arrêt demandé, à bientôt.")


if __name__ == "__main__":
    run_forever()
