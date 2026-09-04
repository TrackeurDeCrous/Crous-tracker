"""
Configuration centralisée du monitor Crous.
Toutes les valeurs sensibles (webhooks) et paramétrables (URLs de recherche,
intervalles, bounding box) viennent du fichier .env pour ne jamais être
codées en dur dans la logique du programme.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# En exécutable PyInstaller (--onefile), le code tourne depuis un dossier
# temporaire d'extraction : il faut alors se baser sur l'emplacement réel
# de l'exécutable (sys.executable) plutôt que sur __file__ pour trouver le
# .env, et pour que state/ et logs/ soient créés à côté du .exe.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class WatcherConfig:
    name: str
    search_url: str
    webhook_url: str
    state_file: Path
    only_new: bool = True


# --- Webhooks Discord fournis par l'utilisateur -----------------------------
WEBHOOK_SAULCY = os.getenv("DISCORD_WEBHOOK_SAULCY", "")

# --- URLs de recherche Crous -------------------------------------------------
# ATTENTION : trouverunlogement.lescrous.fr change régulièrement l'identifiant
# numérique de "tool" (phase de campagne : vœux, phase complémentaire, etc.).
# Le plus fiable est de récupérer l'URL toi-même :
#   1. Va sur https://trouverunlogement.lescrous.fr
#   2. Recherche "Metz", zoome sur l'Île du Saulcy (ou clique sur les
#      résidences Saulcy / CROUS Metz Saulcy) puis "Rechercher dans la zone"
#   3. Copie l'URL de la barre d'adresse (elle contient .../search?bounds=...)
#   4. Colle-la dans CROUS_SEARCH_URL_SAULCY ci-dessous / dans le .env
#
# Une valeur par défaut (bounding box autour de l'Île du Saulcy à Metz) est
# fournie pour que le script fonctionne dès le départ, mais VÉRIFIE-LA.
DEFAULT_SAULCY_URL = (
    "https://trouverunlogement.lescrous.fr/tools/47/search"
    "?bounds=6.15464_49.1220463_6.1694012_49.1178192"
    "&locationName=Universit%C3%A9+de+Lorraine+-+Campus+du+Saulcy%2C+Metz"
)
# Recherche nationale (aucun filtre géographique) : sert à vérifier que le
# pipeline de scraping + Discord fonctionne bien, puisqu'elle doit renvoyer
# du nouveau contenu très régulièrement.

SEARCH_URL_SAULCY = os.getenv("CROUS_SEARCH_URL_SAULCY", DEFAULT_SAULCY_URL)

# --- Politesse / anti-bannissement ------------------------------------------
# Intervalle de base entre deux cycles de vérification (en secondes).
POLL_INTERVAL_SECONDS = _get_int("POLL_INTERVAL_SECONDS", 300)  # 5 min
# Jitter aléatoire ajouté/retiré à l'intervalle pour ne pas taper le site
# à un rythme parfaitement régulier et prévisible.
POLL_JITTER_SECONDS = _get_int("POLL_JITTER_SECONDS", 60)
# Pause minimale entre les deux watchers (Saulcy puis National) dans un
# même cycle, pour ne jamais envoyer deux requêtes quasi simultanées.
BETWEEN_WATCHERS_DELAY_SECONDS = _get_float("BETWEEN_WATCHERS_DELAY_SECONDS", 8.0)
# Nombre max de tentatives en cas d'échec réseau / page bloquée, avant
# d'abandonner le cycle et d'attendre le suivant (jamais de ré-essai immédiat
# en boucle serrée).
MAX_RETRIES = _get_int("MAX_RETRIES", 3)
RETRY_BASE_DELAY_SECONDS = _get_float("RETRY_BASE_DELAY_SECONDS", 15.0)
# Timeout de chargement de page (Playwright), en millisecondes.
PAGE_TIMEOUT_MS = _get_int("PAGE_TIMEOUT_MS", 30000)
# User-Agent "normal" de navigateur (celui par défaut de Chromium convient
# déjà ; on le rend configurable si besoin de l'aligner sur un vrai Chrome).
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
)

STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

WATCHERS = [
    WatcherConfig(
        name="Crous Saulcy (Metz)",
        search_url=SEARCH_URL_SAULCY,
        webhook_url=WEBHOOK_SAULCY,
        state_file=STATE_DIR / "seen_saulcy.json",
    ),
]
