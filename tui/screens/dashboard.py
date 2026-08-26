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


def build_task_row(index: int, occurrence) -> tuple[Text, ...]:
    # Couleur uniquement, sans gras : le statut (rouge/vert/blanc) doit rester
    # la seule source de mise en valeur, pas le poids de la police.
    style = STATUS_COLORS.get(occurrence.status, STATUS_COLORS[STATUS_NEUTRAL])
    details = " / ".join(str(v) for v in occurrence.details.values() if v) or "—"
    label = STATUS_LABELS.get(occurrence.status, occurrence.status)
    return (
        Text(str(index), style=style),
        Text(occurrence.time, style=style),
        Text(occurrence.name, style=style),
        Text(details, style=style),
        Text(label, style=style),
        Text(occurrence.note or "—", style=style),
    )
