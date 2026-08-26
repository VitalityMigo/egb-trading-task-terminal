"""
tui/widgets/header_bar.py — bandeau supérieur : marque, date, horloge vivante,
compteurs "urgentes / faites" et navigateur jour/semaine (sections 4.3 et 5.1
du blueprint, redesign navigateur demandé ensuite).

Layout (une seule ligne, height: 3, centrée verticalement) :
  gauche  : marque + date + horloge + compteurs urgent/fait (position
            d'origine, avant l'ajout du navigateur) ;
  droite  : case "Tout" + navigateur (mode JOUR/SEMAINE, flèches ◂ ▸,
            libellé du jour ou de la semaine affichée), repoussé à l'extrême
            droite maintenant qu'il ne partage plus l'espace avec les
            compteurs.
Le contenu s'adapte à la largeur du terminal (render() est appelé à chaque
resize par Textual) : au-delà d'un certain seuil on abrège ou on masque des
éléments plutôt que de laisser le texte déborder.

Le navigateur est aussi utilisable à la souris : chaque segment cliquable
(case "Tout", libellé de mode, flèches, libellé de date) porte un style Rich
avec `meta={"@click": "app.<action>"}` — Textual reconnaît nativement ce
mécanisme (c'est ce qui rend les touches du Footer cliquables) et déclenche
l'action correspondante sur l'App au clic, sans code de gestion d'événement
supplémentaire ici.

Toute la définition de "semaine" (lundi -> dimanche) vient de
task_service.week_range — ce widget ne fait que formater, il ne recalcule
aucune règle métier.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

import task_service

_WEEKDAY_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_WEEKDAY_ABBR = ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"]
_MONTH_FR = [
    "", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

# Doit rester synchronisé avec tui/theme.tcss.
_FG_PRIMARY = "#FFB000"
_FG_HEADER = "#00C8FF"
_FG_URGENT = "#FF3B3B"
_FG_DONE = "#00D26A"
_FG_MUTED = "#5C5C5C"


def _clickable(color: str, action: str, bold: bool = False) -> Style:
    return Style(color=color, bold=bold or None) + Style(meta={"@click": action})


class HeaderBar(Static):
    urgent_count: reactive[int] = reactive(0)
    done_count: reactive[int] = reactive(0)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.nav_mode = "day"          # "day" | "week"
        self.nav_anchor = date.today()
        self.show_all = False          # case "Tout" de la vue actuellement affichée

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)

    def set_counts(self, urgent: int, done: int) -> None:
        self.urgent_count = urgent
        self.done_count = done

    def set_nav(self, mode: str, anchor: date, show_all: bool = False) -> None:
        self.nav_mode = mode
        self.nav_anchor = anchor
        self.show_all = show_all
        self.refresh()

    # ------------------------------------------------------------------
    # Rendu adaptatif — appelé par Textual à chaque seconde (horloge) et à
    # chaque redimensionnement du terminal.
    # ------------------------------------------------------------------

    def render(self) -> Text:
        width = self.size.width or 80
        now = datetime.now()

        left = Text()
        left.append(" DESK CLI ", style=f"bold {_FG_PRIMARY}")
        if width >= 70:
            date_label = f"{_WEEKDAY_FR[now.weekday()]} {now.day:02d} {_MONTH_FR[now.month]} {now.year}"
            left.append("▸ ", style=_FG_MUTED)
            left.append(f"{date_label}  ", style=_FG_HEADER)
        left.append("▸ ", style=_FG_MUTED)
        left.append(now.strftime("%H:%M:%S"), style="bold")
        left.append("      ")
        if width < 60:
            left.append(f"{self.urgent_count}U", style=f"bold {_FG_URGENT}")
            left.append(" · ", style=_FG_MUTED)
            left.append(f"{self.done_count}F", style=f"bold {_FG_DONE}")
        else:
            left.append(f"{self.urgent_count} urgentes", style=f"bold {_FG_URGENT}")
            left.append("  ·  ", style=_FG_MUTED)
            left.append(f"{self.done_count} faites", style=f"bold {_FG_DONE}")

        right = self._format_nav(width)

        gap = max(1, width - left.cell_len - right.cell_len)
        out = Text()
        out.append_text(left)
        out.append(" " * gap)
        out.append_text(right)
        # Si tout ne tient toujours pas (terminal très étroit), on préfère
        # une coupe nette à droite plutôt qu'un retour à la ligne — sinon le
        # bandeau passe sur 2 lignes et écrase la première ligne du tableau.
        out.no_wrap = True
        out.overflow = "crop"
        return out

    def _format_nav(self, width: int) -> Text:
        """Bloc droit : case "Tout" + navigateur Jour/Semaine, entièrement
        cliquable à la souris (voir docstring du module)."""
        text = Text()

        box = "☑" if self.show_all else "☐"
        box_color = _FG_PRIMARY if self.show_all else _FG_MUTED
        box_style = _clickable(box_color, "app.toggle_show_all")
        text.append(box, style=box_style)
        if width >= 50:
            text.append(" Tout", style=box_style)
        text.append("   ")

        # Tant que "Tout" est coché, le navigateur ne pilote plus la table :
        # on l'assourdit pour que ce soit visuellement clair, sans le
        # désactiver (décocher doit retrouver exactement la même position).
        dim = self.show_all
        mode_color = _FG_MUTED if dim else _FG_HEADER
        label_color = _FG_MUTED if dim else _FG_PRIMARY
        arrow_color = _FG_MUTED

        mode_label, period_label = self._nav_labels(width)

        text.append(mode_label, style=_clickable(mode_color, "app.toggle_period"))
        text.append(" ")
        text.append("◂", style=_clickable(arrow_color, "app.prev_page"))
        text.append(f" {period_label} ", style=_clickable(label_color, "app.nav_reset_today"))
        text.append("▸", style=_clickable(arrow_color, "app.next_page"))
        return text

    def _nav_labels(self, width: int) -> tuple[str, str]:
        today = date.today()

        if self.nav_mode == "week":
            mode_label = "SEM" if width < 90 else "SEMAINE"
            monday, sunday = task_service.week_range(self.nav_anchor)
            this_monday, _ = task_service.week_range(today)
            if monday == this_monday:
                label = "CETTE SEMAINE"
            else:
                label = f"{monday.day:02d}/{monday.month:02d}–{sunday.day:02d}/{sunday.month:02d}"
        else:
            mode_label = "JOUR"
            if self.nav_anchor == today:
                label = "AUJOURD'HUI"
            elif self.nav_anchor == today + timedelta(days=1):
                label = "DEMAIN"
            elif self.nav_anchor == today - timedelta(days=1):
                label = "HIER"
            else:
                label = f"{_WEEKDAY_ABBR[self.nav_anchor.weekday()]} {self.nav_anchor.day:02d}/{self.nav_anchor.month:02d}"

        return mode_label, label
