"""
tui/screens/auctions.py — construction des colonnes/lignes de la vue
Adjudications pour le DataTable de l'écran principal (voir la note
d'architecture dans tui/screens/dashboard.py).

Colonnes et largeurs alignées sur la même logique que la vue Tâches
(dashboard.py) — round 12 :
- "Date" retirée (portée par le navigateur jour/semaine du bandeau, donc déjà
  connue) et "Instrument" retirée (peu utilisée) ; "Heure" placée en 2e
  position, juste après "N°" — même ordre que la vue Tâches (N°, Heure, ...).
- Plus aucune colonne en auto-dimensionnement Textual (`width=None`) : toutes
  calculées explicitement, comme pour TASK_COLUMN_WIDTHS dans dashboard.py et
  pour la même raison (voir le commentaire détaillé là-bas — bug de colonnes
  déformées après un aller-retour Semaine + case "Tout", jamais reproduit
  avec certitude mais éliminé par construction en supprimant le mécanisme
  d'auto-dimensionnement). "N°" et "Heure" sont d'ailleurs les mêmes
  constantes que côté Tâches (importées, pas redéfinies).
"""

from __future__ import annotations

from constants import AUCTION_TYPES, COUNTRIES
from tui.screens.dashboard import N_COLUMN_WIDTH, TIME_COLUMN_WIDTH

AUCTION_COLUMNS = ("N°", "Heure", "Pays", "Type", "Maturité", "Volume (M)", "NCO", "Note")

# Largeur de contenu (hors cell_padding) donnée à la colonne Note — voir la
# note équivalente dans tui/screens/dashboard.py (même logique, appliquée ici
# à la vue Adjudications).
NOTE_COLUMN_WIDTH = 40

# Comme côté Tâches : catalogues fermés (COUNTRIES, AUCTION_TYPES) -> largeur
# calculée une fois pour toutes à partir du plus long élément possible, plutôt
# que laissée à l'auto-dimensionnement Textual.
PAYS_COLUMN_WIDTH = max(len(c) for c in COUNTRIES)
TYPE_COLUMN_WIDTH = max(len(t) for t in AUCTION_TYPES)
# "YYYY-MM-DD" : format fixe, toujours 10 caractères quand renseigné.
MATURITE_COLUMN_WIDTH = 10
# Pas de catalogue fermé pour un volume (nombre libre) : largeur choisie assez
# large pour les ordres de grandeur usuels d'un desk, avec une troncature de
# sécurité (voir _crop ci-dessous) pour ne jamais dépasser la largeur fixée.
VOLUME_COLUMN_WIDTH = 10
# "Oui" / "Non" / "—"
NCO_COLUMN_WIDTH = 3

AUCTION_COLUMN_WIDTHS = {
    "N°": N_COLUMN_WIDTH,
    "Heure": TIME_COLUMN_WIDTH,
    "Pays": PAYS_COLUMN_WIDTH,
    "Type": TYPE_COLUMN_WIDTH,
    "Maturité": MATURITE_COLUMN_WIDTH,
    "Volume (M)": VOLUME_COLUMN_WIDTH,
    "NCO": NCO_COLUMN_WIDTH,
    "Note": NOTE_COLUMN_WIDTH,
}


def _crop(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1].rstrip() + "…"


def _truncate_note(note) -> str:
    return _crop(note or "—", NOTE_COLUMN_WIDTH)


def build_auction_row(index: int, auction) -> tuple[str, ...]:
    volume = f"{auction.volume:g}" if auction.volume is not None else "—"
    return (
        str(index),
        # "-" et non "—" : même convention que la colonne Heure de la vue
        # Tâches (occurrence sans heure, round 12) — c'est le même champ,
        # affiché au même endroit.
        auction.time or "-",
        auction.country,
        auction.type or "—",
        auction.maturity or "—",
        _crop(volume, VOLUME_COLUMN_WIDTH),
        "Oui" if auction.nco else ("Non" if auction.nco is not None else "—"),
        _truncate_note(auction.note),
    )
