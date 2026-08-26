"""
notifier.py — envoi de notifications système.

Priorité : toast natif Windows via `win11toast` (WinRT, Centre de notifications).
Si indisponible (import qui échoue, erreur au runtime, ou OS différent de
Windows), on retombe sur `plyer` (cross-platform), ce qui permet de développer
et tester le même code sur Linux/macOS. En tout dernier recours (aucune des
deux libs disponible), on affiche simplement la notification dans la console
pour ne jamais faire planter l'appelant.
"""

from __future__ import annotations

import sys

from constants import NOTIFY_APP_NAME


def send_notification(title: str, message: str) -> bool:
    """Tente d'envoyer une notification système. Retourne True si un des
    mécanismes a réussi, False si on est retombé sur l'affichage console."""
    if sys.platform == "win32":
        try:
            from win11toast import toast  # import paresseux : dépendance optionnelle

            toast(title, message, app_id=NOTIFY_APP_NAME)
            return True
        except Exception:
            pass  # on bascule sur le fallback ci-dessous

    try:
        from plyer import notification  # import paresseux : dépendance optionnelle

        notification.notify(
            title=title,
            message=message,
            app_name=NOTIFY_APP_NAME,
            timeout=10,
        )
        return True
    except Exception:
        pass

    print(f"[NOTIFICATION] {title} — {message}")
    return False
