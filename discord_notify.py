"""
Envoi de messages vers un webhook Discord, avec :
- respect du rate-limit renvoyé par Discord (HTTP 429 + Retry-After)
- petites pauses entre les messages pour rester large sous la limite
  officielle (~30 requêtes/minute par webhook)
- retries limités en cas d'erreur réseau ponctuelle
"""
from __future__ import annotations

import logging
import time
from typing import Any, Iterable

import requests

logger = logging.getLogger("crous_monitor.discord")

MAX_EMBEDS_PER_MESSAGE = 10
DELAY_BETWEEN_MESSAGES = 1.2  # secondes, largement sous la limite Discord


def _post(webhook_url: str, payload: dict[str, Any], max_retries: int = 3) -> bool:
    if not webhook_url:
        logger.warning("Aucune URL de webhook configurée, message ignoré.")
        return False

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=15)
        except requests.RequestException as exc:
            logger.warning("Erreur réseau vers Discord (tentative %s/%s) : %s",
                            attempt, max_retries, exc)
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 429:
            retry_after = 1.0
            try:
                retry_after = float(resp.json().get("retry_after", 1.0))
            except Exception:
                pass
            logger.info("Rate-limit Discord atteint, pause %.1fs", retry_after)
            time.sleep(retry_after + 0.5)
            continue

        if 200 <= resp.status_code < 300:
            return True

        logger.warning("Discord a répondu %s: %s", resp.status_code, resp.text[:300])
        time.sleep(2 * attempt)

    return False


def send_startup_message(webhook_url: str, watcher_name: str, nb_logements_initiaux: int) -> None:
    payload = {
        "embeds": [
            {
                "title": f"🟢 Monitor démarré — {watcher_name}",
                "description": (
                    f"{nb_logements_initiaux} logement(s) déjà référencés au démarrage. @505424519268139008 "
                    "Seules les nouvelles annonces à partir de maintenant seront notifiées."
                ),
                "color": 0x2ECC71,
            }
        ]
    }
    _post(webhook_url, payload)


def send_error_message(webhook_url: str, watcher_name: str, message: str) -> None:
    payload = {
        "embeds": [
            {
                "title": f"⚠️ Erreur — {watcher_name}",
                "description": message[:3500],
                "color": 0xE74C3C,
            }
        ]
    }
    _post(webhook_url, payload)


def send_new_listings(webhook_url: str, watcher_name: str, listings: Iterable[dict]) -> None:
    """Envoie les nouvelles annonces sous forme d'embeds, en respectant la
    limite de 10 embeds par message Discord, avec une petite pause entre
    chaque envoi."""
    listings = list(listings)
    if not listings:
        return

    for i in range(0, len(listings), MAX_EMBEDS_PER_MESSAGE):
        chunk = listings[i : i + MAX_EMBEDS_PER_MESSAGE]
        embeds = []
        for item in chunk:
            embeds.append(
                {
                    "title": (item.get("title") or "Nouveau logement Crous")[:256],
                    "url": item.get("url"),
                    "description": (item.get("description") or "")[:400],
                    "color": 0x3498DB,
                    "footer": {"text": watcher_name},
                }
            )
        payload = {
            "content": f"🏠 {len(chunk)} nouveau(x) logement(s) détecté(s) — {watcher_name} @everyone",
            "embeds": embeds,
        }
        ok = _post(webhook_url, payload)
        if not ok:
            logger.error("Échec d'envoi d'un lot de %s annonce(s) vers Discord.", len(chunk))
        time.sleep(DELAY_BETWEEN_MESSAGES)
