# Nova-Tunes

**Ton système musical 100% local — sans cloud, sans pub, sans compte.**

Un jukebox personnel construit autour de trois briques :

- **Navidrome** — serveur de musique web auto-hébergé (comme un Spotify local)
- **Soulseek** — réseau P2P pour découvrir et télécharger de la musique via slskd (daemon avec API REST)
- **Recommender** — script qui analyse ta bibliothèque et suggère de nouveaux artistes via MusicBrainz
- **Download automation** — scripts Python pour télécharger des albums entiers avec covers, tags, et organisation auto

Tout le trafic reste en local. Aucun service cloud.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         INTERNET                                 │
│                                                                  │
│   Soulseek P2P Network (port UDP 61112 / TCP 50300 relay)        │
│         peers: <YOUR_SOULSEEK_USER> + millions d'autres utilisateurs │
└────────────────────────────┬─────────────────────────────────────┘
                             │ TCP REST API
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  CONTAINER: soulseek (slskd/slskd)  ──►  port 5030 (HTTP)        │
│                                                                  │
│  Soulseek daemon process                                          │
│    - Se connecte au réseau Soulseek avec tes credentials          │
│    - Sert l'API REST (auth Bearer token)                         │
│    - Écrit les fichiers téléchargés dans /music                  │
│                                                                  │
│  Config: SLSKD_SOULSEEK_USERNAME / _PASSWORD (env vars)          │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             │ fichiers MP3/FLAC dans /music
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  CONTAINER: navidrome (deluan/navidrome)  ──►  port 4533 (HTTP)  │
│                                                                  │
│  Navidrome (serveur de musique)                                   │
│    - Scan automatique de /music toutes les heures                 │
│    - Player web: http://localhost:4533                            │
│    - Lecture, playlists, recherche                                │
│                                                                  │
│  Scan initial au démarrage, puis triggers périodiques             │
└──────────────────────────────────────────────────────────────────┘
                             ▲
                             │ scan
                    ┌────────┴────────┐
                    │   ./music/       │
                    │  (dossier host)  │
                    └─────────────────┘
```

**Pilotage par Hermes (CLI) ou scripts Python :**

```
Hermes CLI ──► download_album.py ──► slskd REST API (localhost:5030)
                                ├── POST /api/v0/session         (auth)
                                ├── POST /api/v0/searches         (lancer search)
                                ├── GET  /api/v0/searches/{id}   (état)
                                ├── GET  /api/v0/searches/{id}/responses  (résultats)
                                ├── POST /api/v0/transfers/downloads/{user} (enqueue)
                                └── GET  /api/v0/transfers/downloads      (statut)
                                └── iTunes API (cover art HD)
                                └── Organize: Artist/Album (Year)/
                                └── Fix permissions (no sudo needed)
                                └── Trigger Navidrome scan
```

---

## Table des matières

1. [Prérequis](#prérequis)
2. [Installation](#installation)
3. [Configuration des credentials](#configuration-des-credentials)
4. [Démarrage rapide](#démarrage-rapide)
5. [Download automation](#download-automation)
6. [API slskd — Guide complet](#api-slskd--guide-complet)
7. [Navidrome — premier accès](#navidrome--premier-accès)
8. [Le Recommender](#le-recommander)
9. [Gestion des pochettes](#gestion-des-pochettes)
10. [Structure des fichiers](#structure-des-fichiers)
11. [Commandes utiles](#commandes-utiles)
12. [Troubleshooting](#troubleshooting)
13. [Bugs connus et limitations](#bugs-connus-et-limitations)
14. [FAQ](#faq)
15. [Stack technique](#stack-technique)
16. [Roadmap](#roadmap)

---

## Prérequis

- **Docker Desktop** (Windows + WSL) ou **Docker** (Linux / macOS)
- **Docker Compose** standalone (`/home/niko/bin/docker-compose`) ou intégré (`docker compose`)
- **Python 3.10+** avec `pip`
- **yt-dlp** dans `/home/niko/bin/yt-dlp` (fallback pour YouTube/SoundCloud)
- **Ports libres** : 4533 (Navidrome), 5030 (slskd API), 50300 (slskd relay TCP)

---

## Installation

### 1. Cloner le projet

```bash
git clone https://github.com/nikodindon/nova-tunes.git
cd nova-tunes
```

### 2. Configurer les credentials Soulseek

```bash
# Créer le fichier .env à la racine du projet
cp .env.example .env   # si un template existe, sinon créer manuellement
# Éditer .env et remplir :
# SLSKD_USERNAME=<YOUR_SOULSEEK_USER>
# SLSKD_PASSWORD=<YOUR_SOULSEEK_PASS>
# SLSKD_WEB_USER=<YOUR_SLSKD_WEB_USER>
# SLSKD_WEB_PASS=<YOUR_SLSKD_WEB_PASS>
```

Le `.env` contient tes credentials Soulseek. **Il est dans `.gitignore` — ne JAMAIS le commiter.**

Pour créer un compte Soulseek : https://www.soulseekqt.net/network.html (gratuit, sans email)

### 3. Installer les dépendances Python

```bash
pip install musicbrainzngs mutagen --break-system-packages
```

### 4. Lancer les services

```bash
# Version standalone (WSL)
docker-compose up -d

