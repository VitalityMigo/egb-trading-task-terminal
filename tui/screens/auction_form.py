"""
tui/screens/auction_form.py — formulaire modal d'ajout/édition d'adjudication
(F4 en vue Adjudications, ou commande "AUCTION ADD"). En mode ajout, seuls
Volume, NCO et Note sont optionnels — round 16, sur demande d'Augustin : Pays,
Date, Heure, Type et Maturité sont désormais tous obligatoires (marqués d'un
*) pour créer une adjudication.

Mode ajout (auction=None) : tous les champs sont éditables. Round 19, sur
demande d'Augustin : le champ de création en série hebdomadaire a été retiré
(une seule adjudication à la fois, plus de "_weekly_count").

Mode édition (auction=<Auction>, ouvert au clic/Entrée sur une ligne
existante) — round 15, sur demande d'Augustin : Pays, Date, Type et Volume ne
sont plus modifiables a posteriori et sont présentés en lecture seule, même
principe que TaskDetailModal (tui/screens/confirm.py) — titre `« Pays »` +
une ligne d'info compacte (date · type · volume) au lieu de champs Select/
Input. Seuls Heure, Maturité, NCO et Note restent éditables en direct (et y
restent optionnels : la contrainte "obligatoire" du round 16 ne s'applique
qu'à la création, pas à l'édition). Ces quatre champs "verrouillés" ne sont
simplement pas envoyés dans le dict de soumission : auction_service.update_auction
garde alors leur valeur actuelle (fields.get(clé, valeur_existante)), donc
rien à recopier ici.

Retourne (via dismiss) soit None (annulé), soit "delete" (round 16 — bouton
Suppr. en mode édition, décidé par tui/app.py comme pour TaskDetailModal),
soit un dict de champs prêt à être passé directement à
auction_service.add_auction(...) / update_auction(...).

Style plat, même famille que TaskDetailModal/TaskFormModal (classe
.modal-box.-form-wide dans theme.tcss) : un seul cadre visible, champs sans
bordure propre, boutons compacts sans gros bloc de couleur. Le bouton
"Vérifier les tâches liées" (mode édition uniquement) vit dans la même ligne
que Annuler/Valider/Suppr., callé à gauche du cadre (classe -split) — round
15, remplace l'ancienne case "Régénérer les tâches liées" (supprimée : le
bouton Vérifier fait tout en un, en ne touchant jamais aux tâches déjà
présentes, contrairement à Régénérer qui supprimait puis recréait tout). Le
bouton "Suppr." (round 16, mode édition uniquement) réutilise la classe
-delete-btn déjà définie pour TaskDetailModal (theme.tcss) — même rouge, pas
de CSS supplémentaire nécessaire.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

import auction_service
import task_service
from models import Auction


class AuctionFormModal(ModalScreen[Optional[Union[dict, str]]]):
    BINDINGS = [("escape", "cancel", "Annuler")]

    def __init__(self, auction: Optional[Auction] = None) -> None:
        super().__init__()
        self.auction = auction

    def compose(self) -> ComposeResult:
        a = self.auction
        countries = auction_service.get_countries()

        with Vertical(classes="modal-box -form-wide"):
            if a is None:
                yield Static("AJOUTER UNE ADJUDICATION", classes="modal-title")
            else:
                # Présentation en lecture seule des 4 champs verrouillés,
                # même principe que le titre + la ligne d'info de
                # TaskDetailModal (« nom » puis date · heure · détails).
                yield Static(f"« {a.country} »", classes="modal-title")
                year, month, day = a.date.split("-")
                date_label = f"{day}/{month}/{year}"
                volume_label = f"{a.volume:g} M" if a.volume is not None else "—"
                yield Static(f"{date_label}  ·  {a.type or '—'}  ·  {volume_label}", classes="detail-line")

            if a is None:
                # Toujours une vraie valeur par défaut (jamais de sélection
                # vide) : un champ obligatoire laissé sur un "prompt" vide
                # est le genre de piège qui fait qu'un Entrée un peu rapide
                # ne valide rien.
                yield Static("Pays *", classes="field-label")
                yield Select([(c, c) for c in countries], value=countries[0], allow_blank=False, id="f-country")

                yield Static("Date * (YYYY-MM-DD)", classes="field-label")
                yield Input(value=datetime.now().strftime("%Y-%m-%d"), id="f-date")

            yield Static("Heure (HH:MM)" + (" *" if a is None else ""), classes="field-label")
            yield Input(value=(a.time or "" if a else ""), placeholder="10:50", id="f-time")

            if a is None:
                # Même logique que Pays : une vraie valeur par défaut plutôt
                # qu'un Select.NULL, pour que le champ obligatoire ne puisse
                # pas rester "vide" par inadvertance (voir commentaire Pays
                # plus haut).
                auction_types = auction_service.get_auction_types()
                yield Static("Type *", classes="field-label")
                yield Select(
                    [(t, t) for t in auction_types],
                    value=auction_types[0],
                    allow_blank=False,
                    id="f-type",
                )

            yield Static("Maturité (YYYY-MM-DD)" + (" *" if a is None else ""), classes="field-label")
            yield Input(value=(a.maturity or "" if a else ""), id="f-maturity")

            if a is None:
                yield Static("Volume (millions)", classes="field-label")
                yield Input(value="", id="f-volume")

            yield Static("NCO", classes="field-label")
            yield Select(
                [("Oui", True), ("Non", False)],
                value=(a.nco if a and a.nco is not None else Select.NULL),
                id="f-nco",
            )

            yield Static("Note", classes="field-label")
            yield Input(value=(a.note or "" if a else ""), placeholder="optionnel", id="f-note")

            yield Static("", classes="field-error", id="f-error")

            with Horizontal(classes="modal-buttons -compact -split"):
                if a is not None:
                    yield Button("Vérifier les tâches liées", id="btn-ensure-tasks")
                yield Static(classes="-spacer")
                yield Button("Annuler", id="btn-cancel")
                yield Button("Valider", classes="-primary-btn", id="btn-submit")
                if a is not None:
                    yield Button("Suppr.", classes="-delete-btn", id="btn-delete")

    def on_mount(self) -> None:
        if self.auction is None:
            self.query_one("#f-country", Select).focus()
        else:
            self.query_one("#f-time", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        add_mode = self.auction is None
        if event.input.id == "f-time":
            if add_mode:
                self._validate_required(event.input, task_service.is_valid_time, event.value)
            else:
                self._validate_optional(event.input, task_service.is_valid_time, event.value)
        elif event.input.id == "f-maturity":
            if add_mode:
                self._validate_required(event.input, task_service.is_valid_date, event.value)
            else:
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
        elif event.button.id == "btn-ensure-tasks":
            self._ensure_tasks()
        elif event.button.id == "btn-delete":
            self.dismiss("delete")

    def action_cancel(self) -> None:
        self.dismiss(None)

    # ------------------------------------------------------------------
    # Vérifier / créer les tâches liées manquantes — mutation immédiate,
    # indépendante de la validation du formulaire (comme le bouton Fait/Pas
    # fait de TaskDetailModal), la modale reste ouverte.
    # ------------------------------------------------------------------

    def _ensure_tasks(self) -> None:
        if self.auction is None:
            return
        created, warnings = auction_service.ensure_tasks_for_auction(self.auction)
        if created:
            names = ", ".join(f"« {t.name} »" for t in created)
            self.notify(f"{len(created)} tâche(s) créée(s) : {names}.")
        else:
            self.notify("Toutes les tâches liées étaient déjà présentes.")
        for w in warnings:
            self.notify(w, severity="warning")

    def _submit(self) -> None:
        error = self.query_one("#f-error", Static)
        a = self.auction

        time_value = self.query_one("#f-time", Input).value.strip()
        maturity = self.query_one("#f-maturity", Input).value.strip()
        nco = self.query_one("#f-nco", Select).value
        note = self.query_one("#f-note", Input).value.strip() or None

        if a is None:
            # Round 16 : Heure et Maturité deviennent obligatoires à la
            # création (seuls Volume/NCO/Note restent optionnels).
            if not self._validate_required(self.query_one("#f-time", Input), task_service.is_valid_time, time_value):
                error.update("Heure invalide ou manquante : format attendu HH:MM.")
                return
            if not self._validate_required(self.query_one("#f-maturity", Input), task_service.is_valid_date, maturity):
                error.update("Date de maturité invalide ou manquante : format attendu YYYY-MM-DD.")
                return
        else:
            if time_value and not task_service.is_valid_time(time_value):
                error.update("Heure invalide : format attendu HH:MM.")
                return
            if maturity and not task_service.is_valid_date(maturity):
                error.update("Date de maturité invalide : format attendu YYYY-MM-DD.")
                return

        # Pays/Date/Type/Volume : absents du dict en mode édition (verrouillés,
        # pas de widget à lire) -> auction_service.update_auction garde
        # automatiquement la valeur actuelle (fields.get(clé, valeur existante)).
        fields: dict = {
            "time": time_value or None,
            "maturity": maturity or None,
            "nco": (nco if nco is not Select.NULL else None),
            "note": note,
        }

        if a is None:
            country = self.query_one("#f-country", Select).value
            date_value = self.query_one("#f-date", Input).value.strip()
            type_value = self.query_one("#f-type", Select).value
            volume_raw = self.query_one("#f-volume", Input).value.strip()

            if not self._validate_required(self.query_one("#f-date", Input), task_service.is_valid_date, date_value):
                error.update("Date invalide : format attendu YYYY-MM-DD.")
                return
            if volume_raw and not _is_valid_float(volume_raw):
                error.update("Volume invalide : nombre attendu.")
                return

            fields["country"] = country
            fields["date"] = date_value
            fields["type"] = type_value if type_value is not Select.NULL else None
            fields["volume"] = float(volume_raw.replace(",", ".")) if volume_raw else None

        self.dismiss(fields)


def _is_valid_float(value: str) -> bool:
    try:
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False
