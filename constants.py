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
    "NCO Calculation",
    "NCO Estimate",
    "NCO Historisation",
    "Risk 16h30",
    "Risk 17h30",
    "Swap File",
    "PnL Report",
    "Volume HREF",
    "MTS Quotation",
    "Italian Fees",
    "Fees italien Historisation",
    "Pre-Auction Bills Report",
    "Pre-Bills Report",
    "SSA Chain Report",
    "Weekly Macro Recap",
]

# ---------------------------------------------------------------------------
# Adjudications
# ---------------------------------------------------------------------------
COUNTRIES: list[str] = [
    "France",
    "Allemagne",
    "Italie",
    "Espagne",
    "Portugal",
    "Belgique",
    "Finland",
    "Slovenia",
    "UE",
]

# Code (ticker) affiché à la place du nom complet dans la colonne "Détails"
# de la vue Tâches (tui/screens/dashboard.py) — le nom complet reste utilisé
# partout ailleurs (formulaire d'adjudication, colonne "Pays" de la vue
# Adjudications, modale de détail d'une tâche).
COUNTRY_CODES: dict[str, str] = {
    "France": "FR",
    "Allemagne": "DE",
    "Italie": "IT",
    "Espagne": "ES",
    "Portugal": "PT",
    "Belgique": "BE",
    "Finland": "FI",
    "Slovenia": "SLV",
    "UE": "UE",
}

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
# Round 22 : le suivi des notifications n'est plus un process séparé
# (notify_daemon.py, retiré) — il tourne dans la boucle d'événements de la
# TUI elle-même (tui/app.py, Textual set_interval), donc cet intervalle
# s'applique désormais directement à un timer de l'app. Passé de 30s à 2min
# sur demande d'Augustin ("ça a peu d'importance à ce niveau là") ; l'app
# fait en plus une vérification immédiate à chaque lancement, pas seulement
# au premier tic de l'intervalle (voir DeskApp.on_mount).
NOTIFY_CHECK_INTERVAL_SECONDS = 120
NOTIFY_APP_NAME = "Desk CLI"

# Round 22 : deux notifications "générales" quotidiennes, en plus des
# notifications par tâche (30 min avant l'heure prévue) — récapitulatif du
# nombre de tâches du jour pas encore faites, à heure fixe. Dédupliquées comme
# les notifications par tâche (une seule fois par jour), voir
# notification_service._general_notification_key.
GENERAL_NOTIFICATION_TIMES: list[str] = ["08:45", "15:00"]

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
# Round 22 : journal des notifications réellement envoyées (titre, message,
# horodatage, type), distinct de NOTIFIED_FILE (qui ne sert qu'à la
# déduplication "une fois par jour" et ne garde pas l'historique). Alimente la
# page "Log" de la TUI, qui filtre à l'affichage sur la journée en cours —
# le fichier lui-même n'est pas limité à aujourd'hui (purge légère au-delà de
# 7 jours, voir notification_service._prune_log), pour rester utile en cas de
# besoin ponctuel de retrouver une notification de la veille.
NOTIFICATIONS_LOG_FILE = DATA_DIR / "notifications_log.json"

# Icône utilisée pour le toast Windows (win11toast) — rapproche visuellement
# la notification d'un toast "app" moderne (icône ronde + titre + texte),
# dans l'esprit d'un toast Teams, sans reproduire l'identité visuelle de
# Microsoft Teams. Absente sur les autres OS (non utilisée par le repli
# plyer). Si le fichier n'existe pas (ex. pas encore déployé), notifier.py
# l'ignore silencieusement plutôt que d'échouer.
NOTIFY_ICON_FILE = PROJECT_ROOT / "assets" / "notify_icon.png"
