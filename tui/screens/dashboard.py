"""
tui/screens/dashboard.py — construction des colonnes/lignes de la vue Tâches
pour le DataTable de l'écran principal.

Note d'architecture : plutôt que deux `Screen` Textual séparés qu'on empile
(ce qui masquerait le bandeau/la sidebar/la barre de commande à chaque
bascule), l'app garde un unique écran persistant (tui/app.py) et bascule
seulement le contenu du DataTable. Ce module ne fournit que la mise en forme
propre à la vue Tâches — la donnée et le statut viennent entièrement de
task_service, rien n'est recalculé ici.
"""

from __future__ import annotations

from rich.text import Text

from constants import STATUS_DONE, STATUS_NEUTRAL, STATUS_URGENT

TASK_COLUMNS = ("N°", "Heure", "Tâche", "Détails", "Statut", "Note")

# Largeur de contenu (hors cell_padding) donnée à la colonne Note dans
# tui/app.py (add_column("Note", width=NOTE_COLUMN_WIDTH)) — toutes les
# autres colonnes s'auto-dimensionnent sur leur contenu (donc "Tâche" ne
# risque plus d'être poussée hors de l'écran par une note longue). On
# tronque nous-mêmes le texte de la note avec une ellipse pour tenir dans
# cette largeur : le détail complet reste de toute façon visible/éditable
# dans la modale ouverte au clic sur la ligne (tui/screens/confirm.py).
NOTE_COLUMN_WIDTH = 22

# Doit rester synchronisé avec les couleurs de tui/theme.tcss.
STATUS_COLORS = {
    STATUS_URGENT: "#FF3B3B",
    STATUS_DONE: "#00D26A",
    STATUS_NEUTRAL: "#E8E8E8",
}

STATUS_LABELS = {
    STATUS_URGENT: "● URGENT",
    STATUS_DONE: "● Fait",
    STATUS_NEUTRAL: "○ Prévu",
}


def format_details(occurrence) -> str:
    return " / ".join(str(v) for v in occurrence.details.values() if v) or "—"


def truncate_note(note: str | None, width: int = NOTE_COLUMN_WIDTH) -> str:
    text = note or "—"
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1].rstrip() + "…"


def build_task_row(index: int, occurrence) -> tuple[Text, ...]:
    # Couleur uniquement, sans gras : le statut (rouge/vert/blanc) doit rester
    # la seule source de mise en valeur, pas le poids de la police.
    style = STATUS_COLORS.get(occurrence.status, STATUS_COLORS[STATUS_NEUTRAL])
    label = STATUS_LABELS.get(occurrence.status, occurrence.status)
    return (
        Text(str(index), style=style),
        Text(occurrence.time, style=style),
        Text(occurrence.name, style=style),
        Text(format_details(occurrence), style=style),
        Text(label, style=style),
        Text(truncate_note(occurrence.note), style=style),
    )
