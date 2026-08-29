"""
tui/screens/log.py — construction des colonnes/lignes de la vue "Log"
(round 22) pour le DataTable de l'écran principal — même architecture que
tui/screens/dashboard.py (vue Tâches) et tui/screens/auctions.py (vue
Adjudications) : ce module ne fait que formater, la donnée vient entièrement
de notification_service.get_today_log(), déjà filtrée sur la journée en
cours et triée du plus récent au plus ancien.
"""

from __future__ import annotations

from rich.text import Text

from constants import NOTIFY_APP_NAME, TASK_CATALOG
from notification_service import KIND_GENERAL, KIND_TEST, KIND_URGENT
from tui.screens.dashboard import N_COLUMN_WIDTH

LOG_COLUMNS = ("N°", "Heure", "Type", "Titre", "Message")

# "HH:MM:SS" — contrairement aux vues Tâches/Adjudications (qui n'ont besoin
# que de "HH:MM", l'heure prévue), le Log montre l'instant réel d'envoi ;
# les secondes aident à distinguer deux notifications proches (rare, mais
# possible si plusieurs tâches urgentes passent au même contrôle).
TIME_COLUMN_WIDTH = 8

KIND_LABELS = {
    KIND_URGENT: "Urgent",
    KIND_GENERAL: "Général",
    KIND_TEST: "Test",
}
TYPE_COLUMN_WIDTH = max(len(label) for label in KIND_LABELS.values())

# Même logique que TASK_NAME_COLUMN_WIDTH (dashboard.py) : catalogue fermé
# de noms de tâche -> largeur calculée une fois pour toutes plutôt que laissée
# à l'auto-dimensionnement Textual. Le titre d'une notif par tâche est
# toujours "<NOTIFY_APP_NAME> — <nom de tâche>" ; les titres génériques
# ("Récapitulatif", "Test") sont toujours plus courts.
_PREFIX = f"{NOTIFY_APP_NAME} — "
TITLE_COLUMN_WIDTH = len(_PREFIX) + max(len(n) for n in TASK_CATALOG)

MESSAGE_COLUMN_WIDTH = 46

LOG_COLUMN_WIDTHS = {
    "N°": N_COLUMN_WIDTH,
    "Heure": TIME_COLUMN_WIDTH,
    "Type": TYPE_COLUMN_WIDTH,
    "Titre": TITLE_COLUMN_WIDTH,
    "Message": MESSAGE_COLUMN_WIDTH,
}

# Doit rester cohérent avec les couleurs de statut (dashboard.py / theme.tcss) :
# urgent en rouge (même sémantique que STATUS_URGENT), général en cyan
# (couleur d'en-tête, neutre), test en gris atténué (jamais une vraie alerte).
KIND_COLORS = {
    KIND_URGENT: "#FF3B3B",
    KIND_GENERAL: "#00C8FF",
    KIND_TEST: "#5C5C5C",
}


def _crop(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1].rstrip() + "…"


def build_log_row(index: int, entry: dict) -> tuple[Text, ...]:
    kind = entry.get("kind", "")
    style = KIND_COLORS.get(kind, KIND_COLORS[KIND_GENERAL])
    label = KIND_LABELS.get(kind, kind or "—")
    sent_at = entry.get("sent_at", "")
    time_part = sent_at.split(" ")[1] if " " in sent_at else sent_at
    return (
        Text(str(index), style=style),
        Text(time_part or "-", style=style),
        Text(label, style=style),
        Text(_crop(entry.get("title", ""), TITLE_COLUMN_WIDTH), style=style),
        Text(_crop(entry.get("message", ""), MESSAGE_COLUMN_WIDTH), style=style),
    )
