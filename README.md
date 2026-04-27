# Nova-Tunes

**Ton système musical 100% local — sans cloud, sans pub, sans compte.**

Nova-Tunes est un jukebox personnel construit autour de trois briques :

- **Navidrome** — un serveur de musique web auto-hebergé (comme un Spotify local)
- **Soulseek** — le réseau P2P pour découvrir et télécharger de la musique
- **Recommender** — un script qui analyse ta bibliothèque et te suggère de nouveaux artistes via MusicBrainz

```
                    ┌─────────────────────────────────┐
  Internet  ──────►  │       Soulseek P2P              │
                    │  (download de musique via       │
                    │   interface web noVNC)           │
                    └──────────────┬──────────────────┘
                                   │ fichiers
                                   ▼
                    ┌─────────────────────────────────┐
  Browser  ◄───────  │       Navidrome                 │
                    │  (player web + scan musique)    │
                    └──────────────┬──────────────────┘
                                   │ lecture
                                   ▼
                    ┌─────────────────────────────────┐
                    │    Suggest.py (Recommender)     │
                    │  MusicBrainz API → suggestions  │
                    └─────────────────────────────────┘
```

---

## Fonctionnalités

| Feature | Détail |
|---------|--------|
| **Player web** | Navidrome sur http://localhost:4533 — lecture, Playlists, search |
| **P2P downloads** | SoulseekQt via navigateur (noVNC) sur http://localhost:6080 |
| **Recommandations** | Script Python qui interroge MusicBrainz pour trouver des artistes similaires |
| **100% local** | Aucune donnée ne quitte ta machine — pas de cloud, pas de compte |
| **Multi-plateforme** | Docker Compose + scripts Python (fonctionne sur Linux / WSL / macOS) |

---

## Prérequis

- **Docker** + **Docker Compose** (standalone ou `docker compose` v2)
- **Python 3.10+** avec `pip`
- **Ports libres** : 4533, 6080

---

## Installation

### 1. Cloner le projet

```bash
git clone https://github.com/nikodindon/nova-tunes.git
cd nova-tunes
```

### 2.Installer les dépendances Python

```bash
pip install musicbrainzngs mutagen --break-system-packages
```

### 3. Lancer les services

```bash
# Version standalone (WSL / ancienne install Docker)
docker-compose up -d

# Version Docker Compose v2
docker compose up -d
```

### 4. Vérifier

| Service | URL | Status attendu |
|---------|-----|----------------|
| Navidrome (player web) | http://localhost:4533 | Page de login |
| Soulseek (téléchargement P2P) | http://localhost:6080 | Interface noVNC |

---

## Configuration

### Structure des dossiers

```
nova-tunes/
├── music/                  # ← ta bibliothèque musicale (Navidrome scanne ici)
│   └── (artist)/(album)/   #   téléchargez ici via Soulseek ou yt-dlp
├── data/                   # cache du recommender
├── navidrome/              # config Navidrome
│   └── data/               # données Navidrome (non push)
├── soulseek/               # config Soulseek
│   ├── appdata/            # données Soulseek (non push)
│   └── shared/             # dossier partagé (non push)
├── recommender/
│   └── suggest.py          # script de recommandations
└── docker-compose.yml
```

### Ajouter de la musique

**Option A — via Soulseek (recommandé)**
1. Ouvre http://localhost:6080
2. Connecte-toi (compte Soulseek gratuit, sans email)
3. Cherche un artiste / album
4. Le fichier arrive dans `music/complete/<user>/<album>/`

**Option B — via yt-dlp (fallback)**
```bash
yt-dlp -x --audio-format mp3 \
  -o "music/%(artist)s - %(title)s.%(ext)s" \
  "https://youtube.com/watch?v=..."
```

**Option C — copie directe**
```bash
cp /path/to/album.mp3 music/
```

### Navidrome — premier accès

1. Ouvre http://localhost:4533
2. **Premier lancement** : crée un compte admin (email + mot de passe)
3. La musique dans `music/` est scannée automatiquement toutes les heures
4. Pour rescanner immédiatement : **Settings → Library → Scan now**

---

## Le Recommender

Le script `recommender/suggest.py` analyse ta bibliothèque locale et te propose de nouveaux artistes via l'API MusicBrainz.

