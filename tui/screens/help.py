"""
tui/screens/help.py — F1 : légende des couleurs + rappel des raccourcis
(section 5.2 du blueprint).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class HelpModal(ModalScreen[None]):
    BINDINGS = [("escape", "close", "Fermer")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Static("AIDE — LÉGENDE & RACCOURCIS", classes="modal-title")
            yield Static(
                "Couleurs\n"
                "  ● Rouge : à ≤30 min de l'heure prévue ou en retard, pas fait\n"
                "  ● Vert  : fait\n"
                "  ○ Blanc : prévu, pas encore urgent\n\n"
                "Raccourcis\n"
                "  F1 Aide      F2 Tâches      F3 Adjudications  F7 Log\n"
                "  F4 Ajouter   F5 Fait        F6 Supprimer      F9 Quitter\n"
                "  F10 Test notif (envoie une notification de test immédiate)\n"
                "  Tab          bascule le navigateur Jour / Semaine (bandeau, en haut à droite)\n"
                "  ◂ / ▸        (flèches, ou PgUp/PgDn) jour ou semaine précédent(e) / suivant(e)\n"
                "               — s'applique aux Tâches ET aux Adjudications (vue globale)\n"
                "  /            focus la barre de commande (TODAY, TOMORROW, WEEK, NOTIF TEST, ...)\n"
                "  Entrée       actions rapides sur la ligne sélectionnée\n"
                "  Esc          ferme / annule\n\n"
                "Notifications (page Log — F7)\n"
                "  Liste les notifications reçues aujourd'hui (tâches urgentes, récapitulatifs\n"
                "  8h45/15h00, tests) — surveillance intégrée à l'app, plus de process séparé.\n"
                "  F10, ou commande « NOTIF TEST » : envoie une notification de test immédiate.\n\n"
                "Souris (bandeau, en haut à droite)\n"
                "  clic sur JOUR/SEMAINE   bascule le mode\n"
                "  clic sur ◂ / ▸          jour/semaine précédent(e) / suivant(e)\n"
                "  clic sur la date        revient à aujourd'hui\n"
                "  case ☐ Tout             affiche toute la liste (Tâches ou Adjudications),\n"
                "                          sans filtre de date — indépendante par vue\n\n"
                "Bandeau latéral (vue Tâches)\n"
                "  Filtre adju.            limite la liste aux tâches liées à l'adjudication\n"
                "                          choisie (adjudications à venir uniquement) —\n"
                "                          repasser sur « Toutes » pour retirer le filtre"
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Fermer", variant="primary", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
