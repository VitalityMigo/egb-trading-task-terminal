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

from datetime import date, timedelta  # noqa: E402
from typing import Optional  # noqa: E402

from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Horizontal, Vertical  # noqa: E402
from textual.widgets import DataTable, Footer, Static  # noqa: E402

import auction_service  # noqa: E402
import task_service  # noqa: E402
from constants import STATUS_DONE, STATUS_URGENT  # noqa: E402
from tui.screens.auction_form import AuctionFormModal  # noqa: E402
from tui.screens.auctions import (  # noqa: E402
    AUCTION_COLUMNS,
    NOTE_COLUMN_WIDTH as AUCTION_NOTE_WIDTH,
    build_auction_row,
)
from tui.screens.confirm import DeleteAuctionModal, DeleteScopeModal, TaskDetailModal  # noqa: E402
from tui.screens.dashboard import (  # noqa: E402
    NOTE_COLUMN_WIDTH as TASK_NOTE_WIDTH,
    TASK_COLUMNS,
    build_task_row,
)
from tui.screens.help import HelpModal  # noqa: E402
from tui.screens.task_form import TaskFormModal  # noqa: E402
from tui.widgets.command_bar import CommandBar  # noqa: E402
from tui.widgets.header_bar import HeaderBar  # noqa: E402

