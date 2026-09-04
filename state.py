"""Persistance légère (fichier JSON) des identifiants de logements déjà
notifiés, pour ne jamais renvoyer deux fois la même annonce et pour
survivre à un redémarrage du script."""
from __future__ import annotations

import json
from pathlib import Path


def load_seen(state_file: Path) -> set[str]:
    if not state_file.exists():
        return set()
    try:
        with state_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("seen_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(state_file: Path, seen_ids: set[str]) -> None:
    tmp_file = state_file.with_suffix(".tmp")
    with tmp_file.open("w", encoding="utf-8") as f:
        json.dump({"seen_ids": sorted(seen_ids)}, f, ensure_ascii=False, indent=2)
    tmp_file.replace(state_file)
