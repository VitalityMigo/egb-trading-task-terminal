"""
tui/screens/auctions.py — construction des colonnes/lignes de la vue
Adjudications pour le DataTable de l'écran principal (voir la note
d'architecture dans tui/screens/dashboard.py).
"""

from __future__ import annotations

AUCTION_COLUMNS = (
    "N°", "Pays", "Date", "Heure", "Type", "Instrument", "Maturité", "Volume (M)", "NCO", "Note",
)


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
        auction.note or "—",
    )
