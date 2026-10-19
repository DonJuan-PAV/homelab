# Media server: Jellyfin + File Browser

- **Jellyfin** (port 8096): your own Netflix for movies, shows and videos.
- **File Browser** (port 8085): upload files to the server from any browser, including your phone.

File Browser can see two folders: `Videos` (what Jellyfin plays) and `Music` (what Navidrome plays). Upload a video into `Videos` and it shows up in Jellyfin.

## First-time setup

Put this folder next to `yt2mp3` on the server, then inside it:

```bash
mkdir -p media/Movies media/Shows "media/Home Videos" jellyfin/config jellyfin/cache filebrowser-data
docker compose up -d
```

Create the folders as your own user (not with sudo), so the apps can write to them.

- Jellyfin: `http://SERVER-IP:8096`
- File Browser: `http://SERVER-IP:8085`, first login `admin` / `admin`. **Change the password right away** in Settings.

If a page doesn't load: `sudo ufw allow 8096` and `sudo ufw allow 8085`.

## Setting up Jellyfin libraries

On first visit Jellyfin asks you to create an account, then to add libraries. Add one per folder:

| Content type | Folder |
|---|---|
| Movies | `/media/Movies` |
| Shows | `/media/Shows` |
| Home Videos and Photos | `/media/Home Videos` |

## How to name files so Jellyfin recognizes them

Jellyfin finds the poster, description and cast automatically when files are named like this:

```
Movies/Movie Name (2019)/Movie Name (2019).mp4
Shows/Show Name/Season 01/Show Name S01E01.mp4
```

Random clips (phone videos, recordings) go in `Home Videos` with any name.

New files usually appear on their own within a few minutes. To force it: Jellyfin dashboard → Libraries → Scan All Libraries.

## Watching outside your home

Use Tailscale, same as for music: `http://100.x.x.x:8096` from the Jellyfin app on your phone. On mobile data, lower the streaming quality in the app to save data.

## Different folders

To use folders somewhere else, create a `.env` file next to `docker-compose.yml`:

```
MEDIA_DIR=/home/pablo/Videos
MUSIC_DIR=/home/pablo/yt2mp3/music
```

If your user id isn't 1000 (check with `id -u`), also add `PUID=` and `PGID=` with your numbers.
