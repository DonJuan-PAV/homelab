# homelab

The setup of my home server: an Ubuntu machine running about ten self-hosted apps in Docker. Everything here is the real configuration it runs, collected automatically by [`collect.sh`](collect.sh).

## What it runs

| App | What it does | Port |
|---|---|---|
| Home Base | Custom dashboard: app status, server stats, world clock, live counters | 80 |
| Jellyfin | Movies and shows, streamed to any device | 8096 |
| Navidrome | Music library and player | 4533 |
| You Link to MP3 | Custom app: YouTube links to songs for the music library | 8080 |
| File Browser | Upload and manage media from any device | 8085 |
| qBittorrent + Gluetun | Torrents, forced through a NordVPN tunnel with a kill switch | 8070 |
| mail-notifier | Custom app: counts important Outlook and Gmail emails for the dashboard | 8090 |
| Pi-hole | Network-wide ad blocking (DNS) | 8053 |
| Portainer | Web UI to manage the containers | 9443 |

Remote access goes through **Tailscale**, so nothing is exposed to the public internet. [`apps/INVENTORY.md`](apps/INVENTORY.md) lists exactly what's running, regenerated on every collect.

## How it's built

```
              Tailscale (private remote access)
                          │
┌─────────────────────── Ubuntu server ───────────────────────┐
│  Home Base ── checks every app's port, shows live numbers   │
│                                                             │
│  Jellyfin ─┐                                                │
│  File Browser ─┼── shared media folder ◄── qBittorrent      │
│  Navidrome ◄─── You Link to MP3            │                │
│                                           Gluetun ── NordVPN│
│  mail-notifier ── Outlook (Graph API) + Gmail (IMAP)        │
│  Pi-hole (DNS)   Portainer                                  │
└─────────────────────────────────────────────────────────────┘
```

A few decisions worth noting:

- **VPN only where it's needed.** qBittorrent has no network of its own (`network_mode: service:gluetun`), so all of its traffic goes through the VPN, and if the tunnel drops it loses internet instead of leaking the home IP. Every other app keeps the normal connection.
- **Secrets never live in compose files.** Each app reads them from its own `.env`, which is git-ignored; this repo only contains `.env.example` files with the names.
- **Read-only where possible.** The dashboard mounts the host disk read-only (for the free-space meter) and the config files read-only.
- **Health-aware startup.** qBittorrent waits until the VPN container reports healthy before starting.

## Layout

```
apps/<app>/          docker-compose.yml, Dockerfile and config for each app
apps/INVENTORY.md    what's running, generated
collect.sh           gathers everything above from the live server
```

## Updating this repo

```bash
./collect.sh          # copies the current setup, writes .env.example files, scans for secrets
git diff              # review what changed
git add . && git commit -m "Describe the change" && git push
```

`collect.sh` stops with an error if it finds a password written in plain text, so it can't be committed by accident.

## Rebuilding the server from this repo

1. Install Ubuntu Server, Docker and Docker Compose.
2. Clone this repo, and for each app: copy `.env.example` to `.env` and fill in the values.
3. Restore the media and app data from backup.
4. In each `apps/<app>/` folder: `docker compose up -d`.