# Version Docker Compose v2
docker compose up -d
```

### 5. Vérifier

| Service | URL | Ce que tu dois voir |
|---------|-----|---------------------|
| Navidrome (player) | http://localhost:4533 | Page de login / dashboard |
| slskd (API + web UI) | http://localhost:5030 | Interface web slskd |
| Logs Navidrome | `docker logs navidrome` | "Scanner scheduled" |
| Logs slskd | `docker logs soulseek` | "Connected to Soulseek network" |

---

## Configuration des credentials

### Variables d'environnement (.env)

```bash
# Credentials Soulseek (compte gratuit sur soulseekqt.net)
SLSKD_USERNAME=<YOUR_SOULSEEK_USER>
SLSKD_PASSWORD=***

# Credentials interface web slskd (optionnel — interface pas vraiment utilisée)
SLSKD_WEB_USER=<YOUR_SLSKD_WEB_USER>
SLSKD_WEB_PASS=<YOUR_SLSKD_WEB_PASS>
```

Ces variables sont injectées dans le conteneur `soulseek` par docker-compose et passées à slskd au démarrage.

### Credentials interface web slskd

Par défaut, l'interface web de slskd (`http://localhost:5030`) est protégée par Basic Auth :
- Utilisateur : `slskd`
- Mot de passe : `slskd`

Tu n'as normalement pas besoin d'y accéder — tout est pilotable via l'API REST.

### Modifier le mot de passe web slskd

Édite le `.env` et redémarre :

```bash
docker-compose restart soulseek
```

---

## Démarrage rapide

### Télécharger un album complet (recommandé)

```bash
# Télécharger un album avec cover art et organisation auto
python3 download_album.py "Emperor" "In The Nightside Eclipse" 1994

# Le script fait tout :
# 1. Multi-query search sur Soulseek
# 2. Sélection du meilleur source (plus de fichiers + vitesse)
# 3. Téléchargement de tous les tracks
# 4. Organisation dans Artist/Album (Year)/
# 5. Téléchargement cover art HD depuis iTunes
# 6. Fix des permissions (pas de sudo nécessaire)
# 7. Trigger du scan Navidrome
```

### Download automatique via Hermes

Depuis Hermes, dis simplement :
```
"download The Warning Error"
```
ou
```
"cherche et télécharge metallica fuel"
```

Hermes exécute `download_album.py` qui automatise tout le workflow.

### Télécharger un titre unique (fallback)

```bash
# Chercher et télécharger un titre via slskd
python3 soulseek-like/download.py "Pink Floyd Dark Side of the Moon"

# Voir les résultats sans télécharger
python3 soulseek-like/download.py "Pink Floyd Dark Side of the Moon" --list

# Avec un timeout de recherche plus long (par défaut 40s)
python3 soulseek-like/download.py "Pink Floyd Dark Side of the Moon" --timeout 60
```

### Accéder à Navidrome

1. Ouvre http://localhost:4533
2. Crée un compte admin au premier lancement
3. L'album apparaît dans la bibliothèque après le prochain scan (automatique toutes les heures)

