"""
Monitor Crous -> Discord.

Deux watchers tournent en séquentiel (jamais en parallèle, pour rester
discret vis-à-vis du site) :
  1. "Crous Saulcy (Metz)"        -> notifie uniquement les logements dans
                                      la zone de l'Île du Saulcy
  2. "Crous France entière (test)" -> notifie TOUS les nouveaux logements
                                      du site, pour vérifier que le pipeline
                                      de scraping + webhook fonctionne bien
                                      (ce watcher doit détecter du nouveau
                                      contenu très régulièrement).

Lancement :
    python main.py
Le script tourne en continu (Ctrl+C pour arrêter).
"""
from __future__ import annotations

import logging
import random
import sys
import time
from logging.handlers import RotatingFileHandler

import config
import discord_notify as notif
from scraper import fetch_listings, run_playwright
from state import load_seen, save_seen

logger = logging.getLogger("crous_monitor")


def setup_logging() -> None:
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        config.LOGS_DIR / "crous_monitor.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)


def run_watcher_cycle(browser, watcher: config.WatcherConfig, first_run: bool) -> None:
    seen = load_seen(watcher.state_file)

    last_error = None
    listings = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            listings = fetch_listings(browser, watcher.search_url)
            break
        except Exception as exc:  # réseau, timeout Playwright, page cassée...
            last_error = exc
            wait = config.RETRY_BASE_DELAY_SECONDS * attempt
            logger.warning(
                "[%s] échec tentative %s/%s (%s) — nouvelle tentative dans %.0fs",
                watcher.name, attempt, config.MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)

    if listings is None:
        logger.error("[%s] abandon du cycle après %s tentatives : %s",
                      watcher.name, config.MAX_RETRIES, last_error)
        if watcher.webhook_url:
            notif.send_error_message(
                watcher.webhook_url, watcher.name,
                f"Impossible de charger la page de recherche après {config.MAX_RETRIES} tentatives : {last_error}",
            )
        return

    current_ids = {item.id for item in listings}

    if first_run and not seen:
        # Premier lancement : on enregistre l'état actuel sans spammer Discord
        # avec des dizaines/centaines d'annonces déjà existantes.
        save_seen(watcher.state_file, current_ids)
        logger.info("[%s] initialisation : %s logement(s) déjà en ligne référencés.",
                    watcher.name, len(current_ids))
        if watcher.webhook_url:
            notif.send_startup_message(watcher.webhook_url, watcher.name, len(current_ids))
        return

    new_ids = current_ids - seen
    if new_ids:
        new_listings = [item.as_dict() for item in listings if item.id in new_ids]
        logger.info("[%s] %s nouveau(x) logement(s) détecté(s).", watcher.name, len(new_listings))
        if watcher.webhook_url:
            notif.send_new_listings(watcher.webhook_url, watcher.name, new_listings)
    else:
        logger.info("[%s] aucun nouveau logement (total actuel : %s).",
                    watcher.name, len(current_ids))

    # On ne "désapprend" jamais un logement disparu (retiré/loué) : on garde
    # l'union pour éviter de re-notifier s'il réapparaît brièvement suite à
    # un rafraîchissement partiel côté site.
    save_seen(watcher.state_file, seen | current_ids)


def main() -> None:
    setup_logging()
    logger.info("Démarrage du monitor Crous — %s watcher(s) configuré(s).", len(config.WATCHERS))

    for w in config.WATCHERS:
        if not w.webhook_url:
            logger.warning("Watcher %r : aucune URL de webhook Discord définie (voir .env).", w.name)

    first_run = True
    with run_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            while True:
                cycle_start = time.time()
                for idx, watcher in enumerate(config.WATCHERS):
                    try:
                        run_watcher_cycle(browser, watcher, first_run)
                    except Exception:
                        logger.exception("Erreur inattendue sur le watcher %r", watcher.name)
                    if idx < len(config.WATCHERS) - 1:
                        time.sleep(config.BETWEEN_WATCHERS_DELAY_SECONDS)

                first_run = False

                elapsed = time.time() - cycle_start
                jitter = random.uniform(-config.POLL_JITTER_SECONDS, config.POLL_JITTER_SECONDS)
                sleep_for = max(30.0, config.POLL_INTERVAL_SECONDS + jitter - elapsed)
                logger.info("Cycle terminé en %.1fs, prochaine vérification dans %.0fs.",
                            elapsed, sleep_for)
                time.sleep(sleep_for)
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur.")
