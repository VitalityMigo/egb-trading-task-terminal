"""
tui/screens/confirm.py — petits modaux de confirmation / choix rapide :
- DeleteScopeModal : occurrence du jour vs. toute la série (tâche récurrente).
- DeleteAuctionModal : suppression d'une adjudication, cascade optionnelle sur
  les tâches liées (case à cocher dans la même modale, section 5.5).
- TaskDetailModal : détail d'une occurrence de tâche (touche Entrée ou clic
  dans le DataTable, vue Tâches) — affichage compact des infos + édition
  directe de la Note, plus discret qu'un formulaire complet.
"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from rich.text import Text
from textual.widgets import Button, Checkbox, Input, Select, Static

import auction_service
import task_service
from constants import (
    RECURRENCE_LABELS,
    RECURRENCE_ONCE,
    RECURRENCE_TYPES,
    RECURRENCE_WEEKLY,
    STATUS_DONE,
    STATUS_NEUTRAL,
    WEEKDAY_LABELS,
)
from tui.screens.dashboard import STATUS_COLORS, STATUS_LABELS, format_details


class DeleteScopeModal(ModalScreen[Optional[str]]):
    """Retourne "occurrence", "series", ou None si annulé."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    def __init__(self, task_name: str) -> None:
        super().__init__()
        self.task_name = task_name

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Static("SUPPRIMER UNE TÂCHE RÉCURRENTE", classes="modal-title")
            yield Static(f"« {self.task_name} » se répète. Que veux-tu supprimer ?")
            with Horizontal(classes="modal-buttons"):
                yield Button("Annuler", id="btn-cancel")
                yield Button("Occurrence du jour", id="btn-occurrence")
                yield Button("Toute la série", variant="error", id="btn-series")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-occurrence":
            self.dismiss("occurrence")
        elif event.button.id == "btn-series":
            self.dismiss("series")

    def action_cancel(self) -> None:
        self.dismiss(None)