Pour rescanner immédiatement :
```bash
docker exec navidrome /app/navidrome scan --full
# ou via API
curl -X POST http://localhost:4533/api/v1/do/scan
```

---

## Download automation

### download_album.py — Script principal

**Usage :**
```bash
python3 download_album.py "<Artist>" "<Album>" [Year]

# Exemples :
python3 download_album.py "Emperor" "In The Nightside Eclipse" 1994
python3 download_album.py "Dark Tranquillity" "The Gallery" 1995
python3 download_album.py "Stevie Ray Vaughan" "Texas Flood"
```

**Fonctionnement :**

```
1. Auth slskd → obtenir Bearer token (credentials web UI)
2. Multi-query search (4 requêtes : artist+album, artist+album+year, etc.)
3. Attendre 25s entre chaque search (Soulseek est lent)
4. Grouper les résultats par (username, album_dir)
5. Sélectionner le meilleur source :
   - Plus grand nombre de fichiers
   - Vitesse moyenne la plus élevée
6. Enqueue des fichiers avec retry logic (gestion rate limits 429)
7. Monitorer la progression jusqu'à completion
8. Organiser dans music/Artist/Album (Year)/
9. Télécharger la cover art depuis iTunes API (HD 1000x1000)
10. Fix des permissions (chown sans sudo, fallback Docker)
11. Cleanup des dossiers temporaires Soulseek
12. Trigger du scan Navidrome
13. Logging JSON dans ~/.cache/nova-tunes/
```

**Features :**
- Multi-query search avec wait times optimisés
- Déduplication des fichiers en queue
- Retry automatique sur rate limits (429)
- Organisation auto : `Artist/Album (Year)/`
- Cover art HD depuis iTunes API
- Fix permissions sans sudo (Docker exec fallback)
- Cleanup des folders temporaires Soulseek
- Trigger Navidrome scan auto
- Logs JSON pour audit trail

### soulseek-like/download.py — Download de titres uniques

Script legacy pour télécharger des titres individuels ou des albums simples.

**Usage :**
```bash
python3 soulseek-like/download.py "query"                    # download best match
python3 soulseek-like/download.py "query" --list           # show results only
python3 soulseek-like/download.py "query" --limit 20       # max results to consider
python3 soulseek-like/download.py "query" --timeout 60      # search timeout
```

**Fallback yt-dlp :**
Si slskd est inaccessible, le script fallback sur YouTube/SoundCloud via yt-dlp.

---

## API slskd — Guide complet

slskd expose une API REST complète sur `http://localhost:5030`. Toutes les routes nécessitent un token Bearer obtenu via authentication.

### Authentication

```bash
# Obtenir un token (valide ~7 jours)
TOKEN=$(curl -s -X POST http://localhost:5030/api/v0/session \
  -H "Content-Type: application/json" \
  -d '{"username":"slskd","password":"slskd"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Utiliser le token dans les requêtes suivantes
curl http://localhost:5030/api/v0/... -H "Authorization: Bearer $TOKEN"
```

**Note** : le endpoint d'auth utilise les credentials de l'interface web slskd (`slskd`/`slskd` par défaut), PAS les credentials Soulseek. slskd valide l'auth web UI pour délivrer le token API.

### Routes principales

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/api/v0/session` | Authentification — retourne le Bearer token |
| `POST` | `/api/v0/searches` | Lancer une recherche |
| `GET` | `/api/v0/searches/{id}` | État d'une recherche (state, fileCount, responseCount) |
| `GET` | `/api/v0/searches/{id}/responses` | Liste des utilisateurs + leurs fichiers |
| `POST` | `/api/v0/transfers/downloads/{username}` | Enqueue des fichiers à télécharger depuis un user |
| `GET` | `/api/v0/transfers/downloads` | Liste des transferts actifs avec leur état |
| `DELETE` | `/api/v0/transfers/downloads/{username}/{transferId}` | Annuler un transfert |

### Lancer une recherche

```bash
SEARCH_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

curl -X POST http://localhost:5030/api/v0/searches \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"id\":\"$SEARCH_ID\",\"searchText\":\"pink floyd dark side of the moon\"}"
```

Réponse : `{}` (vide, succès)

### Poll l'état de la recherche

```bash
# Retourne JSON avec state, fileCount, responseCount
curl http://localhost:5030/api/v0/searches/${SEARCH_ID} \
  -H "Authorization: Bearer $TOKEN"
