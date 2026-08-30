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

from constants import COUNTRY_CODES, STATUS_DONE, STATUS_NEUTRAL, STATUS_URGENT, TASK_CATALOG

TASK_COLUMNS = ("N°", "Date", "Heure", "Tâche", "Détails", "Statut", "Note")

# Largeur de contenu (hors cell_padding) donnée à la colonne Note dans
# tui/app.py (add_column("Note", width=NOTE_COLUMN_WIDTH)). On tronque
# nous-mêmes le texte de la note avec une ellipse pour tenir dans cette
# largeur : le détail complet reste de toute façon visible/éditable dans la
# modale ouverte au clic sur la ligne (tui/screens/confirm.py). Volontairement
# assez large (une note tient presque toujours en entier) — seules les notes
# vraiment longues sont coupées.
NOTE_COLUMN_WIDTH = 40

# Largeurs fixes pour toutes les colonnes de la vue Tâches. Toutes calculées
# explicitement (aucune colonne laissée en auto-dimensionnement Textual,
# width=None) : "N°" (index, quelques chiffres), "Heure" (format "HH:MM"
# fixe, toujours 5 caractères), "Détails" (pour les tâches issues d'une
# adjudication : "<pays> / <Bills|Bonds>" — le pire cas est "Allemagne /
# Bills" à 17 caractères, donc 18 suffit large).
#
# "Tâche" et "Statut" étaient auto-dimensionnées jusqu'ici (Textual recalcule
# leur largeur en fonction des lignes affichées à chaque add_row). Bug trouvé
# lors du signalement d'Augustin (colonnes déformées après un aller-retour
# Semaine + case "Tout") : impossible à reproduire de façon fiable en tests
# headless malgré plusieurs tentatives (cycles de bascule répétés, clics
# simulés, jeux de données variés — jamais de déformation constatée dans le
# sandbox), donc cause exacte non confirmée avec certitude. Mais les deux
# colonnes se prêtaient de toute façon à un calcul déterministe, ce qui
# élimine complètement le mécanisme d'auto-dimensionnement incrémental de
# Textual (le suspect le plus probable, puisque les 4 autres colonnes déjà en
# largeur fixe n'ont jamais été concernées par ce bug) plutôt que de
# dépendre d'un état recalculé à chaque clear()+repopulate :
#   - "Tâche" : les noms de tâches viennent d'un catalogue fixe fermé
#     (TASK_CATALOG, aucune saisie libre) — la largeur nécessaire est donc
#     connue à l'avance, une fois pour toutes, indépendamment des lignes
#     réellement affichées à un instant donné.
#   - "Statut" : seuls 3 libellés possibles (STATUS_LABELS), eux aussi fixes.
TASK_NAME_COLUMN_WIDTH = max(len(n) for n in TASK_CATALOG)
N_COLUMN_WIDTH = 1
TIME_COLUMN_WIDTH = 5
DETAILS_COLUMN_WIDTH = 12
# Round 23 : colonne "Date" ajoutée juste après "N°", pour se repérer plus
# facilement en mode Semaine ou "Tout" (plusieurs jours affichés à la fois,
# demande d'Augustin). Format "JJ/MM" sans année — même convention compacte
# que le reste de l'app (auction_service.format_auction_short_label,
# header_bar.py) : le bandeau donne déjà l'année/le contexte, pas la peine de
# la répéter sur chaque ligne. Toujours 5 caractères, comme "Heure" (HH:MM).
DATE_COLUMN_WIDTH = 5

# Espace supplémentaire (au-delà du cell_padding) ajouté explicitement après
# "Tâche" : c'est la colonne la plus lue d'un coup d'œil, elle gagne à
# respirer un peu plus que le reste (contrairement à "Détails", qui elle
# est resserrée à une largeur fixe).
_EXTRA_GAP = " "

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

STATUS_COLUMN_WIDTH = max(len(label) for label in STATUS_LABELS.values())

TASK_COLUMN_WIDTHS = {
    "N°": N_COLUMN_WIDTH,
    "Date": DATE_COLUMN_WIDTH,
    "Heure": TIME_COLUMN_WIDTH,
    "Tâche": TASK_NAME_COLUMN_WIDTH + len(_EXTRA_GAP),
    "Détails": DETAILS_COLUMN_WIDTH,
    "Statut": STATUS_COLUMN_WIDTH,
    "Note": NOTE_COLUMN_WIDTH,
}


def format_date_short(date_str: str) -> str:
    """"YYYY-MM-DD" -> "JJ/MM" (sans année) — voir DATE_COLUMN_WIDTH. Repli
    "-" si la date est absente/mal formée plutôt qu'un crash d'affichage."""
    if not date_str or len(date_str) < 10:
        return "-"
    return f"{date_str[8:10]}/{date_str[5:7]}"


def format_details(occurrence, use_country_code: bool = False) -> str:
    """use_country_code=True remplace le pays ("Belgique") par son code
    ("BE") — utilisé uniquement pour la colonne "Détails" du tableau
    (build_task_row ci-dessous, plus compact) ; la modale de détail d'une
    tâche (tui/screens/confirm.py) garde le nom complet par défaut."""
    parts = []
    for key, value in occurrence.details.items():
        if not value:
            continue
        if use_country_code and key == "pays":
            value = COUNTRY_CODES.get(value, value)
        parts.append(str(value))
    return " / ".join(parts) or "—"


def _crop(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1].rstrip() + "…"


def truncate_note(note: str | None, width: int = NOTE_COLUMN_WIDTH) -> str:
    return _crop(note or "—", width)


def build_task_row(index: int, occurrence) -> tuple[Text, ...]:
    # Couleur uniquement, sans gras : le statut (rouge/vert/blanc) doit rester
    # la seule source de mise en valeur, pas le poids de la police.
    style = STATUS_COLORS.get(occurrence.status, STATUS_COLORS[STATUS_NEUTRAL])
    label = STATUS_LABELS.get(occurrence.status, occurrence.status)
    details_text = _crop(format_details(occurrence, use_country_code=True), DETAILS_COLUMN_WIDTH)
    return (
        Text(str(index), style=style),
        Text(format_date_short(occurrence.date), style=style),
        Text(occurrence.time or "-", style=style),
        Text(occurrence.name + _EXTRA_GAP, style=style),
        Text(details_text, style=style),
        Text(label, style=style),
        Text(truncate_note(occurrence.note), style=style),
    )
