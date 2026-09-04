"""
Scraping de trouverunlogement.lescrous.fr.

Le site est une application JS (rendu côté client), un simple requests.get()
ne suffit donc pas à voir les résultats : on utilise Playwright (Chromium
headless) pour charger la page comme un vrai navigateur le ferait.

Stratégie d'extraction volontairement robuste aux changements de design :
on ne cible pas des classes CSS (qui changent souvent d'une mise à jour du
site à l'autre) mais le seul élément stable observé sur ce site : les liens
vers une fiche logement, qui suivent toujours le motif
    /tools/<id>/accommodations/<id>
On récupère ensuite le texte du bloc parent (carte résultat) le plus proche
pour en tirer un titre / une courte description.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin

from playwright.sync_api import Browser, Page, TimeoutError as PWTimeoutError, sync_playwright

from config import PAGE_TIMEOUT_MS, USER_AGENT

logger = logging.getLogger("crous_monitor.scraper")

ACCOMMODATION_LINK_RE = re.compile(r"/tools/\d+/accommodations/\d+")

# Boutons de bannière cookies courants (FR) à essayer de fermer pour ne pas
# bloquer le rendu des résultats.
COOKIE_BUTTON_TEXTS = [
    "Tout accepter",
    "J'accepte",
    "Accepter",
    "Accepter tout",
    "OK",
]


@dataclass
class Listing:
    id: str
    url: str
    title: str
    description: str

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
        }


def _dismiss_cookie_banner(page: Page) -> None:
    for text in COOKIE_BUTTON_TEXTS:
        try:
            btn = page.get_by_role("button", name=re.compile(text, re.IGNORECASE))
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                logger.debug("Bannière cookies fermée via bouton %r", text)
                return
        except Exception:
            continue


def _extract_listings(page: Page, base_url: str) -> list[Listing]:
    """Récupère, depuis le DOM rendu, tous les liens vers une fiche logement
    ainsi qu'un court texte descriptif issu de leur carte parente."""
    anchors = page.locator("a[href*='/accommodations/']")
    count = anchors.count()
    results: dict[str, Listing] = {}

    for i in range(count):
        anchor = anchors.nth(i)
        try:
            href = anchor.get_attribute("href") or ""
        except Exception:
            continue
        if not ACCOMMODATION_LINK_RE.search(href):
            continue

        full_url = urljoin(base_url, href)
        acc_id_match = re.search(r"/accommodations/(\d+)", href)
        acc_id = acc_id_match.group(1) if acc_id_match else full_url

        if acc_id in results:
            continue

        title = ""
        description = ""
        try:
            title = (anchor.inner_text(timeout=1000) or "").strip()
        except Exception:
            pass

        # On remonte jusqu'à un conteneur de carte plausible pour récupérer
        # un peu de texte de contexte (résidence, ville, loyer...).
        try:
            card_text = anchor.evaluate(
                """el => {
                    let node = el;
                    for (let i = 0; i < 4 && node.parentElement; i++) {
                        node = node.parentElement;
                        if (node.innerText && node.innerText.length > 40) break;
                    }
                    return node.innerText || '';
                }"""
            )
            description = (card_text or "").strip().replace("\n", " · ")
        except Exception:
            pass

        if not title:
            title = description[:80] if description else "Logement Crous"

        results[acc_id] = Listing(
            id=acc_id,
            url=full_url,
            title=title[:250],
            description=description[:400],
        )

    return list(results.values())


def _scroll_to_load_all(page: Page, max_scrolls: int = 15, pause_s: float = 0.4) -> None:
    """Certains résultats sont chargés en lazy-loading / pagination infinie
    au scroll : on descend progressivement la page pour tout charger, avec
    une petite pause à chaque étape (courtoisie + laisse le temps au DOM de
    se mettre à jour)."""
    last_height = -1
    for _ in range(max_scrolls):
        page.mouse.wheel(0, 2000)
        time.sleep(pause_s)
        try:
            height = page.evaluate("document.body.scrollHeight")
        except Exception:
            break
        if height == last_height:
            break
        last_height = height


def fetch_listings(browser: Browser, search_url: str) -> list[Listing]:
    """Charge une URL de recherche et retourne la liste des logements trouvés."""
    context = browser.new_context(user_agent=USER_AGENT, locale="fr-FR")
    page = context.new_page()
    try:
        page.goto(search_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
        except PWTimeoutError:
            # Certaines pages gardent une connexion ouverte (websocket, polling) ;
            # on continue même si "networkidle" n'est jamais atteint.
            pass

        _dismiss_cookie_banner(page)
        time.sleep(1.0)  # laisse le temps au JS de peupler les résultats
        _scroll_to_load_all(page)

        listings = _extract_listings(page, search_url)
        return listings
    finally:
        context.close()


def run_playwright():
    """Context manager pratique pour obtenir un navigateur Chromium headless
    partagé entre les deux watchers (une seule instance, pas de concurrence)."""
    return sync_playwright()
