"""
tui/app.py — point d'entrée de la nouvelle interface Textual, thème "Bloomberg
rétro" (blueprint sections 3 à 5). Aucune logique métier ici : tout passe par
task_service / auction_service, exactement comme cli.py. Les deux interfaces
lisent/écrivent les mêmes fichiers data/*.json, donc marquer une tâche faite
dans l'une la fait apparaître faite dans l'autre.

Architecture : un unique écran persistant (header + sidebar + DataTable +
barre de commande + footer restent toujours visibles) plutôt que des Screen
empilés pour chaque vue — voir la note dans tui/screens/dashboard.py. Les
formulaires et confirmations, eux, sont de vrais ModalScreen.

Comme l'outil n'est pas ouvert en continu, rien n'est mis en cache au-delà de
la session en cours : chaque rafraîchissement recalcule les occurrences et les
statuts à partir de l'heure actuelle (task_service.get_occurrences), donc
rouvrir l'app après une absence affiche immédiatement l'état à jour.

Lancement : python tui/app.py   (depuis la racine du projet, ou tui/app.py
directement — le sys.path est ajusté ci-dessous pour que ça marche dans les
deux cas).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from datetime import date, datetime, timedelta  # noqa: E402
from typing import Optional  # noqa: E402

from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Horizontal, Vertical  # noqa: E402
from textual.widgets import DataTable, Footer, Select, Static  # noqa: E402

import auction_service  # noqa: E402
import notification_service  # noqa: E402
import notifier  # noqa: E402
import task_service  # noqa: E402
from constants import NOTIFY_CHECK_INTERVAL_SECONDS, STATUS_DONE, STATUS_URGENT  # noqa: E402
from tui.screens.auction_form import AuctionFormModal  # noqa: E402
from tui.screens.auctions import (  # noqa: E402
    AUCTION_COLUMN_WIDTHS,
    AUCTION_COLUMNS,
    build_auction_row,
)
from tui.screens.confirm import DeleteAuctionModal, DeleteScopeModal, TaskDetailModal  # noqa: E402
from tui.screens.dashboard import (  # noqa: E402
    TASK_COLUMN_WIDTHS,
    TASK_COLUMNS,
    build_task_row,
)
from tui.screens.log import LOG_COLUMN_WIDTHS, LOG_COLUMNS, build_log_row  # noqa: E402
from tui.screens.task_form import TaskFormModal  # noqa: E402
from tui.widgets.header_bar import HeaderBar  # noqa: E402

# Fenêtre utilisée par la case "Tout" (bandeau) côté Tâches — voir la note
# dans DeskApp._refresh_tasks. Nombre de lignes de chaque ligne du tableau
# (Tâches et Adjudications) : add_row(height=N) prend un entier de lignes de
# TERMINAL — il n'existe rien entre "0 ligne ajoutée" (1) et "1 ligne vide
# entière ajoutée" (2). Ce n'est pas un réglage fin possible côté Textual,
# c'est la résolution minimale d'une grille de caractères (aucune lib TUI ne
# peut faire un demi-interligne, pas plus que vim ou nano). 1 (serré) essayé,
# jugé trop dense ; 2 (plein interligne) essayé, jugé trop espacé — donc pas
# de 3e valeur disponible ici. On reste sur 1 : avec le padding des colonnes
# élargi (cell_padding=4) et le tri des largeurs de colonnes qui suit, la
# densité reste lisible sans le "trou" d'une ligne vide entière.
ALL_WINDOW_PAST_DAYS = 90
ALL_WINDOW_FUTURE_DAYS = 365
ROW_HEIGHT = 1

# Round 18 : libellé de l'option "aucun filtre" du sélecteur "par
# adjudication" (sidebar, vue Tâches uniquement) — toujours la première
# option de la liste (même convention que les autres Select de l'app :
# toujours une vraie valeur par défaut, jamais un Select.NULL/blank), donc
# aussi le moyen de "reset" le filtre en un clic.
ALL_AUCTIONS_FILTER_LABEL = "Toutes"


class MainTable(DataTable):
    """DataTable central. Redéfinit tab/pageup/pagedown/left/right : par
    défaut Textual utilise tab pour déplacer le focus, pageup/pagedown/
    left/right pour faire défiler ou déplacer le curseur dans le tableau lui
    même — ces bindings, posés directement sur le widget focusé, gagnent sur
    les bindings équivalents déclarés au niveau de l'App. Le navigateur
    jour/semaine global doit rester utilisable même quand le tableau a le
    focus (cas normal : c'est le seul widget interactif de l'écran principal)."""

    BINDINGS = [
        Binding("tab", "app.toggle_period", "Jour/Semaine", show=False),
        Binding("pageup", "app.prev_page", "Préc.", show=False),
        Binding("pagedown", "app.next_page", "Suiv.", show=False),
        Binding("left", "app.prev_page", "Préc.", show=False),
        Binding("right", "app.next_page", "Suiv.", show=False),
    ]


class DeskApp(App):
    """Interface principale, style terminal Bloomberg rétro."""

    CSS_PATH = "theme.tcss"
    TITLE = "DESK CLI"

    # Round 23 : réorganisation demandée par Augustin — "Aide" (F1) et la
    # barre de commande ("/") retirées (jugées inutiles à l'usage : tout ce
    # qu'elles apportaient a un équivalent clavier direct ailleurs — F4 pour
    # ajouter, F5/F6 pour fait/suppr., Tab pour la semaine, F8 pour tester
    # les notifs). F1-F9 renumérotés en conséquence ; F7 "Actualiser" est
    # nouveau (voir action_refresh_now). tui/screens/help.py et
    # tui/widgets/command_bar.py restent sur le disque (code mort, non
    # importés) plutôt que supprimés — pas de raison de toucher à plus de
    # fichiers que nécessaire pour ce changement.
    BINDINGS = [
        Binding("f1", "view_tasks", "Tâches"),
        Binding("f2", "view_auctions", "Adjudications"),
        Binding("f3", "view_log", "Log"),
        Binding("f4", "add_item", "Ajouter"),
        Binding("f5", "mark_done", "Fait"),
        Binding("f6", "delete_item", "Suppr"),
        Binding("f7", "refresh_now", "Actualiser"),
        Binding("f8", "notif_test", "Notif"),
        Binding("f9", "quit", "Quitter"),
        Binding("tab", "toggle_period", "Jour/Semaine", show=False),
        Binding("pagedown", "next_page", "Suiv.", show=False),
        Binding("pageup", "prev_page", "Préc.", show=False),
        Binding("left", "prev_page", "Préc.", show=False),
        Binding("right", "next_page", "Suiv.", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.current_view = "tasks"        # "tasks" | "auctions" | "log"
        self.nav_mode = "day"               # "day" | "week" — navigateur global
        self.nav_anchor = date.today()      # date affichée (jour) ou contenue (semaine)
        # Round 22 : "log" ignore nav_mode/nav_anchor/show_all (toujours la
        # journée en cours, voir _refresh_log) — la clé existe quand même
        # dans ce dict pour que _refresh_header_counts/toggle restent
        # génériques sans cas particulier sur current_view.
        self.show_all = {"tasks": False, "auctions": False, "log": False}  # case "Tout" du bandeau, par vue
        self._task_occurrences: list = []
        self._auction_items: list = []
        self._log_entries: list = []
        # Round 18 : filtre "par adjudication" de la vue Tâches (sidebar).
        # None = aucun filtre ("Toutes"). Propre à la vue Tâches (jamais
        # appliqué côté Adjudications), mais la valeur persiste si on va voir
        # les Adjudications puis qu'on revient sur Tâches (même logique que
        # nav_mode/nav_anchor, partagés et non réinitialisés au changement de
        # vue). `_task_auction_signature` mémorise la dernière liste
        # d'adjudications à venir utilisée pour peupler le Select : ne
        # reconstruire les options que si elle a changé (voir
        # _refresh_task_auction_filter, sinon chaque refresh_data() — toutes
        # les 30s — déclencherait un cycle d'événements Select.Changed
        # synthétiques).
        self.task_auction_filter: Optional[str] = None
        self._task_auction_signature: Optional[tuple] = None

    # ------------------------------------------------------------------
    # Construction de l'écran
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("[T] Tâches", id="nav-tasks", classes="sidebar-item -active")
                yield Static("[A] Adjudications", id="nav-auctions", classes="sidebar-item")
                yield Static("[L] Log", id="nav-log", classes="sidebar-item")
                # Round 18 : filtre "par adjudication", propre à la vue
                # Tâches — masqué (display=False) côté Adjudications par
                # _refresh_task_auction_filter, jamais retiré du DOM. Options
                # réelles peuplées au premier refresh_data() (on_mount) ; le
                # placeholder ici n'est visible qu'une fraction de frame.
                yield Static("Filtre adju.", id="sidebar-filter-label", classes="field-label sidebar-filter-label")
                yield Select(
                    [(ALL_AUCTIONS_FILTER_LABEL, None)],
                    value=None,
                    allow_blank=False,
                    id="task-auction-filter",
                )
            yield MainTable(
                id="main-table",
                cursor_type="row",
                cell_padding=4,
                cursor_foreground_priority="renderable",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(30, self.refresh_data)
        # Round 22 : le suivi des notifications tourne désormais dans ce même
        # process (plus de notify_daemon.py séparé) — timer dédié (2 min,
        # voir constants.NOTIFY_CHECK_INTERVAL_SECONDS) + une vérification
        # immédiate au lancement, pour ne pas attendre le premier tic avant
        # de rattraper une tâche déjà urgente à l'ouverture.
        self.set_interval(NOTIFY_CHECK_INTERVAL_SECONDS, self._check_notifications)
        self.refresh_data()
        self._check_notifications()
        # Round 23 : par défaut Textual donne le focus au premier widget
        # focusable du DOM (le Select "Filtre adju." de la sidebar) et non au
        # tableau — sans ça, les flèches haut/bas (navigation ligne par ligne
        # demandée par Augustin) n'auraient rien à faire puisque le tableau ne
        # serait jamais focusé tant qu'on n'a pas cliqué dessus à la souris.
        self.query_one("#main-table", DataTable).focus()

    # ------------------------------------------------------------------
    # Rafraîchissement des données affichées
    # ------------------------------------------------------------------

    def refresh_data(self, *, reset_cursor: bool = False) -> None:
        """Round 23 : `table.clear()` (dans _refresh_tasks/_refresh_auctions/
        _refresh_log ci-dessous) ramène toujours le curseur du DataTable à la
        ligne 0 — et refresh_data() est appelé après CHAQUE action (F5, F6,
        ajout, ...) ainsi que par le timer périodique (30s). Sans rien faire
        de plus, ça voulait dire que F5/F6 ne portaient jamais que sur la
        première ligne en pratique, quoi qu'on ait navigué avec les flèches
        haut/bas juste avant (déjà géré nativement par Textual sur le
        DataTable, aucun code à écrire pour ça) — signalé par Augustin.
        Fix : on mémorise la ligne courante avant de reconstruire le tableau,
        et on la restaure après (bornée au nouveau nombre de lignes) — sauf
        quand `reset_cursor=True`, utilisé par les actions qui changent
        vraiment ce qui est affiché (bascule de vue, changement de jour/
        semaine, case "Tout") : là, revenir en haut de la nouvelle liste a
        plus de sens que de garder un index qui ne correspond plus à rien de
        précis."""
        # Le filtre "par adjudication" doit être résolu avant de construire
        # le tableau (il peut s'auto-réinitialiser si l'adjudication choisie
        # vient de passer, voir _refresh_task_auction_filter).
        self._refresh_task_auction_filter()
        table = self.query_one("#main-table", DataTable)
        keep_row = 0 if reset_cursor else (table.cursor_row or 0)
        if self.current_view == "tasks":
            self._refresh_tasks(table)
        elif self.current_view == "auctions":
            self._refresh_auctions(table)
        else:
            self._refresh_log(table)
        if table.row_count:
            table.move_cursor(row=min(keep_row, table.row_count - 1))
        self._refresh_header_counts()
        self._refresh_sidebar()
        self.query_one(HeaderBar).set_nav(
            self.nav_mode, self.nav_anchor, self.show_all[self.current_view]
        )

    def _refresh_sidebar(self) -> None:
        self.query_one("#nav-tasks", Static).set_class(self.current_view == "tasks", "-active")
        self.query_one("#nav-auctions", Static).set_class(self.current_view == "auctions", "-active")
        self.query_one("#nav-log", Static).set_class(self.current_view == "log", "-active")

    def _refresh_task_auction_filter(self) -> None:
        """Round 18 : peuple/actualise le Select "Filtre adju." de la
        sidebar — uniquement les adjudications à venir
        (auction_service.get_upcoming_auctions), étiquette compacte "<code>
        <jour>/<mois>" (auction_service.format_auction_short_label). Visible
        uniquement en vue Tâches (masqué, pas retiré, côté Adjudications).

        Ne touche `Select.set_options`/`.value` QUE si la liste des
        adjudications à venir a réellement changé depuis le dernier appel
        (comparaison par tuple d'ids, `_task_auction_signature`) : Textual
        poste un message `Select.Changed` — traité de façon asynchrone, donc
        après le retour de cette méthode — à chaque `set_options` et à
        chaque assignation de `.value`, y compris programmatique. Le faire
        sans condition à chaque refresh_data() (toutes les 30s, plus après
        chaque action) déclencherait donc un `on_select_changed` synthétique
        à chaque cycle, qui rappellerait refresh_data(), qui referait
        set_options/.value, etc. — un bouclage perpétuel. En ne le faisant
        que lorsque la liste change réellement (rare : nouvelle adjudication
        ajoutée, ou une adjudication qui vient de passer minuit et sort de la
        fenêtre "à venir"), les événements synthétiques générés se corrigent
        d'eux-mêmes en 1-2 cycles de refresh_data() (bon marché, aucun effet
        visible) sans jamais boucler indéfiniment — voir on_select_changed."""
        select = self.query_one("#task-auction-filter", Select)
        select.display = self.current_view == "tasks"

        upcoming = auction_service.get_upcoming_auctions()
        signature = tuple(a.id for a in upcoming)
        if signature == self._task_auction_signature:
            return
        self._task_auction_signature = signature

        options = [(ALL_AUCTIONS_FILTER_LABEL, None)] + [
            (auction_service.format_auction_short_label(a), a.id) for a in upcoming
        ]
        # Garde la sélection en cours si l'adjudication filtrée est toujours
        # à venir, sinon retombe sur "Toutes" (ex. l'adjudication choisie
        # vient de passer, ou a été supprimée) plutôt que de filtrer
        # silencieusement sur un id qui ne peut plus jamais matcher.
        keep = self.task_auction_filter if self.task_auction_filter in signature else None
        select.set_options(options)
        select.value = keep
        self.task_auction_filter = keep

    def on_select_changed(self, event: Select.Changed) -> None:
        """Round 18 : seul le Select "task-auction-filter" (sidebar) est géré
        ici — les Select des modaux ont chacun leur propre gestionnaire sur
        leur propre Screen. Le garde-fou `value == self.task_auction_filter`
        absorbe les événements synthétiques rejoués par
        _refresh_task_auction_filter (set_options/.value programmatiques)
        sans déclencher de refresh_data() supplémentaire inutile une fois la
        valeur reconverge vers son état correct."""
        if event.select.id != "task-auction-filter":
            return
        value = None if event.value is Select.BLANK else event.value
        if value == self.task_auction_filter:
            return
        self.task_auction_filter = value
        self.refresh_data()

    def _nav_range(self) -> tuple[date, date]:
        """Plage de dates couverte par le navigateur global (jour/semaine),
        partagée entre la vue Tâches et la vue Adjudications."""
        return task_service.nav_range(self.nav_mode, self.nav_anchor)

    def _refresh_tasks(self, table: DataTable) -> None:
        if self.show_all["tasks"]:
            # "Tout" (case à cocher du bandeau) : pas de filtre de date. Les
            # récurrences (daily/weekly) étant par nature infinies, on prend
            # une fenêtre large plutôt qu'un intervalle non borné — largement
            # suffisant pour un desk (rien n'est planifié sur des années).
            start, end = date.today() - timedelta(days=ALL_WINDOW_PAST_DAYS), date.today() + timedelta(days=ALL_WINDOW_FUTURE_DAYS)
        else:
            start, end = self._nav_range()
        occurrences = task_service.get_occurrences(start, end)
        if self.task_auction_filter:
            # Round 18 : filtre "par adjudication" (sidebar) — combiné en ET
            # avec la fenêtre de dates ci-dessus (jour/semaine ou "Tout"),
            # pas à sa place : on affine ce qui est déjà affiché, on ne
            # l'ignore pas.
            occurrences = [o for o in occurrences if o.auction_id == self.task_auction_filter]
        self._task_occurrences = occurrences

        table.clear(columns=True)
        # Toutes les colonnes ont une largeur fixe définie dans dashboard.py
        # (TASK_COLUMN_WIDTHS), aucune en auto-dimensionnement Textual — voir
        # le commentaire de TASK_COLUMN_WIDTHS pour pourquoi ("Tâche" et
        # "Statut" étaient auto-dimensionnées jusqu'ici, converties en
        # largeurs fixes suite à un bug de colonnes déformées après un
        # aller-retour Semaine + case "Tout"). N°/Heure n'ont besoin que de
        # peu de place, Détails et Note sont plafonnées et déjà tronquées
        # avec une ellipse par build_task_row côté dashboard.py.
        for label in TASK_COLUMNS:
            table.add_column(label, width=TASK_COLUMN_WIDTHS.get(label))
        for i, occ in enumerate(occurrences, start=1):
            table.add_row(*build_task_row(i, occ), height=ROW_HEIGHT)

    def _refresh_auctions(self, table: DataTable) -> None:
        # Vue globale : mêmes bornes (jour/semaine) que la vue Tâches, plus
        # de pagination fixe — le navigateur du bandeau pilote les deux vues.
        if self.show_all["auctions"]:
            # Les adjudications sont des entrées explicites (pas de
            # récurrence infinie) : "Tout" peut être un vrai sans-filtre.
            auctions = auction_service.list_auctions_sorted()
        else:
            start, end = self._nav_range()
            auctions = auction_service.get_auctions_in_range(start, end)
        self._auction_items = auctions

        table.clear(columns=True)
        # Mêmes largeurs fixes déterministes que la vue Tâches (voir le
        # commentaire au-dessus, dans _refresh_tasks, et AUCTION_COLUMN_WIDTHS
        # dans tui/screens/auctions.py) : aucune colonne en auto-dimensionnement.
        for label in AUCTION_COLUMNS:
            table.add_column(label, width=AUCTION_COLUMN_WIDTHS.get(label))
        for i, a in enumerate(auctions, start=1):
            table.add_row(*build_auction_row(i, a), height=ROW_HEIGHT)

    def _refresh_log(self, table: DataTable) -> None:
        # Round 22 : toujours la journée en cours, jamais piloté par le
        # navigateur jour/semaine du bandeau (contrairement aux vues Tâches
        # et Adjudications) — voir la note dans __init__.
        entries = notification_service.get_today_log()
        self._log_entries = entries

        table.clear(columns=True)
        for label in LOG_COLUMNS:
            table.add_column(label, width=LOG_COLUMN_WIDTHS.get(label))
        for i, entry in enumerate(entries, start=1):
            table.add_row(*build_log_row(i, entry), height=ROW_HEIGHT)

    def _check_notifications(self) -> None:
        """Timer (constants.NOTIFY_CHECK_INTERVAL_SECONDS) + appel immédiat
        au lancement (on_mount) — voir notification_service.run_check pour la
        logique (tâches urgentes + récapitulatifs matin/après-midi). Si la
        page Log est actuellement affichée, on la rafraîchit tout de suite
        pour qu'une notification qui vient d'être envoyée y apparaisse sans
        attendre le prochain refresh_data() périodique (jusqu'à 30s)."""
        notification_service.run_check(datetime.now())
        if self.current_view == "log":
            self.refresh_data()

    def _refresh_header_counts(self) -> None:
        # Les compteurs portent toujours sur les tâches du jour, quelle que
        # soit la vue et la position du navigateur actuellement affichées.
        start, end = task_service.day_range(date.today())
        counts = task_service.count_by_status(task_service.get_occurrences(start, end))
        # "à faire" = tout ce qui n'est pas encore fait aujourd'hui (urgent
        # inclus) — Augustin préfère voir ce qui reste plutôt que ce qui a
        # déjà été fait.
        todo = sum(counts.values()) - counts[STATUS_DONE]
        self.query_one(HeaderBar).set_counts(counts[STATUS_URGENT], todo)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_view_tasks(self) -> None:
        self.current_view = "tasks"
        self.refresh_data(reset_cursor=True)
        self._focus_table()

    def action_view_auctions(self) -> None:
        self.current_view = "auctions"
        self.refresh_data(reset_cursor=True)
        self._focus_table()

    def action_view_log(self) -> None:
        self.current_view = "log"
        self.refresh_data(reset_cursor=True)
        self._focus_table()

    def _focus_table(self) -> None:
        """Round 23 : redonne le focus au tableau après un changement de vue
        (F1/F2/F3) — au cas où le focus aurait dérivé sur le Select "Filtre
        adju." de la sidebar (clic souris dessus) entre-temps, ce qui aurait
        sinon fait passer les flèches haut/bas dans le menu déroulant du
        Select plutôt que dans les lignes du tableau."""
        self.query_one("#main-table", DataTable).focus()

    def action_toggle_period(self) -> None:
        """Tab : bascule le navigateur global entre mode Jour et mode
        Semaine (Tâches et Adjudications partagent le même état)."""
        self.nav_mode = "week" if self.nav_mode == "day" else "day"
        # Une action de navigation explicite doit toujours se voir : si
        # "Tout" était coché, la table ignorait nav_mode/nav_anchor et
        # affichait la même liste complète quoi qu'on bascule/déplace — on le
        # décoche donc ici (voir aussi _nav_step / action_nav_reset_today).
        self.show_all[self.current_view] = False
        self.refresh_data(reset_cursor=True)

    def action_next_page(self) -> None:
        self._nav_step(1)

    def action_prev_page(self) -> None:
        self._nav_step(-1)

    def _nav_step(self, direction: int) -> None:
        """Flèche droite/gauche (ou PgDn/PgUp) : avance/recule d'un jour en
        mode Jour, d'une semaine en mode Semaine — applicable aux deux vues."""
        if self.nav_mode == "week":
            self.nav_anchor += timedelta(weeks=direction)
        else:
            self.nav_anchor += timedelta(days=direction)
        # Voir le commentaire dans action_toggle_period : sans ça, une
        # flèche pressée alors que "Tout" est coché change bien nav_anchor
        # (visible dans le libellé du bandeau) mais la table affichée reste
        # identique, ce qui donnait l'impression que "la flèche ne marche
        # pas".
        self.show_all[self.current_view] = False
        self.refresh_data(reset_cursor=True)

    def action_toggle_show_all(self) -> None:
        """Case "Tout" du bandeau (cliquable à la souris) : bascule
        l'affichage de la vue courante entre le navigateur Jour/Semaine et
        la liste complète (fenêtre large), sans changer nav_mode/nav_anchor
        — décocher revient exactement là où on en était."""
        view = self.current_view
        self.show_all[view] = not self.show_all[view]
        self.refresh_data(reset_cursor=True)

    def action_nav_reset_today(self) -> None:
        """Clic sur le libellé du navigateur (ex. "AUJOURD'HUI") : revient
        sur aujourd'hui sans changer de mode Jour/Semaine."""
        self.nav_anchor = date.today()
        self.show_all[self.current_view] = False
        self.refresh_data(reset_cursor=True)

    def action_refresh_now(self) -> None:
        """F7 "Actualiser" (round 23) : force un rafraîchissement immédiat de
        l'affichage — get_occurrences()/compute_status() recalculent déjà les
        statuts à partir de l'heure actuelle à chaque appel (comme au
        lancement, voir le docstring en tête de fichier), donc c'est
        exactement le même calcul que celui du timer périodique (30s) ou
        d'un relancement de l'app, juste déclenché à la demande plutôt que
        d'attendre — utile pour voir tout de suite une tâche repasser en
        rouge à l'heure convenue plutôt que d'attendre jusqu'à 30s. Curseur
        préservé (pas une navigation, juste un rafraîchissement du même
        contenu)."""
        self.refresh_data()
        self.notify("Affichage actualisé.")

    # ------------------------------------------------------------------
    # Actions F4 / F5 / F6 sur la ligne sélectionnée
    # ------------------------------------------------------------------

    def _selected_row(self) -> Optional[int]:
        table = self.query_one("#main-table", DataTable)
        return table.cursor_row

    def action_add_item(self) -> None:
        # F4 "Ajouter" ouvre toujours le formulaire d'ajout, quelle que soit
        # la vue — jamais un formulaire d'édition, même si une ligne est
        # sélectionnée dans le tableau. Bug corrigé : côté Adjudications,
        # cette action rouvrait par erreur l'adjudication sous le curseur
        # (`DataTable.cursor_row` vaut 0 dès qu'une ligne existe, ce n'est
        # jamais None même sans sélection explicite de l'utilisateur) au
        # lieu d'ouvrir un formulaire vide — reproductible dès qu'une
        # adjudication existait déjà pour le jour affiché. L'édition d'une
        # adjudication existante passe uniquement par le clic/Entrée sur sa
        # ligne (on_data_table_row_selected) ou par la commande "AUCTION
        # ADD", jamais par F4 — même principe déjà en place côté Tâches
        # ci-dessus, qui n'a jamais eu ce bug.
        if self.current_view == "tasks":
            self.push_screen(TaskFormModal(), self._on_task_form_result)
        elif self.current_view == "auctions":
            self.push_screen(AuctionFormModal(), self._on_auction_form_result)
        else:
            # Vue Log (round 22) : rien à ajouter, c'est un journal en
            # lecture seule — même geste (bip) que F5/F6 sur cette vue.
            self.bell()

    def action_mark_done(self) -> None:
        """F5 : agit sur la ligne sous le curseur (haut/bas natif du
        DataTable, curseur désormais préservé entre deux refresh_data() —
        voir son docstring), pas toujours la première ligne comme avant
        round 23. Round 23 : bascule dans les deux sens (comme le bouton
        Fait/Pas fait de TaskDetailModal depuis le round 9) — une tâche déjà
        faite repasse "pas fait" au lieu de rester bloquée sur "fait"."""
        if self.current_view != "tasks":
            self.bell()
            return
        row = self._selected_row()
        if row is None or not (0 <= row < len(self._task_occurrences)):
            self.bell()
            return
        occ = self._task_occurrences[row]
        occurrence_date = task_service.parse_date(occ.date)
        if occ.status == STATUS_DONE:
            task_service.mark_undone(occ.task_id, occurrence_date)
            self.notify(f"« {occ.name} » repassée pas fait.")
        else:
            task_service.mark_done(occ.task_id, occurrence_date)
            self.notify(f"« {occ.name} » marquée faite.")
        self.refresh_data()

    def action_delete_item(self) -> None:
        row = self._selected_row()
        if self.current_view == "tasks":
            if row is None or not (0 <= row < len(self._task_occurrences)):
                self.bell()
                return
            occ = self._task_occurrences[row]
            if occ.is_recurring:
                self.push_screen(DeleteScopeModal(occ.name), lambda scope, o=occ: self._delete_task(o, scope))
            else:
                self._delete_task(occ, "series")
        elif self.current_view == "auctions":
            if row is None or not (0 <= row < len(self._auction_items)):
                self.bell()
                return
            auction = self._auction_items[row]
            linked = task_service.list_tasks_for_auction(auction.id)
            self.push_screen(
                DeleteAuctionModal(auction, len(linked)),
                lambda cascade, a=auction: self._delete_auction(a, cascade),
            )
        else:
            # Vue Log (round 22) : rien à supprimer, journal en lecture seule.
            self.bell()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Entrée (ou clic) sur une ligne : ouvre le détail compact (tâches,
        avec Note éditable directement) ou le formulaire d'édition pré-rempli
        (adjudications) — amélioration UX par rapport à la v1 (section 5.1 du
        blueprint)."""
        row = event.cursor_row
        if self.current_view == "tasks":
            if not (0 <= row < len(self._task_occurrences)):
                return
            occ = self._task_occurrences[row]
            self.push_screen(TaskDetailModal(occ), lambda action, o=occ: self._on_row_action(o, action))
        elif self.current_view == "auctions":
            if not (0 <= row < len(self._auction_items)):
                return
            auction = self._auction_items[row]
            self.push_screen(
                AuctionFormModal(auction=auction),
                lambda result, aid=auction.id: self._on_auction_form_result(result, aid),
            )
        # Vue Log (round 22) : entrées non cliquables, pas de détail à ouvrir
        # — un clic/Entrée ne fait donc rien de plus que déplacer le curseur.

    def _on_row_action(self, occ, action: Optional[str]) -> None:
        if action == "delete":
            if occ.is_recurring:
                self.push_screen(DeleteScopeModal(occ.name), lambda scope, o=occ: self._delete_task(o, scope))
            else:
                self._delete_task(occ, "series")
        else:
            # Fermeture simple (Échap/Fermer) : la Note, le switch Fait/Pas
            # fait et la récurrence ont pu être modifiés et déjà enregistrés
            # par la modale elle-même (TaskDetailModal, mutation en direct
            # sur chaque champ) — on rafraîchit quand même pour que le
            # tableau affiche tout de suite les valeurs à jour.
            self.refresh_data()

    # ------------------------------------------------------------------
    # Callbacks des modaux
    # ------------------------------------------------------------------

    def _delete_task(self, occ, scope: Optional[str]) -> None:
        if scope is None:
            return
        task_service.delete_task(occ.task_id, scope=scope, occurrence_date=task_service.parse_date(occ.date))
        self.refresh_data()

    def _delete_auction(self, auction, cascade: Optional[bool]) -> None:
        if cascade is None:
            return
        auction_service.delete_auction(auction.id, cascade=bool(cascade))
        self.refresh_data()

    def _request_delete_auction(self, auction_id: str) -> None:
        """Round 16 : bouton "Suppr." dans AuctionFormModal (mode édition) —
        même flux de confirmation (DeleteAuctionModal, cascade optionnelle
        sur les tâches liées) que le raccourci clavier de suppression
        (action_delete_item), déclenché ici depuis la modale de détail."""
        auction = auction_service.get_auction(auction_id)
        if auction is None:
            return
        linked = task_service.list_tasks_for_auction(auction.id)
        self.push_screen(
            DeleteAuctionModal(auction, len(linked)),
            lambda cascade, a=auction: self._delete_auction(a, cascade),
        )

    def _on_task_form_result(self, result: Optional[dict]) -> None:
        if not result:
            return
        try:
            new_task = task_service.add_task(**result)
        except task_service.TaskServiceError as exc:
            self.notify(str(exc), severity="error")
            return

        self.current_view = "tasks"
        target = self._first_occurrence_date(new_task.id)
        if target is not None:
            self.nav_mode = "day"
            self.nav_anchor = target
            self.notify(f"« {new_task.name} » ajoutée.")
        else:
            self.notify(
                f"« {new_task.name} » ajoutée, mais aucune occurrence à venir — "
                "vérifie la date saisie si tu t'attendais à la voir.",
                severity="warning",
            )
        self.refresh_data(reset_cursor=True)

    def _first_occurrence_date(self, task_id: str) -> Optional[date]:
        """Date à afficher pour qu'une tâche qu'on vient d'ajouter soit
        visible tout de suite (navigateur basculé dessus en mode Jour),
        plutôt que de sembler avoir disparu alors qu'elle est bien
        enregistrée. Cherche la première occurrence à venir ; si la tâche
        n'a que des occurrences passées (date antérieure saisie), retombe
        sur la plus récente d'entre elles."""
        today = date.today()
        start, end = today - timedelta(days=7), today + timedelta(days=365)
        matches = [
            task_service.parse_date(o.date)
            for o in task_service.get_occurrences(start, end)
            if o.task_id == task_id
        ]
        if not matches:
            return None
        upcoming = [d for d in matches if d >= today]
        return min(upcoming) if upcoming else max(matches)

    def _on_auction_form_result(self, result, editing_id: Optional[str] = None) -> None:
        if not result:
            return
        if result == "delete":
            # Round 16 : bouton "Suppr." de AuctionFormModal (mode édition
            # uniquement — result vaut alors toujours une chaîne "delete",
            # jamais un dict, donc pas d'ambiguïté avec le cas normal ci-dessous).
            if editing_id:
                self._request_delete_auction(editing_id)
            return
        try:
            if editing_id:
                updated, warnings = auction_service.update_auction(editing_id, result)
                self.current_view = "auctions"
                self.nav_mode = "day"
                self.nav_anchor = task_service.parse_date(updated.date)
                self.notify(f"Adjudication {updated.country} du {updated.date} modifiée.")
            else:
                self.current_view = "auctions"
                new_auction, warnings = auction_service.add_auction(**result)
                self.nav_mode = "day"
                self.nav_anchor = task_service.parse_date(new_auction.date)
                self.notify(f"Adjudication {new_auction.country} du {new_auction.date} ajoutée.")
            for w in warnings:
                self.notify(w, severity="warning")
            self.refresh_data(reset_cursor=True)
        except auction_service.AuctionServiceError as exc:
            self.notify(str(exc), severity="error")

    def action_notif_test(self) -> None:
        """F8 "Notif" (round 23 : déplacé de F10, la barre de commande "NOTIF
        TEST" qui appelait la même chose ayant été retirée en même temps) —
        envoie une notification de test immédiate."""
        self._send_test_notification()

    def _send_test_notification(self) -> None:
        """Round 22 (suite 3) : ajout d'un diagnostic dans le toast *interne*
        de l'app (celui-ci, contrairement au toast système, s'affiche
        toujours, même si aucun mécanisme système ne fonctionne) — pour
        pouvoir dire précisément quel mécanisme a été tenté et pourquoi il a
        échoué, sans avoir besoin d'accéder à la console (invisible pendant
        qu'une TUI Textual tourne, elle occupe l'écran alternatif du
        terminal). Repose sur `notifier.last_attempt_log`, rempli à chaque
        appel de `notifier.send_notification()`."""
        ok = notification_service.send_test_notification()
        used = ", ".join(
            f"{mechanism}"
            if error is None
            else f"{mechanism} → échec ({error})"
            for mechanism, error in notifier.last_attempt_log
        ) or "aucun mécanisme disponible"
        if ok:
            # Le mécanisme qui a réussi est toujours le dernier de la liste ;
            # les précédents (le cas échéant) ont échoué avant lui.
            self.notify(f"Notification de test envoyée. Essais : {used}.")
        else:
            self.notify(
                f"Notification système non envoyée (repli console). Essais : {used}.",
                severity="warning",
            )
        if self.current_view == "log":
            self.refresh_data()


def main() -> None:
    DeskApp().run()


if __name__ == "__main__":
    main()
