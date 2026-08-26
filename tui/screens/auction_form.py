"""
tui/screens/auction_form.py — formulaire modal d'ajout/édition d'adjudication
(F4 en vue Adjudications, ou commande "AUCTION ADD"). Pays et date sont les
seuls champs obligatoires (marqués d'un *), le reste est groupé en dessous
(section 5.4 du blueprint). Validation inline pour l'heure, la maturité et le
volume.

Mode ajout (auction=None) : propose aussi la création en série hebdomadaire.
Mode édition (auction=<Auction>) : champs pré-remplis, propose de régénérer
les tâches liées plutôt que la récurrence hebdomadaire.

Retourne (via dismiss) soit None (annulé), soit un dict de champs prêt à être
passé à auction_service.add_auction(...) / update_auction(...), avec en plus
les clés internes "_weekly_count" et "_regenerate" que l'app extrait avant
l'appel au service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Select, Static

import auction_service
import task_service
from models import Auction


class AuctionFormModal(ModalScreen[Optional[dict]]):
    BINDINGS = [("escape", "cancel", "Annuler")]

    def __init__(self, auction: Optional[Auction] = None) -> None:
        super().__init__()
        self.auction = auction

    def compose(self) -> ComposeResult:
        a = self.auction
        countries = auction_service.get_countries()
        title = "MODIFIER L'ADJUDICATION" if a else "AJOUTER UNE ADJUDICATION"
        with Vertical(classes="modal-box"):
            yield Static(title, classes="modal-title")

            yield Static("Pays *", classes="field-label")
            # Toujours une vraie valeur par défaut (jamais de sélection vide) :
            # un champ obligatoire laissé sur un "prompt" vide est le genre de
            # piège qui fait qu'un Entrée un peu rapide ne valide rien.
            yield Select(
                [(c, c) for c in countries],
                value=(a.country if a else countries[0]),
                allow_blank=False,
                id="f-country",
            )

            yield Static("Date * (YYYY-MM-DD)", classes="field-label")
            yield Input(value=(a.date if a else datetime.now().strftime("%Y-%m-%d")), id="f-date")

            yield Static("Heure (HH:MM)", classes="field-label")
            yield Input(value=(a.time or "" if a else ""), placeholder="10:50", id="f-time")

            yield Static("Type", classes="field-label")
            yield Select(
                [(t, t) for t in auction_service.get_auction_types()],
                value=(a.type if a and a.type else Select.NULL),
                id="f-type",
            )

            yield Static("Instrument", classes="field-label")
            yield Input(value=(a.instrument or "" if a else ""), id="f-instrument")

            yield Static("Maturité (YYYY-MM-DD)", classes="field-label")
            yield Input(value=(a.maturity or "" if a else ""), id="f-maturity")

            yield Static("Volume (millions)", classes="field-label")
            yield Input(
                value=(f"{a.volume:g}" if a and a.volume is not None else ""),
                id="f-volume",
            )

            yield Static("NCO", classes="field-label")
            yield Select(
                [("Oui", True), ("Non", False)],
                value=(a.nco if a and a.nco is not None else Select.NULL),
                id="f-nco",
            )

            if a is None:
                yield Static("Occurrences hebdomadaires (1 = pas de récurrence)", classes="field-label")
                yield Input(value="1", id="f-weekly-count")
            else:
                yield Checkbox("Régénérer les tâches liées", id="f-regenerate")

            yield Static("Note", classes="field-label")
            yield Input(value=(a.note or "" if a else ""), placeholder="optionnel", id="f-note")

            yield Static("", classes="field-error", id="f-error")

            with Horizontal(classes="modal-buttons"):
                yield Button("Annuler", id="btn-cancel")
                yield Button("Valider", variant="primary", id="btn-submit")

    def on_mount(self) -> None:
        self.query_one("#f-country", Select).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "f-time":
            self._validate_optional(event.input, task_service.is_valid_time, event.value)
        elif event.input.id == "f-maturity":
            self._validate_optional(event.input, task_service.is_valid_date, event.value)
        elif event.input.id == "f-volume":
            self._validate_optional(event.input, _is_valid_float, event.value)
        elif event.input.id == "f-date":
            self._validate_required(event.input, task_service.is_valid_date, event.value)

    def _validate_optional(self, widget: Input, validator, value: str) -> bool:
        if value == "":
            widget.remove_class("-invalid", "-valid")
            return True
        ok = validator(value)
        widget.set_class(not ok, "-invalid")
        widget.set_class(ok, "-valid")
        return ok

    def _validate_required(self, widget: Input, validator, value: str) -> bool:
        ok = value != "" and validator(value)
        widget.set_class(not ok, "-invalid")
        widget.set_class(ok, "-valid")
        return ok

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-submit":
            self._submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _submit(self) -> None:
        error = self.query_one("#f-error", Static)

        country = self.query_one("#f-country", Select).value
        date_value = self.query_one("#f-date", Input).value.strip()
        time_value = self.query_one("#f-time", Input).value.strip()
        type_value = self.query_one("#f-type", Select).value
        instrument = self.query_one("#f-instrument", Input).value.strip()
        maturity = self.query_one("#f-maturity", Input).value.strip()
        volume_raw = self.query_one("#f-volume", Input).value.strip()
        nco = self.query_one("#f-nco", Select).value
        note = self.query_one("#f-note", Input).value.strip() or None

        if not self._validate_required(self.query_one("#f-date", Input), task_service.is_valid_date, date_value):
            error.update("Date invalide : format attendu YYYY-MM-DD.")
            return
        if time_value and not task_service.is_valid_time(time_value):
            error.update("Heure invalide : format attendu HH:MM.")
            return
        if maturity and not task_service.is_valid_date(maturity):
            error.update("Date de maturité invalide : format attendu YYYY-MM-DD.")
            return
        if volume_raw and not _is_valid_float(volume_raw):
            error.update("Volume invalide : nombre attendu.")
            return

        fields: dict = {
            "country": country,
            "date": date_value,
            "time": time_value or None,
            "type": (type_value if type_value is not Select.NULL else None),
            "instrument": instrument or None,
            "maturity": maturity or None,
            "volume": (float(volume_raw.replace(",", ".")) if volume_raw else None),
            "nco": (nco if nco is not Select.NULL else None),
            "note": note,
        }

        if self.auction is None:
            raw_count = self.query_one("#f-weekly-count", Input).value.strip()
            try:
                count = int(raw_count) if raw_count else 1
            except ValueError:
                error.update("Nombre d'occurrences invalide.")
                return
            if count < 1:
                error.update("Le nombre d'occurrences doit être >= 1.")
                return
            fields["_weekly_count"] = count if count > 1 else None
        else:
            fields["_regenerate"] = self.query_one("#f-regenerate", Checkbox).value

        self.dismiss(fields)


def _is_valid_float(value: str) -> bool:
    try:
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False
