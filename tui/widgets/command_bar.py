"""
tui/widgets/command_bar.py — barre de commande façon <GO> Bloomberg (section 5.3
du blueprint). Ce widget ne fait qu'afficher le prompt "> " et un champ de
saisie : le parsing et l'exécution des commandes (TASK ADD, AUCTION LIST,
WEEK, ...) sont gérés par l'app (tui/app.py), qui seule a accès aux données
actuellement affichées à l'écran (nécessaire pour "TASK DONE 3" par exemple).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Input, Static


class CommandBar(Horizontal):
    class Submitted(Message):
        def __init__(self, command: str) -> None:
            self.command = command
            super().__init__()

    def compose(self) -> ComposeResult:
        yield Static("> ", id="cmd-prompt")
        yield Input(
            placeholder="TASK ADD · TASK DONE 3 · AUCTION LIST · WEEK · TODAY · TOMORROW · NOTIF TEST",
            id="cmd-input",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        command = event.value.strip()
        event.input.value = ""
        if command:
            self.post_message(self.Submitted(command))

    def focus_input(self) -> None:
        self.query_one("#cmd-input", Input).focus()

    def clear(self) -> None:
        self.query_one("#cmd-input", Input).value = ""
