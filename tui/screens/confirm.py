"""
tui/screens/confirm.py — petits modaux de confirmation / choix rapide :
- DeleteScopeModal : occurrence du jour vs. toute la série (tâche récurrente).
- DeleteAuctionModal : suppression d'une adjudication, cascade optionnelle sur
  les tâches liées (case à cocher dans la même modale, section 5.5).
- RowActionModal : actions rapides sur la ligne sélectionnée (touche Entrée
  dans le DataTable, vue Tâches) — amélioration UX par rapport à la v1.
"""

from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Static


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


class RowActionModal(ModalScreen[Optional[str]]):
    """Actions rapides sur une occurrence de tâche : "done", "delete", ou None."""

    BINDINGS = [("escape", "cancel", "Annuler")]

    def __init__(self, task_name: str) -> None:
        super().__init__()
        self.task_name = task_name

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Static(f"« {self.task_name} »", classes="modal-title")
            with Horizontal(classes="modal-buttons"):
                yield Button("Annuler", id="btn-cancel")
                yield Button("Marquer fait (F5)", variant="primary", id="btn-done")
                yield Button("Supprimer (F6)", variant="error", id="btn-delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-done":
            self.dismiss("done")
        elif event.button.id == "btn-delete":
            self.dismiss("delete")

    def action_cancel(self) -> None:
        self.dismiss(None)
