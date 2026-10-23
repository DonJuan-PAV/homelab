# homelab

My home server, juanito. It's an Ubuntu machine running around 15 apps in Docker: some I use every day (music, movies, passwords), some I built myself, and some I set up mostly to learn how they work.

Everything in `apps/` is the real configuration the server is running right now. I don't write it by hand. `collect.sh` copies it from the live server, so this repo shows what's actually there, not what I meant to set up.

## Why I have this

It started small, with a little YouTube-to-MP3 app. Then I wanted an alternative to Spotify, which keeps raising its price while the app gets worse with every update, so I set up Navidrome to stream my own music from anywhere. Then I wanted my movies too, then a dashboard to see everything in one place, and it kept growing from there.

It's also where I practice the things I don't get to do much at my day job in IT support: Linux, networking, security, backups, and fixing things I broke myself.

## What runs on it

| App | What it's for | Who can reach it |
|---|---|---|
| Home Base | My own dashboard (I built it): every app, whether it's up, server stats, an Amsterdam clock | Home + Tailscale |
| Jellyfin | Movies and shows | Public (movies.ricamivida.com) |
| Fare Watch | My flight price tracker's website, see [flight-tracker](https://github.com/PAV-JUAN/flight-tracker) | Public (flights.ricamivida.com) |
| Navidrome | My music library, streamed to my phone | Home + Tailscale |
| You Link to MP3 | I built it: paste a YouTube link, get the song | Home + Tailscale |
| File Browser | Upload and manage media from any device | Home + Tailscale |
| qBittorrent + Gluetun | Download client, forced through a VPN | Tailscale only |
| mail-notifier | I built it: counts important Outlook and Gmail emails for Home Base | Home + Tailscale |
| Vaultwarden | My password manager | Tailscale only |
| Uptime Kuma | Watches every app and tells me when something goes down | Home + Tailscale |
| Grafana | Private charts for the flight tracker | Home + Tailscale |
| Pi-hole | Ad blocking for the whole network (DNS) | Admin page: Tailscale only |
| Portainer | Web UI to manage the containers | Tailscale only |
| Caddy | Reverse proxy and HTTPS for the public sites | Ports 80/443 |

`apps/INVENTORY.md` is regenerated on every collect and lists exactly what's running.

## How things get in

There are only two ways in.

1. **Public sites** (Jellyfin and Fare Watch): the router forwards ports 80 and 443 to the server, Caddy takes it from there and handles HTTPS. CrowdSec reads Caddy's logs and blocks IPs that look like they're probing or attacking, and ufw blocks every port I didn't open on purpose.
2. **Everything else** goes through Tailscale. If your device isn't on my Tailscale network, you can't even see those apps.

The domain's DNS is on Cloudflare, with a small container that updates my home IP whenever my internet provider changes it.

## Decisions I made, and why

Anything that can change settings or holds passwords (Portainer, Vaultwarden, Pi-hole's admin page, qBittorrent) is Tailscale-only. I'd rather connect to Tailscale first than have a login page sitting on the internet.

The download client doesn't have a network of its own. It borrows Gluetun's VPN connection (`network_mode: service:gluetun`), so if the VPN drops, it loses internet instead of leaking my home IP. It's the only app on the VPN; everything else uses the normal connection. It also waits for the VPN container to report healthy before it starts.

Passwords and API keys never go in the compose files. Each app reads them from its own `.env`, which git ignores. This repo only has `.env.example` files with the variable names. `collect.sh` also scans for anything that looks like a password in plain text and stops if it finds one, so I can't commit one by accident.

The website for the flight tracker connects to the database with a user that can only read two tables. Even if there's a bug in my code, it can't change or delete anything.

## Backups

Every night, restic backs up the apps' data and configs to two places: a USB stick that stays plugged into the server, and an encrypted copy on Google Drive (through rclone). The USB stick is only 4 GB, so I'm picky about what goes in it. Movies and shows are skipped, since those can be downloaded again.

There's also a restore test script that actually restores files and checks them. A backup I've never restored is just a guess.

## Things that went wrong (so far)


**My own website didn't load at home.** flights.ricamivida.com worked from my phone on data but not from my Wi-Fi. My router can't loop traffic back to its own public IP, so now Pi-hole answers that domain with the server's local address for devices at home.

**Tailscale.** I installed it on the server and then couldn't figure out why I couldn't reach Vaultwarden from my PC. It has to be installed on the device you're connecting *from* too. Obvious in hindsight.

## Updating this repo

```bash
./collect.sh     # copy the current setup from the server, write .env.example files, scan for secrets
git diff         # check what changed before committing
git add .
git commit -m "what changed"
git push
```

## Rebuilding the server from this repo

1. Install Ubuntu Server, Docker and Docker Compose.
2. Clone this repo. For each app, copy `.env.example` to `.env` and fill in the values.
3. Restore the app data from the restic backup.
4. In each `apps/<app>/` folder, run `docker compose up -d`.

## Still on my list

- Login protection for Jellyfin (next)
- Make Navidrome public through Caddy, like Jellyfin
- My own Android app that streams music from Navidrome (started)
