# Monitor Crous → Discord (Île du Saulcy, Metz)

Surveille [trouverunlogement.lescrous.fr](https://trouverunlogement.lescrous.fr) et envoie une
notification Discord (via webhook) dès qu'un nouveau logement apparaît.

Deux watchers sont configurés :

| Watcher | Rôle | Webhook |
|---|---|---|
| **Crous Saulcy (Metz)** | Notifie uniquement les logements dans la zone de l'Île du Saulcy | `DISCORD_WEBHOOK_SAULCY` |
| **Crous France entière (test)** | Notifie TOUS les nouveaux logements du site — sert à vérifier que le pipeline fonctionne, car il doit détecter du nouveau contenu très régulièrement | `DISCORD_WEBHOOK_ALL` |

Les deux webhooks que tu as donnés sont déjà renseignés dans `.env`.

## ⚠️ À faire avant le premier lancement : vérifier l'URL de recherche

Le site Crous change régulièrement l'identifiant numérique de "phase" dans
ses URLs (`/tools/<id>/search`), selon la période de l'année (vœux, phase
principale, phase complémentaire...). Une valeur par défaut est fournie
dans `config.py`, **mais il faut la vérifier / mettre à jour toi-même** :

1. Va sur https://trouverunlogement.lescrous.fr
2. Recherche "Metz" puis navigue/zoome jusqu'à l'Île du Saulcy (ou filtre
   directement sur les résidences Crous du secteur Saulcy).
3. Clique sur "Rechercher dans cette zone".
4. Copie l'URL complète de la barre d'adresse (elle contient
   `.../search?bounds=...`).
5. Colle-la dans le `.env` :
   ```
   CROUS_SEARCH_URL_SAULCY=<ton URL copiée>
   ```
6. Pour le watcher "France entière", l'URL de recherche sans aucun filtre
   géographique convient (`CROUS_SEARCH_URL_ALL`).

Sans cette vérification, le script utilisera une bounding box approximative
autour de l'Île du Saulcy (49.108–49.128 N, 6.150–6.180 E) qui peut ne plus
correspondre à l'ID de campagne en cours.

## Installation

```bash
cd crous_monitor
python3 -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # télécharge le navigateur headless (une fois)
```

## Lancement

```bash
python main.py
```

Le script tourne en continu :
- au premier lancement, il **enregistre l'état actuel sans notifier**
  (pour éviter de spammer Discord avec toutes les annonces déjà en ligne),
  et envoie juste un message "🟢 Monitor démarré" avec le nombre de
  logements déjà référencés ;
- ensuite, à chaque cycle (5 min par défaut, ± 1 min de variation
  aléatoire), il compare les logements trouvés à ceux déjà vus et notifie
  uniquement les nouveaux.

Pour le laisser tourner en arrière-plan durablement : `screen`/`tmux`, un
service `systemd`, une tâche planifiée, ou un conteneur Docker.

## Pourquoi ça ne devrait pas te faire bannir

Le site est une application JS (résultats rendus côté client), donc le
script utilise un vrai navigateur headless (Chromium via Playwright) plutôt
que d'essayer de deviner une API interne non documentée — comportement
identique à celui d'un visiteur normal, pas de contournement technique.

Bonnes pratiques appliquées dans le code :
- **une seule requête à la fois** (jamais de scraping en parallèle) ;
- **intervalle raisonnable entre deux vérifications** (5 min par défaut,
  avec un peu d'aléatoire pour ne pas taper à un rythme parfaitement
  robotique) ;
- **pause entre les deux watchers** dans un même cycle ;
- **backoff progressif** en cas d'échec (pas de ré-essai immédiat en
  boucle) ;
- **User-Agent standard de navigateur**, aucune tentative de masquer ou
  falsifier l'origine des requêtes ;
- état persistant en local (`state/*.json`) pour ne jamais re-scraper une
  information déjà connue plus que nécessaire.

Ceci reste malgré tout un script d'automatisation d'un site tiers : lis les
[conditions d'utilisation](https://trouverunlogement.lescrous.fr) du site
avant un usage prolongé ou intensif, et n'abaisse pas `POLL_INTERVAL_SECONDS`
à une valeur agressive.

## Sécurité

Le fichier `.env` contient tes URLs de webhook Discord, qui permettent à
quiconque les possède de poster dans tes salons Discord. Ne le partage pas
publiquement (ne le commit pas sur un dépôt Git public) et régénère les
webhooks depuis les paramètres Discord si tu penses qu'ils ont fuité.

## Créer un exécutable Windows (.exe)

Un exécutable ne peut être construit que **sur Windows lui-même** (PyInstaller
ne fait pas de compilation croisée depuis un autre OS). Un script fait tout
le travail pour toi :

1. Copie tout le dossier `crous_monitor/` sur ta machine Windows.
2. Vérifie que [Python 3.10+](https://www.python.org/downloads/) est installé
   (coche "Add python.exe to PATH" pendant l'installation).
3. Double-clique sur `build_windows.bat` (ou lance-le depuis une invite de
   commandes). Il va :
   - créer un environnement virtuel et installer les dépendances,
   - télécharger le navigateur Chromium utilisé par Playwright,
   - construire `crous_monitor.exe` avec PyInstaller,
   - copier ton `.env` à côté de l'exécutable final.
4. Le résultat se trouve dans `dist\crous_monitor.exe` (+ `dist\.env` juste à
   côté — ne les sépare pas, l'exe lit sa configuration dans ce `.env`).

Ensuite, double-clic sur `dist\crous_monitor.exe` pour lancer la
surveillance (une fenêtre de console reste ouverte avec les logs).

**Notes :**
- Le navigateur Chromium de Playwright n'est pas intégré dans le `.exe` : il
  est installé une fois dans le cache local Windows
  (`%USERPROFILE%\AppData\Local\ms-playwright`) par le script de build, et
  restera disponible pour l'exe tant que tu ne le supprimes pas.
- Pour lancer l'exe automatiquement au démarrage de Windows : crée un
  raccourci vers `crous_monitor.exe` et place-le dans le dossier
  `shell:startup` (Win+R → `shell:startup`).
- Windows Defender / SmartScreen peut afficher un avertissement au premier
  lancement d'un `.exe` non signé (normal pour un exécutable "fait maison") :
  clique sur "Informations complémentaires" → "Exécuter quand même".



```
crous_monitor/
├── main.py             # boucle principale (orchestration des watchers)
├── scraper.py          # scraping Playwright résilient
├── discord_notify.py   # envoi des notifications (avec gestion du rate-limit)
├── state.py            # persistance des logements déjà vus
├── config.py           # lecture de la configuration (.env)
├── requirements.txt
├── build_windows.bat   # construit crous_monitor.exe (à lancer SUR Windows)
├── .env                # webhooks + réglages (déjà pré-rempli)
└── state/, logs/        # générés automatiquement
```
