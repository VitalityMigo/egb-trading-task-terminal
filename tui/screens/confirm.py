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
from textual.widgets import Button, Checkbox, Input, Static

import task_service
from constants import STATUS_NEUTRAL
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
    compacte, Note directement éditable (Input pré-rempli). Retourne "done",
    "delete", ou None (fermeture simple — la note, elle, est déjà enregistrée
    à ce moment-là si elle a été modifiée, voir _save_note_if_changed).

    La modale appelle task_service directement pour la note (mutation unique
    et auto-contenue, liée à l'édition en direct dans le champ) plutôt que de
    la faire remonter par dismiss() ; les actions "done"/"delete", elles,
    restent décidées par tui/app.py comme pour les autres modaux (portée plus
    large : gestion de la récurrence, rafraîchissement, notifications)."""

    BINDINGS = [("escape", "close", "Fermer")]

    def __init__(self, occurrence) -> None:
        super().__init__()
        self.occurrence = occurrence

    def compose(self) -> ComposeResult:
        occ = self.occurrence
        status_style = STATUS_COLORS.get(occ.status, STATUS_COLORS[STATUS_NEUTRAL])
        status_label = STATUS_LABELS.get(occ.status, occ.status)
        with Vertical(classes="modal-box -detail"):
            yield Static(f"« {occ.name} »", classes="modal-title")
            yield Static(f"{occ.time}  ·  {format_details(occ)}", classes="detail-line")
            yield Static(Text(status_label, style=status_style), classes="detail-line")
            yield Static("Note", classes="field-label")
            yield Input(value=occ.note or "", placeholder="—", id="f-note")
            with Horizontal(classes="modal-buttons -compact"):
                yield Button("Fermer", id="btn-close")
                yield Button("Fait", classes="-done-btn", id="btn-done")
                yield Button("Suppr.", classes="-delete-btn", id="btn-delete")

    def on_mount(self) -> None:
        self.query_one("#f-note", Input).focus()

    def _save_note_if_changed(self) -> None:
        value = self.query_one("#f-note", Input).value.strip()
        if value != (self.occurrence.note or ""):
            task_service.update_task(self.occurrence.task_id, note=value or None)
            self.occurrence.note = value or None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save_note_if_changed()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._save_note_if_changed()
        if event.button.id == "btn-close":
            self.dismiss(None)
        elif event.button.id == "btn-done":
            self.dismiss("done")
        elif event.button.id == "btn-delete":
            self.dismiss("delete")

    def action_close(self) -> None:
        self._save_note_if_changed()
        self.dismiss(None)
