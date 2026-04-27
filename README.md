# Nova-Tunes

**Ton système musical 100% local — sans cloud, sans pub, sans compte.**

Un jukebox personnel construido autour de trois briques :

- **Navidrome** — serveur de musique web auto-hébergé (comme un Spotify local)
- **Soulseek** — réseau P2P pour découvrir et télécharger de la musique via slskd (daemon avec API REST)
- **Recommender** — script qui analyse ta bibliothèque et suggère de nouveaux artistes via MusicBrainz

Tout le trafic reste en local. Aucun service cloud.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         INTERNET                                 │
│                                                                  │
│   Soulseek P2P Network (port UDP 61112 / TCP 50300 relay)        │
│         peers: nikodindon2 + millions d'autres utilisateurs       │
└────────────────────────────┬─────────────────────────────────────┘
                             │ TCP REST API
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  CONTAINER: soulseek (slskd/slskd)  ──►  port 5030 (HTTP)        │
│                                                                  │
│  Soulseek daemon process                                          │
│    - Se connecte au réseau Soulseek avec tes credentials          │
│    - Sert l'API REST (auth Bearer token)                         │
│    - Écrit les fichiers téléchargées dans /music                  │
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

**Pilotage par Hermes (CLI) :**

```
Hermes CLI ──► download.py ──► slskd REST API (localhost:5030)
                                ├── POST /api/v0/session         (auth)
                                ├── POST /api/v0/searches         (lancer search)
                                ├── GET  /api/v0/searches/{id}   (état)
                                ├── GET  /api/v0/searches/{id}/responses  (résultats)
                                ├── POST /api/v0/transfers/downloads/{user} (enqueue)
                                └── GET  /api/v0/transfers/downloads      (statut)
```

---

## Table des matières

