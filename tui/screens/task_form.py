"""
tui/screens/task_form.py — formulaire modal d'ajout de tâche (F4 en vue Tâches,
ou commande "TASK ADD"). Validation inline de l'heure (HH:MM) avant même la
soumission : bordure rouge dès que la saisie est invalide (section 5.4 du
blueprint) — pas seulement après appui sur Entrée.

Retourne (via dismiss) soit None (annulé), soit un dict prêt à être passé en
kwargs à task_service.add_task(...).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

import task_service
from constants import RECURRENCE_LABELS, RECURRENCE_ONCE, RECURRENCE_TYPES, RECURRENCE_WEEKLY, WEEKDAY_LABELS


class TaskFormModal(ModalScreen[Optional[dict]]):
    BINDINGS = [("escape", "cancel", "Annuler")]

    def compose(self) -> ComposeResult:
        catalog = task_service.get_catalog()
        with Vertical(classes="modal-box"):
            yield Static("AJOUTER UNE TÂCHE", classes="modal-title")

            yield Static("Nom *", classes="field-label")
            # Pas de "prompt" vide : un premier nom est pré-sélectionné pour
            # qu'une validation trop rapide (Entrée, Entrée) ne puisse jamais
            # rester bloquée sur une sélection vide.
            yield Select(
                [(n, n) for n in catalog],
                value=catalog[0],
                allow_blank=False,
                id="f-name",
            )

            yield Static("Récurrence *", classes="field-label")
            yield Select(
                [(RECURRENCE_LABELS[r], r) for r in RECURRENCE_TYPES],
                value=RECURRENCE_ONCE,
                allow_blank=False,
                id="f-recurrence",
            )

            yield Static("Date (YYYY-MM-DD) *", classes="field-label", id="f-date-label")
            yield Input(value=datetime.now().strftime("%Y-%m-%d"), id="f-date")

            yield Static("Jour de la semaine *", classes="field-label", id="f-weekday-label")
            yield Select([(w, i) for i, w in enumerate(WEEKDAY_LABELS)], value=0, allow_blank=False, id="f-weekday")

            yield Static("Heure * (HH:MM)", classes="field-label")
            yield Input(placeholder="16:30", id="f-time")

            yield Static("Note", classes="field-label")
            yield Input(placeholder="optionnel", id="f-note")

            yield Static("", classes="field-error", id="f-error")

            with Horizontal(classes="modal-buttons"):
                yield Button("Annuler", id="btn-cancel")
                yield Button("Valider", variant="primary", id="btn-submit")

    def on_mount(self) -> None:
        self._sync_recurrence_fields()
        self.query_one("#f-name", Select).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "f-recurrence":
            self._sync_recurrence_fields()

    def _sync_recurrence_fields(self) -> None:
        recurrence = self.query_one("#f-recurrence", Select).value
        show_date = recurrence == RECURRENCE_ONCE
        show_weekday = recurrence == RECURRENCE_WEEKLY
        self.query_one("#f-date-label").display = show_date
        self.query_one("#f-date", Input).display = show_date
        self.query_one("#f-weekday-label").display = show_weekday
        self.query_one("#f-weekday", Select).display = show_weekday

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "f-time":
            self._validate_time(event.value, show_error=False)

    def _validate_time(self, value: str, show_error: bool = True) -> bool:
        time_input = self.query_one("#f-time", Input)
        error = self.query_one("#f-error", Static)
        if value == "":
            time_input.remove_class("-invalid", "-valid")
            if show_error:
                error.update("L'heure est obligatoire.")
            return False
        if task_service.is_valid_time(value):
            time_input.remove_class("-invalid")
            time_input.add_class("-valid")
            error.update("")
            return True
        time_input.remove_class("-valid")
        time_input.add_class("-invalid")
        error.update("Heure invalide : format attendu HH:MM (ex. 16:30).")
        return False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-submit":
            self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        error = self.query_one("#f-error", Static)
        name = self.query_one("#f-name", Select).value
        recurrence = self.query_one("#f-recurrence", Select).value
        time_value = self.query_one("#f-time", Input).value.strip()
        note = self.query_one("#f-note", Input).value.strip() or None

        if not self._validate_time(time_value):
            return

        recurrence_date = None
        recurrence_weekday = None
        if recurrence == RECURRENCE_ONCE:
            recurrence_date = self.query_one("#f-date", Input).value.strip()
            if not task_service.is_valid_date(recurrence_date):
                error.update("Date invalide : format attendu YYYY-MM-DD.")
                return
        elif recurrence == RECURRENCE_WEEKLY:
            recurrence_weekday = self.query_one("#f-weekday", Select).value

        self.dismiss({
            "name": name,
            "time": time_value,
            "recurrence": recurrence,
            "recurrence_date": recurrence_date,
            "recurrence_weekday": recurrence_weekday,
            "note": note,
        })
