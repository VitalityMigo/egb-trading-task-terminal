"""
tui/screens/auctions.py — construction des colonnes/lignes de la vue
Adjudications pour le DataTable de l'écran principal (voir la note
d'architecture dans tui/screens/dashboard.py).
"""

from __future__ import annotations

AUCTION_COLUMNS = (
    "N°", "Pays", "Date", "Heure", "Type", "Instrument", "Maturité", "Volume (M)", "NCO", "Note",
)

# Largeur de contenu (hors cell_padding) donnée à la colonne Note — voir la
# note équivalente dans tui/screens/dashboard.py (même logique, appliquée ici
# à la vue Adjudications).
NOTE_COLUMN_WIDTH = 22


def _truncate_note(note) -> str:
    text = note or "—"
    if len(text) <= NOTE_COLUMN_WIDTH:
        return text
    if NOTE_COLUMN_WIDTH <= 1:
        return text[:NOTE_COLUMN_WIDTH]
    return text[: NOTE_COLUMN_WIDTH - 1].rstrip() + "…"


def build_auction_row(index: int, auction) -> tuple[str, ...]:
    return (
        str(index),
        auction.country,
        auction.date,
        auction.time or "—",
        auction.type or "—",
        auction.instrument or "—",
        auction.maturity or "—",
        f"{auction.volume:g}" if auction.volume is not None else "—",
        "Oui" if auction.nco else ("Non" if auction.nco is not None else "—"),
        _truncate_note(auction.note),
    )
