"""
constants.py — valeurs fixes partagées par tout le projet (backend, CLI v1, TUI Textual).

Rien ici ne dépend d'une interface particulière : c'est la source unique de vérité
pour le catalogue de tâches, les pays, les types de récurrence et les paramètres
de la règle de couleur d'urgence.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Catalogue fixe des noms de tâches (pas de saisie libre autorisée)
# ---------------------------------------------------------------------------
TASK_CATALOG: list[str] = [
    "Bond Definition",
    "Bond Historisation",
    "Inflation Historisation",
    "NCO Estimate",
    "NCO Historisation",
    "Risk 16h30",
    "Risk 17h30",
    "Swap File",
    "PnL Report",
    "Volume HREF",
    "MTS Quotation",
    "Italian Fees",
    "Pre-Auction Bills Report",
    "SSA Chain Report",
    "Weekly Macro Recap",
]

# ---------------------------------------------------------------------------
# Adjudications
# ---------------------------------------------------------------------------
COUNTRIES: list[str] = ["France", "Belgique", "Allemagne", "Italie", "Espagne"]
AUCTION_TYPES: list[str] = ["Bills", "Bond"]

# ---------------------------------------------------------------------------
# Récurrence des tâches
# ---------------------------------------------------------------------------
RECURRENCE_ONCE = "once"                # une fois, à une date précise
RECURRENCE_BUSINESS_DAILY = "business_daily"  # tous les jours ouvrés
RECURRENCE_DAILY = "daily"              # tous les jours (7j/7)
RECURRENCE_WEEKLY = "weekly"            # chaque semaine, jour fixe

RECURRENCE_TYPES: list[str] = [
    RECURRENCE_ONCE,
    RECURRENCE_BUSINESS_DAILY,
    RECURRENCE_DAILY,
    RECURRENCE_WEEKLY,
]

RECURRENCE_LABELS: dict[str, str] = {
    RECURRENCE_ONCE: "Une fois",
    RECURRENCE_BUSINESS_DAILY: "Tous les jours ouvrés",
    RECURRENCE_DAILY: "Tous les jours (7j/7)",
    RECURRENCE_WEEKLY: "Chaque semaine",
}

WEEKDAY_LABELS: list[str] = [
    "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche",
]

# ---------------------------------------------------------------------------
# Statuts d'occurrence (couleur)
# ---------------------------------------------------------------------------
STATUS_URGENT = "urgent"   # rouge : <=30 min avant l'heure (ou déjà passée), pas fait
STATUS_DONE = "done"       # vert : fait
STATUS_NEUTRAL = "neutral"  # neutre : ni urgent ni fait

# Fenêtre d'urgence, en minutes avant l'heure prévue.
URGENCY_WINDOW_MINUTES = 30

# ---------------------------------------------------------------------------
# Heure par défaut utilisée pour les tâches générées automatiquement dont le
# déclencheur n'est pas directement calé sur l'heure de l'adjudication
# (règles 1, 3 et 5 de la section 2.3 du blueprint). Modifiable au besoin.
# ---------------------------------------------------------------------------
AUTO_TASK_DEFAULT_TIME = "09:00"

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
NOTIFY_CHECK_INTERVAL_SECONDS = 30
NOTIFY_APP_NAME = "Desk CLI"

# ---------------------------------------------------------------------------
# Stockage
# ---------------------------------------------------------------------------
# Dossier data/ toujours relatif à la racine du projet (là où se trouve ce
# fichier), pour que cli.py et tui/app.py partagent exactement les mêmes
# fichiers JSON quel que soit le répertoire courant depuis lequel on lance
# python.
import pathlib  # noqa: E402

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
TASKS_FILE = DATA_DIR / "tasks.json"
AUCTIONS_FILE = DATA_DIR / "auctions.json"
NOTIFIED_FILE = DATA_DIR / "notified.json"