### Utilisation

```bash
# Lancer les recommandations (basées sur ta bibliothèque)
python3 recommender/suggest.py

# Suggestion pour un artiste précis
python3 recommender/suggest.py -a "Metallica"

# Re-scanner la bibliothèque avant de suggérer
python3 recommender/suggest.py --refresh
```

### Comment ça marche (technique)

```
music/*.mp3
    │
    ▼  lecture des tags ID3 (mutagen)
    │
library_cache.json
    │
    ▼  extraction des artistes
    │
top_artists = ["Metallica", "Behemoth", "The Warning"]
    │
    ▼  MusicBrainz search → mbid
    │
artist tags = ["thrash metal", "heavy metal", "metal"]
    │
    ▼  MusicBrainz query "tag:thrash metal AND NOT arid:..."
    │
suggestions = ["Metal Church", "Kreator", "Evile", "Trouble"]
```

### Dépendances

```bash
pip install musicbrainzngs mutagen --break-system-packages
```

---

## Stack technique

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Player web | Navidrome (Docker) | Serveur de musique, UI web, lecture audio |
| P2P | SoulseekQt + noVNC (Docker) | Téléchargement de musique |
| Recommender | Python 3 + musicbrainzngs | Suggestions basées sur MusicBrainz |
| Métadonnées | mutagen (Python) | Lecture des tags ID3 des MP3 |
| Orchestration | Docker Compose | Lancement des deux services |

---

## Commandes utiles

```bash
# Démarrer / arrêter
docker-compose up -d        # start
docker-compose down        # stop
docker-compose restart      # restart

# Logs
docker-compose logs -f navidrome
docker-compose logs -f soulseek

# Statut des containers
docker ps

# Rescanner la bibliothèque (via API Navidrome)
curl -X POST http://localhost:4533/api/v1/do/scan

# Reset complet (supprime les données des containers)
docker-compose down -v
docker-compose up -d
```

---

## Roadmap

- [x] **v1** — Navidrome + Soulseek (docker-compose, network_mode host)
- [x] **v2** — Recommender avec MusicBrainz (suggestions par tag)
- [ ] **v3** — Listen log : tracker l'historique d'écoute pour améliorer les suggestions
- [ ] **v4** — Intégration yt-dlp comme fallback (quand Soulseek ne trouve pas)
- [ ] **v5** — Recherche unifiée (Navidrome + suggestions dans une même interface)
- [ ] **v6** — Export de playlists (M3U, JSON)
- [ ] **v7** — Déploiement sur VPS (Navidrome accessible depuis l'extérieur)

---

## FAQ

**Q : Pourquoi Soulseek plutôt que Spotify / Deezer ?**
> Soulseek est un réseau P2P où les utilisateurs partagent leur musique. Pas d'abonnement, pas de DRM, tout est en local. C'est le moyen le plus efficace pour découvrir de la musique obscure ou rare.

**Q : Est-ce que mes MP3 sont partagés automatiquement ?**
> Oui si tu configures un dossier de partages dans Soulseek. Par défaut, seuls les fichiers que tu télécharges sont dans `music/`. Ajoute un dossier de partage (ex: `music/`) dans Soulseek → Options → Shares pour que les autres puissent aussi télécharger depuis toi.

**Q : Le recommender est lent, pourquoi ?**
> MusicBrainz limite ses requêtes à 1 par seconde. Le script ajoute un délai de 0.55s entre chaque appel pour rester poli. 3 artistes = ~20 secondes minimum.

**Q : Comment fonctionne le réseau P2P de Soulseek ?**
> Chaque client écoute sur un port (61122 par défaut). Ton routeur / firewall doit允许 les connexions entrantes sur ce port pour que les autres peers puissent te contacter. Si tu es derrière CGNAT (FAI français), les connexions entrantes peuvent être bloquées — les téléchargements fonctionnent quand même en mode passif.

**Q : Docker Desktop sur WSL — les ports ne marchent pas**
> Ajoute `"serverPorts": [4533, 6080]` dans les paramètres Docker Desktop ou utilise `network_mode: host` dans le docker-compose (déjà configuré).

---

## Licence

MIT — fait pour toi, partage si tu veux.