```

États possibles : `InProgress`, `Completed`, `Completed, ResponseLimitReached`

### Récupérer les résultats

```bash
curl http://localhost:5030/api/v0/searches/${SEARCH_ID}/responses \
  -H "Authorization: Bearer $TOKEN"
```

Réponse : liste de Users, chacun avec un tableau `files` :

```json
[
  {
    "username": "gr3q",
    "fileCount": 3,
    "files": [
      {
        "filename": "music\\Pink Floyd\\1973 - Dark Side of the Moon\\01 - Pink Floyd - Speak to Me.flac",
        "size": 34567890,
        "bitRate": 1411,
        "extension": "flac",
        "length": 190,
        "isLocked": false
      }
    ],
    "hasFreeUploadSlot": true,
    "queueLength": 0,
    "uploadSpeed": 6765746
  }
]
```

### Enqueue un téléchargement

```bash
curl -X POST http://localhost:5030/api/v0/transfers/downloads/gr3q \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '[{"filename":"music\\\\Pink Floyd\\\\1973 - Dark Side of the Moon\\\\01 - Pink Floyd - Speak to Me.flac","size":34567890}]'
```

Note : les `\\\\` dans le path sont des backslashes échappés — le format réel est `music\Artist\Album\Track.ext`

### Suivre un transfert

```bash
curl http://localhost:5030/api/v0/transfers/downloads \
  -H "Authorization: Bearer $TOKEN"
```

Réponse : liste des transferts actifs avec leur `state` :
- `Queued` — en attente
- `InProgress` — en cours (contient `progress` en %)
- `Completed, Succeeded` — terminé
- `Completed, Failed` — échoué

---

## Navidrome — premier accès

1. **Ouvrir** : http://localhost:4533
2. **Compte admin** : crée ton email + mot de passe au premier lancement
3. **Bibliothèque** : elle est scannée automatiquement au démarrage et toutes les heures
4. **Rescan manuel** : Settings → Library → "Scan media library NOW"

```bash
# Rescan via API (sans ouvrir le navigateur)
curl -X POST http://localhost:4533/api/v1/do/scan
```

### Supported formats

Navidrome supporte : MP3, FLAC, AAC, OGG, WAV, AIFF, WMA, APE, OPUS

### Structure recommandée

```
music/
├── Dark Tranquillity/
│   ├── The Gallery (1995)/
│   │   ├── 01 - Pennyblack.flac
│   │   ├── 02 - Soul Intranquil.flac
│   │   ├── cover.jpg
│   │   └── ...
│   ├── Character (2005)/
│   └── Fiction (2007)/
├── Emperor/
│   └── In The Nightside Eclipse (1994)/
└── ...
```

---

## Le Recommender

Le script `recommender/suggest.py` analyse ta bibliothèque locale et te propose de nouveaux artistes via MusicBrainz.

### Utilisation

```bash
# Lancer les recommandations (basées sur ta bibliothèque)
python3 recommender/suggest.py

# Suggestion pour un artiste précis
python3 recommender/suggest.py -a "Pink Floyd"