# Fenêtre utilisée par la case "Tout" (bandeau) côté Tâches — voir la note
# dans DeskApp._refresh_tasks. Nombre de lignes de chaque ligne du tableau
# (Tâches et Adjudications) : la grille d'un terminal ne connaît que des
# lignes entières — DataTable.add_row(height=N) ne peut donc offrir qu'un
# espacement "serré" (1, aucune ligne ajoutée) ou "large" (2, une ligne vide
# entière insérée) ; rien d'intermédiaire n'est possible (cell_padding ne
# joue que sur l'axe horizontal). 1 est le choix retenu : dense et lisible,
# dans l'esprit d'un vrai terminal Bloomberg.
ALL_WINDOW_PAST_DAYS = 90
ALL_WINDOW_FUTURE_DAYS = 365
ROW_HEIGHT = 1


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

    BINDINGS = [
        Binding("f1", "show_help", "Aide"),
        Binding("f2", "view_tasks", "Tâches"),
        Binding("f3", "view_auctions", "Adjudications"),
        Binding("f4", "add_item", "Ajouter"),
        Binding("f5", "mark_done", "Fait"),
        Binding("f6", "delete_item", "Suppr"),
        Binding("tab", "toggle_period", "Jour/Semaine", show=False),
        Binding("pagedown", "next_page", "Suiv.", show=False),
        Binding("pageup", "prev_page", "Préc.", show=False),
        Binding("left", "prev_page", "Préc.", show=False),
        Binding("right", "next_page", "Suiv.", show=False),
        Binding("slash", "focus_command", "Commande", key_display="/"),
        Binding("escape", "clear_command", "Annuler", show=False),
        Binding("f9", "quit", "Quitter"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.current_view = "tasks"        # "tasks" | "auctions"
        self.nav_mode = "day"               # "day" | "week" — navigateur global
        self.nav_anchor = date.today()      # date affichée (jour) ou contenue (semaine)
        self.show_all = {"tasks": False, "auctions": False}  # case "Tout" du bandeau, par vue
        self._task_occurrences: list = []
        self._auction_items: list = []

    # ------------------------------------------------------------------
    # Construction de l'écran
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("[T] Tâches", id="nav-tasks", classes="sidebar-item -active")
                yield Static("[A] Adjudications", id="nav-auctions", classes="sidebar-item")
            yield MainTable(
                id="main-table",
                cursor_type="row",
                cell_padding=3,
                cursor_foreground_priority="renderable",
            )
        yield CommandBar(id="command-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(30, self.refresh_data)
        self.refresh_data()

    # ------------------------------------------------------------------
    # Rafraîchissement des données affichées
    # ------------------------------------------------------------------

    def refresh_data(self) -> None:
        table = self.query_one("#main-table", DataTable)
        if self.current_view == "tasks":
            self._refresh_tasks(table)
        else:
            self._refresh_auctions(table)
        self._refresh_header_counts()
        self._refresh_sidebar()
        self.query_one(HeaderBar).set_nav(
            self.nav_mode, self.nav_anchor, self.show_all[self.current_view]
        )

    def _refresh_sidebar(self) -> None:
        self.query_one("#nav-tasks", Static).set_class(self.current_view == "tasks", "-active")
        self.query_one("#nav-auctions", Static).set_class(self.current_view == "auctions", "-active")

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
        self._task_occurrences = occurrences

        table.clear(columns=True)
        # Toutes les colonnes s'auto-dimensionnent sur leur contenu, sauf
        # Note qui est plafonnée (add_column width=...) : une note longue ne
        # doit jamais pousser "Tâche" hors de l'écran (le texte y est déjà
        # tronqué avec une ellipse par build_task_row, voir dashboard.py).
        for label in TASK_COLUMNS[:-1]:
            table.add_column(label)
        table.add_column(TASK_COLUMNS[-1], width=TASK_NOTE_WIDTH)
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
        for label in AUCTION_COLUMNS[:-1]:
            table.add_column(label)
        table.add_column(AUCTION_COLUMNS[-1], width=AUCTION_NOTE_WIDTH)
        for i, a in enumerate(auctions, start=1):
            table.add_row(*build_auction_row(i, a), height=ROW_HEIGHT)

    def _refresh_header_counts(self) -> None:
        # Les compteurs portent toujours sur les tâches du jour, quelle que
        # soit la vue et la position du navigateur actuellement affichées.
        start, end = task_service.day_range(date.today())
        counts = task_service.count_by_status(task_service.get_occurrences(start, end))
        self.query_one(HeaderBar).set_counts(counts[STATUS_URGENT], counts[STATUS_DONE])

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_view_tasks(self) -> None:
        self.current_view = "tasks"
        self.refresh_data()

    def action_view_auctions(self) -> None:
        self.current_view = "auctions"
        self.refresh_data()

    def action_toggle_period(self) -> None:
        """Tab : bascule le navigateur global entre mode Jour et mode
        Semaine (Tâches et Adjudications partagent le même état)."""
        self.nav_mode = "week" if self.nav_mode == "day" else "day"
        # Une action de navigation explicite doit toujours se voir : si
        # "Tout" était coché, la table ignorait nav_mode/nav_anchor et
        # affichait la même liste complète quoi qu'on bascule/déplace — on le
        # décoche donc ici (voir aussi _nav_step / action_nav_reset_today).
        self.show_all[self.current_view] = False
        self.refresh_data()
        self.query_one(CommandBar).clear()

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
        self.refresh_data()

    def action_toggle_show_all(self) -> None:
        """Case "Tout" du bandeau (cliquable à la souris) : bascule
        l'affichage de la vue courante entre le navigateur Jour/Semaine et
        la liste complète (fenêtre large), sans changer nav_mode/nav_anchor
        — décocher revient exactement là où on en était."""
        view = self.current_view
        self.show_all[view] = not self.show_all[view]
        self.refresh_data()

    def action_nav_reset_today(self) -> None:
        """Clic sur le libellé du navigateur (ex. "AUJOURD'HUI") : revient
        sur aujourd'hui sans changer de mode Jour/Semaine."""
        self.nav_anchor = date.today()
        self.show_all[self.current_view] = False
        self.refresh_data()

    def action_focus_command(self) -> None:
        self.query_one(CommandBar).focus_input()

    def action_clear_command(self) -> None:
        self.query_one(CommandBar).clear()
        self.query_one("#main-table", DataTable).focus()

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    # ------------------------------------------------------------------
    # Actions F4 / F5 / F6 sur la ligne sélectionnée
    # ------------------------------------------------------------------

    def _selected_row(self) -> Optional[int]:
        table = self.query_one("#main-table", DataTable)
        return table.cursor_row

    def action_add_item(self) -> None:
        if self.current_view == "tasks":
            self.push_screen(TaskFormModal(), self._on_task_form_result)
            return

        row = self._selected_row()
        if row is not None and 0 <= row < len(self._auction_items):
            auction = self._auction_items[row]
            self.push_screen(
                AuctionFormModal(auction=auction),
                lambda result, aid=auction.id: self._on_auction_form_result(result, aid),
            )
        else:
            self.push_screen(AuctionFormModal(), self._on_auction_form_result)

    def action_mark_done(self) -> None:
        if self.current_view != "tasks":
            self.bell()
            return
        row = self._selected_row()
        if row is None or not (0 <= row < len(self._task_occurrences)):
            self.bell()
            return
        occ = self._task_occurrences[row]
        task_service.mark_done(occ.task_id, task_service.parse_date(occ.date))
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
        else:
            if row is None or not (0 <= row < len(self._auction_items)):
                self.bell()
                return
            auction = self._auction_items[row]
            linked = task_service.list_tasks_for_auction(auction.id)
            self.push_screen(
                DeleteAuctionModal(auction, len(linked)),
                lambda cascade, a=auction: self._delete_auction(a, cascade),
            )

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
        else:
            if not (0 <= row < len(self._auction_items)):
                return
            auction = self._auction_items[row]
            self.push_screen(
                AuctionFormModal(auction=auction),
                lambda result, aid=auction.id: self._on_auction_form_result(result, aid),
            )

    def _on_row_action(self, occ, action: Optional[str]) -> None:
        if action == "done":
            task_service.mark_done(occ.task_id, task_service.parse_date(occ.date))
            self.refresh_data()
        elif action == "delete":
            if occ.is_recurring:
                self.push_screen(DeleteScopeModal(occ.name), lambda scope, o=occ: self._delete_task(o, scope))
            else:
                self._delete_task(occ, "series")
        else:
            # Fermeture simple (Échap/Fermer) : la Note a pu être modifiée et
            # déjà enregistrée par la modale elle-même (TaskDetailModal) — on
            # rafraîchit quand même pour que la colonne Note affiche tout de
            # suite la valeur à jour.
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
        self.refresh_data()

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

    def _on_auction_form_result(self, result: Optional[dict], editing_id: Optional[str] = None) -> None:
        if not result:
            return
        try:
            if editing_id:
                regenerate = result.pop("_regenerate", False)
                result.pop("_weekly_count", None)
                updated, warnings = auction_service.update_auction(editing_id, result, regenerate_tasks=bool(regenerate))
                self.current_view = "auctions"
                self.nav_mode = "day"
                self.nav_anchor = task_service.parse_date(updated.date)
                self.notify(f"Adjudication {updated.country} du {updated.date} modifiée.")
            else:
                weekly_count = result.pop("_weekly_count", None)
                result.pop("_regenerate", None)
                self.current_view = "auctions"
                if weekly_count:
                    results = auction_service.add_weekly_auctions(result, weekly_count)
                    warnings = [w for _, ws in results for w in ws]
                    first_auction = results[0][0]
                    self.nav_mode = "day"
                    self.nav_anchor = task_service.parse_date(first_auction.date)
                    self.notify(f"{len(results)} adjudications créées ({first_auction.country}, à partir du {first_auction.date}).")
                else:
                    new_auction, warnings = auction_service.add_auction(**result)
                    self.nav_mode = "day"
                    self.nav_anchor = task_service.parse_date(new_auction.date)
                    self.notify(f"Adjudication {new_auction.country} du {new_auction.date} ajoutée.")
            for w in warnings:
                self.notify(w, severity="warning")
            self.refresh_data()
        except auction_service.AuctionServiceError as exc:
            self.notify(str(exc), severity="error")

    # ------------------------------------------------------------------
    # Barre de commande façon <GO> (section 5.3)
    # ------------------------------------------------------------------

    def on_command_bar_submitted(self, message: CommandBar.Submitted) -> None:
        self._execute_command(message.command)

    def _execute_command(self, raw: str) -> None:
        parts = raw.split()
        if not parts:
            return
        verb = parts[0].upper()

        if verb == "TASK":
            self._handle_task_command(parts[1:])
        elif verb == "AUCTION":
            self._handle_auction_command(parts[1:])
        elif verb == "WEEK":
            # Navigateur global : s'applique à la vue actuelle (Tâches ou
            # Adjudications), pas seulement aux Tâches.
            self.nav_mode = "week"
            self.refresh_data()
        elif verb == "TODAY":
            self.nav_mode = "day"
            self.nav_anchor = date.today()
            self.refresh_data()
        elif verb == "TOMORROW":
            self.nav_mode = "day"
            self.nav_anchor = date.today() + timedelta(days=1)
            self.refresh_data()
        else:
            self.notify(f"Commande inconnue : {raw!r}", severity="error")

    def _handle_task_command(self, args: list[str]) -> None:
        sub = args[0].upper() if args else ""
        if sub == "ADD":
            self.action_view_tasks()
            self.push_screen(TaskFormModal(), self._on_task_form_result)
            return
        if sub in ("DONE", "DEL") and len(args) > 1 and args[1].isdigit():
            n = int(args[1])
            if self.current_view != "tasks" or not (1 <= n <= len(self._task_occurrences)):
                self.notify("Numéro de tâche invalide pour la vue actuelle.", severity="error")
                return
            occ = self._task_occurrences[n - 1]
            if sub == "DONE":
                task_service.mark_done(occ.task_id, task_service.parse_date(occ.date))
                self.refresh_data()
            else:
                if occ.is_recurring:
                    self.push_screen(DeleteScopeModal(occ.name), lambda scope, o=occ: self._delete_task(o, scope))
                else:
                    self._delete_task(occ, "series")
            return
        self.notify("Commande TASK inconnue. Essaie : TASK ADD / TASK DONE 3 / TASK DEL 3", severity="error")

    def _handle_auction_command(self, args: list[str]) -> None:
        sub = args[0].upper() if args else ""
        if sub == "ADD":
            self.action_view_auctions()
            self.push_screen(AuctionFormModal(), self._on_auction_form_result)
        elif sub == "LIST":
            self.action_view_auctions()
        else:
            self.notify("Commande AUCTION inconnue. Essaie : AUCTION ADD / AUCTION LIST", severity="error")


def main() -> None:
    DeskApp().run()


if __name__ == "__main__":
    main()
