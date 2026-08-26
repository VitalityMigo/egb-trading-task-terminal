"""
storage.py — persistance JSON, partagée par cli.py et tui/app.py (et notify_daemon.py
pour le fichier de déduplication des notifications).

Écriture atomique (fichier temporaire + remplacement) pour éviter un JSON à moitié
écrit si l'app est fermée brutalement pendant une sauvegarde.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from constants import DATA_DIR


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    _ensure_data_dir()
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as fh:
            content = fh.read().strip()
            if not content:
                return default
            return json.loads(content)
    except (json.JSONDecodeError, OSError):
        # fichier corrompu ou illisible : on ne plante pas l'appli, on repart
        # d'un état vide plutôt que de perdre l'utilisation de l'outil.
        return default


def save_json(path: Path, data: Any) -> None:
    _ensure_data_dir()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)  # remplacement atomique sur Windows comme sur Linux