# Re-scanner la bibliothèque avant de suggérer
python3 recommender/suggest.py --refresh
```

### Comment ça marche

```
music/*.mp3
    │
    ▼  lecture des tags ID3 (mutagen)
    │
library_cache.json
    │
    ▼  extraction des artistes uniques
    │
top_artists = ["Pink Floyd", "Metallica", "The Warning"]
    │
    ▼  MusicBrainz search → artist ID (MBID)
    │
artist_tags = ["psychedelic rock", "progressive rock", "classic rock"]
    │
    ▼  MusicBrainz query "tag:psychedelic rock AND NOT arid:..."
    │
suggestions = ["Camel", "Gong", "Hawkwind", "Porcupine Tree"]
```

### Dépendances

```bash
pip install musicbrainzngs mutagen --break-system-packages
```

---

## Gestion des pochettes

### Téléchargement auto via download_album.py

Le script `download_album.py` télécharge automatiquement les covers depuis l'**iTunes API** en HD (1000x1000) :

```python
# Requête iTunes
https://itunes.apple.com/search?term=Artist+Album&media=music&limit=5

# Récupération de l'URL artworkUrl100
# Upgrade vers HD : 100x100bb → 1000x1000bb
# Sauvegarde dans Album (Year)/cover.jpg
```

### fix_covers.py — Pochettes manquantes

Script pour télécharger les covers manquantes via **MusicBrainz Cover Art Archive** :

```bash
python3 fix_covers.py
```

**Fonctionnement :**
1. Scan de `music/` pour trouver les albums sans `cover.jpg`
2. Extraction artist/album/year depuis le nom du dossier
3. Recherche MusicBrainz pour obtenir le MBID (MusicBrainz ID)
4. Téléchargement depuis Cover Art Archive (endpoints: front, 500, 250)
5. Sauvegarde en `cover.jpg`

**Patterns reconnus :**
- `Album (2010)` → album="Album", year=2010
- `The Satanist (2014)` → album="The Satanist", year=2014
- `Texas Flood (1983)` → album="Texas Flood", year=1983

### Scripts de fix spécifiques

- **fix_covers2.py** : Variante avec logique de fallback supplémentaire
- **fix_moment_cover.py** : Fix pour l'album "Le Moment" (couverture spécifique)

### Bonnes pratiques

- Toujours nommer les pochettes `cover.jpg` (reconnu par Navidrome)
- Privilégier le format JPEG, taille ~500KB-2MB (1000x1000)
- Si iTunes ne trouve pas, essayer MusicBrainz Cover Art Archive
- En dernier recours, télécharger manuellement depuis Discogs/AllMusic

---

## Structure des fichiers

```
nova-tunes/
├── .env                      # credentials Soulseek (NE PAS COMMITER)
├── .env.example              # template credentials (commiter ce fichier)
├── .gitignore                # exclut .env, music/, data/, soulseek/data/
├── docker-compose.yml        # définition des 2 services
│
├── music/                    # ← bibliothèque musicale (Navidrome scanne ici)
│   └── <Artist>/<Album (Year)>/   # structure: Artist/Album (Year)/Track.ext
│       └── cover.jpg              # pochette album (optionnel mais recommandé)
│
├── navidrome/                # données Navidrome
│   └── data/                # NON COMMITÉ (ignore dans .gitignore)
│
├── soulseek/                 # données slskd
│   └── data/                # NON COMMITÉ (ignore dans .gitignore)
│                              # config.slskd vit dans ce dossier via volume Docker
│
├── recommender/
│   ├── suggest.py            # script de recommandations
│   └── __pycache__/          # cache Python (ignoré)
│
├── soulseek-like/
│   ├── download.py           # CLI downloader (slskd API + yt-dlp fallback)
│   └── download.sh           # wrapper shell (download.py --list workflow)
│
├── download_album.py         # 🆕 Script principal : download auto d'albums complets
│                              # - Multi-query search
│                              # - Cover art iTunes HD
│                              # - Organisation Artist/Album (Year)/
│                              # - Fix permissions auto
│                              # - Trigger Navidrome scan
│
├── download_emperor.py       # Script spécifique pour Emperor (legacy)
├── fix_covers.py             # 🆕 Download covers manquantes via MusicBrainz
├── fix_covers2.py            # Variante fix covers avec fallback
├── fix_moment_cover.py       # Fix cover spécifique pour "Le Moment"
│
├── data/                     # cache du recommender
│   ├── library_cache.json    # cache bibliothèque (ignoré)
│   └── download.log          # logs téléchargement (ignoré)
│
└── README.md
```

---

## Commandes utiles

### Docker

```bash
# Démarrer / arrêter
docker-compose up -d        # start
docker-compose down          # stop (garde les données)
docker-compose restart       # restart
docker-compose restart soulseek  # restart slskd uniquement

# Logs en temps réel
docker-compose logs -f          # tous les services
docker-compose logs -f soulseek # slskd uniquement
docker logs soulseek           # équivalent

# Statut des containers
docker ps

# Vérifier que slskd est bien connecté
docker exec soulseek curl -s http://localhost:5030/api/v0/session \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"slskd","password":"slskd"}' | grep token
```

### Navidrome

```bash
# Rescan complet de la bibliothèque
docker exec navidrome /app/navidrome scan --full

# Rescan via API (sans docker exec)
curl -X POST http://localhost:4533/api/v1/do/scan

# API Navidrome (liste des albums via curl)
curl -s http://localhost:4533/api/v1/albums | python3 -m json.tool | head -50
```

### slskd (test API à la main)

```bash
# Auth
TOKEN=$(curl -s -X POST http://localhost:5030/api/v0/session \
  -H "Content-Type: application/json" \
  -d '{"username":"slskd","password":"slskd"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Lancer une recherche
curl -X POST http://localhost:5030/api/v0/searches \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"id":"test-1","searchText":"dark side of the moon"}'

# État de la recherche (après quelques secondes)
curl http://localhost:5030/api/v0/searches/test-1 \
  -H "Authorization: Bearer $TOKEN"

# Résultats (après ~18-25s — Soulseek est lent)
curl http://localhost:5030/api/v0/searches/test-1/responses \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -80
```

### Download scripts

```bash
# Télécharger un album complet
python3 download_album.py "Emperor" "In The Nightside Eclipse" 1994

# Fix des pochettes manquantes
python3 fix_covers.py

# Download titre unique (fallback)
python3 soulseek-like/download.py "Metallica Fuel" --list
```

---

## Troubleshooting

### slskd ne se connecte pas au réseau Soulseek

```bash
# Vérifier les logs
docker logs soulseek 2>&1 | tail -20

# Vérifier que les credentials sont corrects
grep SLSKD .env

# Redémarrer avec les bons credentials
docker-compose restart soulseek
```

**Cause la plus fréquente** : credentials Soulseek incorrects ou compte pas encore validé.

### L'API retourne 401 Unauthorized

```bash
# Le token a expiré — en générer un nouveau
TOKEN=$(curl -s -X POST http://localhost:5030/api/v0/session \
  -H "Content-Type: application/json" \
  -d '{"username":"slskd","password":"slskd"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")
```

### Search lancé mais pas de résultats après 40s

Les searches Soulseek prennent du temps (peer discovery). Le timeout par défaut est 40s, augmente si besoin :

```bash
python3 soulseek-like/download.py "query" --timeout 60
```

Le réseau Soulseek peut aussi être lent en heure de pointe.

### download_album.py ne trouve pas l'album

**Causes possibles :**
1. Album trop rare sur Soulseek → essayer des variantes de search
2. Peer avec l'album est offline → réessayer plus tard
3. Firewall bloque les connexions entrantes → vérifier port 61112 UDP

**Solutions :**
```bash
# Essayer sans année
python3 download_album.py "Artist" "Album"

# Essayer avec query plus large
python3 download_album.py "Artist" "Best of"

# Fallback YouTube via download.py
python3 soulseek-like/download.py "Artist Album"
```

### Navidrome ne voit pas les nouveaux fichiers

```bash
# 1. Vérifier que les fichiers sont dans /music
ls -la music/

# 2. Lancer un scan manuel complet
docker exec navidrome /app/navidrome scan --full

# 3. Vérifier les logs Navidrome
docker logs navidrome 2>&1 | grep -i scan

# 4. Erreur de permissions ?
docker exec navidrome ls -la /music
```

**Cause fréquente** : les fichiers appartiennent à root (depuis le conteneur slskd) et Navidrome n'a pas le droit de les lire. Solution :

```bash
# Rendre les fichiers lisibles par tous
chmod -R 644 music/
find music/ -type d -exec chmod 755 {} \;
```

Ou changer le `user` dans le docker-compose de slskd pour correspondre à ton uid.

### Pochettes non affichées dans Navidrome

```bash
# Vérifier que cover.jpg existe
ls -la "music/Artist/Album (Year)/cover.jpg"

# Vérifier la taille (doit être > 10KB)
file "music/Artist/Album (Year)/cover.jpg"

# Rescanner la bibliothèque
docker exec navidrome /app/navidrome scan --full
```

**Notes :**
- Navidrome reconnaît : `cover.jpg`, `cover.png`, `folder.jpg`, `album.jpg`
- Taille recommandée : 500KB-2MB (1000x1000)
- Format : JPEG ou PNG

### Docker Desktop sur WSL — les ports ne marchent pas

Le docker-compose utilise `network_mode: host` pour contourner le docker-proxy de Docker Desktop. Si les ports ne sont toujours pas accessibles :

```bash
# Vérifier que les ports écoutent
ss -tlnp | grep -E '4533|5030|50300'
```

### Permissions — fichiers owned by root

Les fichiers téléchargés par slskd peuvent appartenir à root. `download_album.py` inclut un fix auto, mais si besoin :

```bash
# Fix manuel (one-time)
sudo chown -R $USER:$USER music/

# Ou configurer Docker pour utiliser ton UID/GID
# Éditer docker-compose.yml et ajouter :
# user: "${UID}:${GID}"
```

---

## Bugs connus et limitations

### API enqueue — responses et files n'ont pas de champ `id`

Les fichiers retournés par `GET /api/v0/searches/{id}/responses` n'ont pas de champ `id`. Le endpoint `PUT /api/v0/searches/{id}/responses/{fileId}` (qui nécessiterait cet ID) retourne 404. Le seul endpoint d'enqueue qui fonctionne est `POST /api/v0/transfers/downloads/{username}` avec le `filename` exact.

### Poll interval — les résultats arrivent après ~18-25s

Les searches Soulseek ne retournent pas de résultats immédiatement. Il faut poll toutes les 2-3s pendant 20-30s. `download.py` gère ça, mais un search avec `--timeout 10` sera toujours vide.

### Caractères non-ASCII dans les filenames sources

Certains peers partagent des fichiers avec des caractères `★` (Etoile), backslashes `\`, ou des chemins Windows complets. `download.py` nettoie les noms de fichiers pour le stockage local, mais le `filename` utilisé pour l'enqueue doit matcher exactement ce que le peer partage. Tout décalage peut causer des downloads silencieux qui restent à 0%.

### Bitrate VBR pas fiable pour comparer des fichiers MP3

Le champ `bitRate` dans les réponses slskd représente souvent le bitrate moyen ou nominal. Pour les MP3 VBR, ce n'est pas un indicateur fiable de qualité. Comparer par taille de fichier est plus robuste.

### slskd ne partage pas automatiquement ta bibliothèque

Par défaut, slskd télécharge dans `/music` sans partager ce dossier sur le réseau Soulseek. Tes fichiers restent locaux. Pour les partager, configure `directories.shares` dans `soulseek/data/slskd.yml`.

### DLNA non supporté

Navidrome ne supporte pas DLNA/UPnP nativement. Si tu veux caster sur une TV ou Chromecast, utilise un middleware comme `ymuse` ou `GMediaRender`.

### iTunes API — covers non trouvées pour albums rares

L'iTunes API est excellente pour les albums mainstream, mais peut échouer sur :
- Albums underground / black metal obscur
- Rééditions limitées
- Albums très anciens (avant 2000)

**Fallback** : utiliser `fix_covers.py` qui interroge MusicBrainz Cover Art Archive (plus complet pour les albums rares).

---

## FAQ

**Q : Pourquoi slskd plutôt que SoulseekQt ?**

slskd est un daemon qui expose une API REST. Ça le rend pilotable depuis n'importe quel script (Python, bash, Hermes). L'interface web est un bonus — tu peux t'en passer entièrement. SoulseekQt nécessite un display (noVNC) ou une interaction GUI.

**Q : Comment créer un compte Soulseek ?**

Va sur https://www.soulseekqt.net/network.html — c'est gratuit, sans email, en 2 minutes.

**Q : Mes MP3 sont-ils partagés automatiquement ?**

Non. Par défaut, slskd télécharge dans `/music` sans partager ce dossier. Pour partager ta bibliothèque avec le réseau Soulseek, configure un dossier de partages dans `soulseek/data/slskd.yml` (option `directories.shares`). Tes fichiers restent en local.

**Q : Le recommander est lent, pourquoi ?**

MusicBrainz limite ses requêtes à 1/seconde. Le script ajoute 0.55s de délai entre chaque appel. 5 artistes = ~25 secondes minimum.

**Q : Comment fonctionne le réseau P2P de Soulseek ?**

Chaque client écoute sur un port UDP (61112 par défaut) pour les connexions entrantes. En pratique, les téléchargements fonctionnent même sans portforwarding (mode passif). Le port TCP 50300 est utilisé pour le relay (quand les peers sont derrière un firewall restrictif).

**Q : Docker Desktop sur WSL — les containers ne démarrent pas ?**

Vérifie que Docker Desktop est bien démarré sur Windows. WSL communique avec Docker Desktop via le socket. Si `docker ps` retourne une erreur, redémarre le service Docker Desktop sur Windows.

**Q : Comment upgrader slskd ?**

```bash
docker-compose pull soulseek
docker-compose up -d soulseek
```

L'image est tagguée `slskd/slskd:latest`. Tes credentials dans `.env` persistent (volume `./soulseek/data`).

**Q : download_album.py vs soulseek-like/download.py — lequel utiliser ?**

- **download_album.py** : pour télécharger des **albums complets** avec covers, organisation auto, etc. C'est le script principal à utiliser dans 90% des cas.
- **soulseek-like/download.py** : pour télécharger des **titres individuels** ou en fallback si download_album.py échoue.

**Q : Comment ajouter un album manuellement ?**

```bash
# 1. Créer la structure
mkdir -p "music/Artist/Album (Year)/"

# 2. Copier les fichiers
cp *.flac "music/Artist/Album (Year)/"

# 3. Ajouter la cover (optionnel mais recommandé)
# - Via iTunes API manuelle
# - Via fix_covers.py
# - Download manuel depuis Discogs

# 4. Rescanner Navidrome
docker exec navidrome /app/navidrome scan --full
```

---

## Stack technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Player web | **Navidrome** (Docker) | Serveur de musique, UI web, lecture, scanning |
| P2P daemon | **slskd** (Docker) | Client Soulseek avec API REST |
| Downloads CLI | **Python 3** (download_album.py, download.py) | Automatisation des searches + downloads |
| Recommander | **Python 3** + musicbrainzngs | Suggestions par tags MusicBrainz |
| Métadonnées audio | **mutagen** (Python) | Lecture des tags ID3 |
| Cover art | **iTunes API**, **MusicBrainz Cover Art Archive** | Pochettes HD |
| Conteneurisation | **Docker Compose** | Orchestration des services |

---

## Roadmap

### Version actuelle : v3.x

- [x] **v1** — Navidrome + SoulseekQt (docker-compose, network_mode host)
- [x] **v2** — Recommander avec MusicBrainz (suggestions par tag)
- [x] **v3** — Remplacement SoulseekQt → slskd (API REST, pilotable CLI)
- [x] **v3.1** — download_album.py : automation complète (multi-query, covers, organize, permissions)
- [x] **v3.2** — fix_covers.py : téléchargement covers manquantes via MusicBrainz
- [x] **v3.3** — Gestion des permissions sans sudo (Docker exec fallback)
- [x] **v3.4** — Cleanup auto des dossiers temporaires Soulseek

### Prochaines versions

- [ ] **v3.5** — Fix download.py : gestion filenames avec caractères non-ASCII (★, backslashes Windows) — nécessite de garder le filename exact pour l'enqueue
- [ ] **v3.6** — Multi-source album download (assembler un album depuis plusieurs peers si un seul ne l'a pas complet)
- [ ] **v3.7** — Qualité FLAC 24-bit > FLAC 16-bit > MP3 320 > MP3 VBR (bitdepth/samplerate disponibles dans l'API)
- [ ] **v3.8** — Lecture credentials slskd depuis `.env` dans download.py (actuellement hardcodé `slskd/slskd`)
- [ ] **v4** — Listen log : tracker l'historique d'écoute pour améliorer les suggestions
- [ ] **v5** — Recherche unifiée (Navidrome + suggestions dans une même interface)
- [ ] **v6** — Export de playlists (M3U, JSON)
- [ ] **v7** — Déploiement sur VPS (Navidrome accessible depuis l'extérieur)
- [ ] **v8** — Tagging auto des fichiers téléchargés (artist, album, year, track number via MusicBrainz)
- [ ] **v9** — Deduplication de bibliothèque (détecter les doublons par fingerprint audio)

---

## Licence

MIT — fait pour toi, partage si tu veux.