1. [Prérequis](#prérequis)
2. [Installation](#installation)
3. [Configuration des credentials](#configuration-des-credentials)
4. [Démarrage rapide](#démarrage-rapide)
5. [API slskd — Guide complet](#api-slskd--guide-complet)
6. [Download CLI — download.py](#download-cli--downloadpy)
7. [Navidrome — premier accès](#navidrome--premier-accès)
8. [Le Recommender](#le-recommender)
9. [Structure des fichiers](#structure-des-fichiers)
10. [Commandes utiles](#commandes-utiles)
11. [Troubleshooting](#troubleshooting)
12. [FAQ](#faq)
13. [Stack technique](#stack-technique)
14. [Roadmap](#roadmap)

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
# SLSKD_USERNAME=ton_username_soulseek
# SLSKD_PASSWORD=ton_mot_de_passe_soulseek
# SLSKD_WEB_USER=slskd
# SLSKD_WEB_PASS=slskd
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
SLSKD_USERNAME=nikodindon2
SLSKD_PASSWORD=olitec

# Credentials interface web slskd (optionnel — interface pas vraiment utilisée)
SLSKD_WEB_USER=slskd
SLSKD_WEB_PASS=slskd
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

### Télécharger un album via CLI (recommandé)

```bash
# Chercher et télécharger "Dark Side of the Moon"
python3 soulseek-like/download.py "Pink Floyd Dark Side of the Moon"

# Voir les résultats sans télécharger
python3 soulseek-like/download.py "Pink Floyd Dark Side of the Moon" --list

# Avec un timeout de recherche plus long (par défaut 30s)
python3 soulseek-like/download.py "Pink Floyd Dark Side of the Moon" --timeout 60
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

Hermes exécute `download.py` qui :
1. Authentifie auprès de slskd (`POST /api/v0/session`)
2. Lance la recherche (`POST /api/v0/searches`)
3. Attend les résultats (poll toutes les 3s, timeout 30s)
4. Enqueue le meilleur résultat (bitrate le plus élevé)
5. Suit le transfert jusqu'à complétion

### Accéder à Navidrome

1. Ouvre http://localhost:4533
2. Crée un compte admin au premier lancement
3. L'album apparaît dans la bibliothèque après le prochain scan (automatique toutes les heures)

Pour rescanner immédiatement :
```bash
curl -X POST http://localhost:4533/api/v1/do/scan
```

---

## API slskd — Guide complet

slskd expose une API REST complète sur `http://localhost:5030`. Toutes les routes都需要 un token Bearer obtenu via authentication.

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

Note : les `\\` dans le path sont des backslashes échappés — le format réel est `music\Artist\Album\Track.ext`

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

## Download CLI — download.py

Script Python qui automatise l'ensemble du flow API slskd + fallback yt-dlp.

### Usage

```bash
python3 soulseek-like/download.py "query"                    # download best match
python3 soulseek-like/download.py "query" --list           # show results only
python3 soulseek-like/download.py "query" --limit 20       # max results to consider
python3 soulseek-like/download.py "query" --timeout 60      # search timeout
```

### Fonctionnement

```
1. Auth slskd → получить Bearer token
2. POST /api/v0/searches avec UUID
3. Poll GET /api/v0/searches/{id} toutes les 3s
4. Quand responseCount > 0 : GET /api/v0/searches/{id}/responses
5. Extraire tous les fichiers, trier par bitrate (best first)
6. Enqueue POST /api/v0/transfers/downloads/{username}
7. Poll GET /api/v0/transfers/downloads jusqu'à Completed
8. Si slskd inaccessible → fallback yt-dlp (YouTube/SoundCloud)
```

### Fallback yt-dlp

Si le démon slskd ne répond pas, `download.py` appelle :

```bash
/home/niko/bin/yt-dlp --no-playlist -x --audio-format mp3 \
  -o "/tmp/nova-tunes.%(ext)s" "ytsearch1:query"
```

Utile comme fallback pour les titres absents de Soulseek.

---

## Navidrome — premier accès

1. **Ouvrir** : http://localhost:4533
2. **Compte admin** : crée ton email + mot de passe au premier lancement
3. **Bibliothèque** : elle est scannée automatiquement au démarrage ettoutes les heures
4. **Rescan manuel** : Settings → Library → "Scan media library NOW"

```bash
# Rescan via API (sans ouvrir le navigateur)
curl -X POST http://localhost:4533/api/v1/do/scan
```

### Supported formats

Navidrome supporte : MP3, FLAC, AAC, OGG, WAV, AIFF, WMA, APE, OPUS

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

## Structure des fichiers

```
nova-tunes/
├── .env                      # credentials Soulseek (NE PAS COMMITER)
├── .env.example              # template credentials (commiter ce fichier)
├── .gitignore                # exclut .env, music/, data/, soulseek/data/
├── docker-compose.yml        # définition des 2 services
│
├── music/                    # ← bibliothèque musicale (Navidrome scanne ici)
│   └── (artist)/(album)/    #   structure recommandée: Artist/Year - Album/Track.ext
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
docker-compose down          # stop ( garde les données)
docker-compose restart       # restart
docker-compose restart soulseek  # restart slskd uniquement

# Logs en temps réel
docker-compose logs -f          # tous les services
docker-compose logs -f soulseek # slskd uniquement
docker logs soulseek           # equivalent

# Statut des containers
docker ps

# Vérifier que slskd est bien connecté
docker exec soulseek curl -s http://localhost:5030/api/v0/session \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"slskd","password":"slskd"}' | grep token
```

### Navidrome

```bash
# Rescan de la bibliothèque
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

# Résultats (après ~20s)
curl http://localhost:5030/api/v0/searches/test-1/responses \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -80
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

### Search lancé mais pas de résultats après 30s

Les searches Soulseek prennent du temps (peer discovery). Augmente le timeout :

```bash
python3 soulseek-like/download.py "query" --timeout 60
```

Le réseau Soulseek peut aussi être lent en heure de pointe.

### Navidrome ne voit pas les nouveaux fichiers

```bash
# 1. Vérifier que les fichiers sont dans /music
ls -la music/

# 2. Lancer un scan manuel
curl -X POST http://localhost:4533/api/v1/do/scan

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

### Docker Desktop sur WSL — les ports ne marchent pas

Le docker-compose utilise `network_mode: host` pour contourner le docker-proxy de Docker Desktop. Si les ports ne sont toujours pas accessibles :

```bash
# Vérifier que les ports écoutent
ss -tlnp | grep -E '4533|5030|50300'
```

---

## FAQ

**Q : Pourquoi slskd plutôt que SoulseekQt ?**

slskd est un daemon qui expose une API REST. Ça le rend pilotable depuis n'importe quel script (Python, bash, Hermes). L'interface web est un bonus — tu peux t'en passer entièrement. SoulseekQt nécessite un display (noVNC) ou une interaction GUI.

**Q : Comment créer un compte Soulseek ?**

Va sur https://www.soulseekqt.net/network.html — c'est gratuit, sans email, en 2 minutes.

**Q : Mes MP3 sont-ils partagés automatiquement ?**

Non. Par défaut, slskd télécharge dans `/music` sans partager ce dossier. Pour partager ta bibliothèque avec le réseau Soulseek, configure un dossier de partages dans `soulseek/data/slskd.yml` (option `directories.shares`). Tes fichiers restent en local.

**Q : Le recommender est lent, pourquoi ?**

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

---

## Stack technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Player web | **Navidrome** (Docker) | Serveur de musique, UI web, lecture, scanning |
| P2P daemon | **slskd** (Docker) | Client Soulseek avec API REST |
| Downloads CLI | **Python 3** (download.py) | Automatisation des searches + downloads |
| Recommender | **Python 3** + musicbrainzngs | Suggestions par tags MusicBrainz |
| Métadonnées audio | **mutagen** (Python) | Lecture des tags ID3 |
| Conteneurisation | **Docker Compose** | Orchestration des services |

---

## Roadmap

- [x] **v1** — Navidrome + SoulseekQt (docker-compose, network_mode host)
- [x] **v2** — Recommender avec MusicBrainz (suggestions par tag)
- [x] **v3** — Remplacement SoulseekQt → slskd (API REST, pilotable CLI)
- [ ] **v4** — Listen log : tracker l'historique d'écoute pour améliorer les suggestions
- [ ] **v5** — Recherche unifiée (Navidrome + suggestions dans une même interface)
- [ ] **v6** — Export de playlists (M3U, JSON)
- [ ] **v7** — Déploiement sur VPS (Navidrome accessible depuis l'extérieur)

---

## Licence

MIT — fait pour toi, partage si tu veux.