class DeleteAuctionModal(ModalScreen[Optional[bool]]):
    """Retourne True/False (cascade ou non), ou None si annulé."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    def __init__(self, auction, linked_count: int) -> None:
        super().__init__()
        self.auction = auction
        self.linked_count = linked_count

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Static("SUPPRIMER L'ADJUDICATION", classes="modal-title")
            yield Static(f"{self.auction.country} — {self.auction.date}")
            if self.linked_count:
                yield Checkbox(
                    f"Supprimer aussi les {self.linked_count} tâche(s) liée(s)",
                    value=True,
                    id="f-cascade",
                )
            with Horizontal(classes="modal-buttons"):
                yield Button("Annuler", id="btn-cancel")
                yield Button("Supprimer", variant="error", id="btn-confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-confirm":
            cascade = False
            if self.linked_count:
                cascade = self.query_one("#f-cascade", Checkbox).value
            self.dismiss(cascade)

    def action_cancel(self) -> None:
        self.dismiss(None)


class TaskDetailModal(ModalScreen[Optional[str]]):
    """Détail d'une occurrence de tâche : infos affichées de façon simple et
    compacte (nom, statut, date/heure/détail, note), plus deux blocs modifiables
    en direct — Note (Input) et Récurrence (Select + jour de semaine si
    hebdomadaire) — et un bouton Fait/Pas fait à bascule (clic = change
    d'état, le texte du bouton change en conséquence — même principe que le
    bouton JOUR/SEMAINE du bandeau). Retourne "delete", ou None (fermeture
    simple).

    Design volontairement plat : un seul cadre visible (celui de la modale,
    voir .modal-box.-detail dans theme.tcss) — les champs internes (Input,
    Select) sont tous stylés sans bordure propre pour éviter l'effet "boîtes
    dans la boîte".

    La modale appelle task_service directement pour la note, le bouton
    Fait/Pas fait et la récurrence (mutations unitaires, auto-contenues,
    liées à l'édition en direct des champs) plutôt que de les faire remonter
    par dismiss() ; seule "delete" reste décidée par tui/app.py comme pour
    les autres modaux (portée plus large : DeleteScopeModal, rafraîchissement,
    notifications).

    Round 18 : une ligne supplémentaire, discrète (couleur atténuée,
    `.detail-line.-muted`), indique la provenance de la tâche juste sous la
    ligne date/heure/détails existante — "None" si créée à la main
    (`occ.auction_id` absent), "Auction <code pays> <jour>/<mois>" si générée
    automatiquement depuis une adjudication (même étiquette compacte que le
    filtre "par adjudication" de la vue Tâches, tui/app.py — voir
    auction_service.format_auction_short_label). N'ajoute qu'une ligne, ne
    touche à rien d'autre dans le layout existant."""

    BINDINGS = [("escape", "close", "Fermer")]

    def __init__(self, occurrence) -> None:
        super().__init__()
        self.occurrence = occurrence
        # Nommé _task_obj (et pas "task") : Screen/MessagePump définit déjà
        # une propriété `task` (l'asyncio.Task qui fait tourner l'écran) —
        # se réapproprier ce nom écraserait une propriété sans setter et
        # lèverait une AttributeError à l'assignation.
        self._task_obj = task_service.get_task(occurrence.task_id)
        self._done = occurrence.status == STATUS_DONE

    def compose(self) -> ComposeResult:
        occ = self.occurrence
        status_style = STATUS_COLORS.get(occ.status, STATUS_COLORS[STATUS_NEUTRAL])
        status_label = STATUS_LABELS.get(occ.status, occ.status)
        year, month, day = occ.date.split("-")
        date_label = f"{day}/{month}/{year}"

        recurrence = self._task_obj.recurrence if self._task_obj else RECURRENCE_ONCE
        weekday_default = occ.dt.weekday()
        if self._task_obj and self._task_obj.recurrence_weekday is not None:
            weekday_default = self._task_obj.recurrence_weekday

        with Vertical(classes="modal-box -detail"):
            yield Static(f"« {occ.name} »", classes="modal-title")
            yield Static(Text(status_label, style=status_style), classes="detail-line", id="f-status")
            yield Static(f"{date_label}  ·  {occ.time or '-'}  ·  {format_details(occ)}", classes="detail-line")
            yield Static(self._provenance_label(), classes="detail-line -muted", id="f-provenance")

            yield Static("Note", classes="field-label")
            yield Input(value=occ.note or "", placeholder="—", id="f-note")

            yield Static("Récurrence", classes="field-label")
            with Horizontal(classes="detail-recurrence"):
                yield Select(
                    [(RECURRENCE_LABELS[r], r) for r in RECURRENCE_TYPES],
                    value=recurrence,
                    allow_blank=False,
                    id="f-recurrence",
                )
                yield Select(
                    [(w, i) for i, w in enumerate(WEEKDAY_LABELS)],
                    value=weekday_default,
                    allow_blank=False,
                    id="f-weekday",
                )
            yield Button("Retirer la récurrence", classes="-link-btn", id="btn-remove-recurrence")

            with Horizontal(classes="modal-buttons -compact"):
                yield Button(self._done_label(), id="btn-toggle-done")
                yield Button("Fermer", id="btn-close")
                yield Button("Suppr.", classes="-delete-btn", id="btn-delete")

    def on_mount(self) -> None:
        self._sync_recurrence_fields()
        self._sync_done_button()
        self.query_one("#f-note", Input).focus()

    # ------------------------------------------------------------------
    # Provenance — round 18 : "None" (créée à la main) ou "Auction <code>
    # <jour>/<mois>" (générée depuis une adjudication). Calculée une fois à
    # l'ouverture, jamais modifiée en direct (pas de widget interactif, pure
    # information).
    # ------------------------------------------------------------------

    def _provenance_label(self) -> str:
        auction_id = self.occurrence.auction_id
        if not auction_id:
            return "None"
        auction = auction_service.get_auction(auction_id)
        if auction is None:
            # Lien cassé (adjudication supprimée sans cascade sur cette
            # tâche) : cas limite, pas de crash, juste un libellé honnête.
            return "Auction (supprimée)"
        return f"Auction {auction_service.format_auction_short_label(auction)}"

    # ------------------------------------------------------------------
    # Note — édition en direct (inchangé par rapport aux rounds précédents).
    # ------------------------------------------------------------------

    def _save_note_if_changed(self) -> None:
        value = self.query_one("#f-note", Input).value.strip()
        if value != (self.occurrence.note or ""):
            task_service.update_task(self.occurrence.task_id, note=value or None)
            self.occurrence.note = value or None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save_note_if_changed()

    # ------------------------------------------------------------------
    # Fait / Pas fait — bouton à bascule (pas de widget Switch : un clic
    # change l'état et le texte du bouton, comme le bouton JOUR/SEMAINE du
    # bandeau), mutation immédiate (mark_done / mark_undone).
    # ------------------------------------------------------------------

    def _done_label(self) -> str:
        return "Fait" if self._done else "Pas fait"

    def _sync_done_button(self) -> None:
        btn = self.query_one("#btn-toggle-done", Button)
        btn.label = self._done_label()
        btn.set_class(self._done, "-done-btn")

    def _toggle_done(self) -> None:
        occ = self.occurrence
        occ_date = task_service.parse_date(occ.date)
        self._done = not self._done
        if self._done:
            task_service.mark_done(occ.task_id, occ_date)
        else:
            task_service.mark_undone(occ.task_id, occ_date)
        occ.status = task_service.compute_status(occ.dt, done=self._done, has_time=occ.has_time)
        status_style = STATUS_COLORS.get(occ.status, STATUS_COLORS[STATUS_NEUTRAL])
        status_label = STATUS_LABELS.get(occ.status, occ.status)
        self.query_one("#f-status", Static).update(Text(status_label, style=status_style))
        self._sync_done_button()

    # ------------------------------------------------------------------
    # Récurrence — Select (type) + Select (jour, si hebdomadaire) + bouton
    # "Retirer" (repasse la tâche en "une fois", pinnée sur la date de
    # l'occurrence affichée). Mutation immédiate à chaque changement, comme
    # la Note — pas de bouton "valider" séparé pour rester simple.
    # ------------------------------------------------------------------

    def _sync_recurrence_fields(self) -> None:
        recurrence = self.query_one("#f-recurrence", Select).value
        self.query_one("#f-weekday", Select).display = recurrence == RECURRENCE_WEEKLY
        self.query_one("#btn-remove-recurrence", Button).display = recurrence != RECURRENCE_ONCE

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "f-recurrence":
            self._apply_recurrence(event.value)
            self._sync_recurrence_fields()
        elif event.select.id == "f-weekday":
            if self.query_one("#f-recurrence", Select).value == RECURRENCE_WEEKLY:
                self._apply_recurrence(RECURRENCE_WEEKLY, weekday=event.value)

    def _apply_recurrence(self, recurrence: str, weekday: Optional[int] = None) -> None:
        occ = self.occurrence
        recurrence_date = None
        recurrence_weekday = None
        if recurrence == RECURRENCE_ONCE:
            recurrence_date = occ.date
        elif recurrence == RECURRENCE_WEEKLY:
            if weekday is None:
                weekday = self.query_one("#f-weekday", Select).value
            recurrence_weekday = weekday
        self._task_obj = task_service.update_task(
            occ.task_id,
            recurrence=recurrence,
            recurrence_date=recurrence_date,
            recurrence_weekday=recurrence_weekday,
        )
        occ.is_recurring = recurrence != RECURRENCE_ONCE

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-remove-recurrence":
            self.query_one("#f-recurrence", Select).value = RECURRENCE_ONCE
            return
        if event.button.id == "btn-toggle-done":
            self._toggle_done()
            return
        self._save_note_if_changed()
        if event.button.id == "btn-close":
            self.dismiss(None)
        elif event.button.id == "btn-delete":
            self.dismiss("delete")

    def action_close(self) -> None:
        self._save_note_if_changed()
        self.dismiss(None)
