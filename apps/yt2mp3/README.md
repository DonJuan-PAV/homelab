# You Link to MP3 + Navidrome

Your own music streaming setup:

- **You Link to MP3** (port 8080): paste a YouTube link, convert it to MP3, and add it to your music library with one click (or download it instead).
- **Navidrome** (port 4533): streams your music library to your browser and phone, like your own Spotify.

Both share one `music` folder. Songs added from the converter go into `music/You Link/` and show up in Navidrome within about a minute.

## Playlists

Paste a playlist link (`youtube.com/playlist?list=…`) and every song goes straight into the library, in its own folder named after the playlist. Navidrome shows it as one album, in playlist order. Songs that can't be converted (deleted, private, too long) are skipped and listed at the end.

If you paste a song opened from inside a playlist (`watch?v=…&list=…`), the page asks whether you want just that song or the whole playlist.

## First-time setup

On the server, inside this folder:

```bash
# 1. Create the folders (they must belong to you, not root)
mkdir -p music navidrome-data

# 2. Check your user and group ids
id -u    # usually 1000
id -g    # usually 1000
```

If either number is **not** 1000, create a file called `.env` next to `docker-compose.yml`:

```
PUID=1001
PGID=1001
```

Then start everything:

```bash
docker compose up -d --build
```

- Converter: `http://SERVER-IP:8080`
- Music library: `http://SERVER-IP:4533`. The first visit asks you to create the admin account.

## Using a different music folder

To use music you already have somewhere else (for example `/home/pablo/Music`), add this to `.env`:

```
MUSIC_DIR=/home/pablo/Music
```

and run `docker compose up -d` again.

## Configuration (converter)

| Variable | Default | Meaning |
|---|---|---|
| `AUTO_ADD_TO_LIBRARY` | `false` | `true` adds every song to the library automatically, no button |
| `LIBRARY_SUBDIR` | `You Link` | Folder inside the library for converted songs |
| `DEFAULT_ALBUM` | `You Link` | Album name used when YouTube doesn't provide one |
| `MAX_PLAYLIST_ITEMS` | `100` | Most songs taken from one playlist |
| `DEFAULT_BITRATE` | `192` | Pre-selected bitrate |
| `MAX_DURATION_SECONDS` | `10800` | Reject longer videos |
| `FILE_TTL_SECONDS` | `3600` | Delete temporary files (not library songs) after this long |
| `NAVIDROME_URL` | *(empty)* | Link for "Open your music library"; empty = same address on port 4533 |
| `PUID` / `PGID` | `1000` | Owner of songs added to the library |

## Listening on your phone

Navidrome works in the phone's browser, but a Subsonic-compatible music app is nicer (offline downloads, lock-screen controls). Add a server in the app with your Navidrome address, username and password.

## Listening outside your home

Recommended: **Tailscale**. Install it on the server and your phone, then use the server's Tailscale address instead of the home IP. Nothing is opened to the internet, and music apps work normally.

## Keeping it working
YouTube changes often and yt-dlp updates to keep up. If conversions start failing, rebuild to pull the latest yt-dlp:
```bash
docker compose build --no-cache yt2mp3 && docker compose up -d
```

## API
- `POST /api/convert` `{"url": "...", "bitrate": "192", "mode": "single" | "playlist"}` → `{"job_id": "...", "mode": "..."}`
- `GET /api/status/<job_id>` → status, progress, eta, title, error, saved_as; playlists also return index, total, overall, overall_eta, added, skipped
- `POST /api/library/<job_id>` → moves the MP3 into the library, returns `{"saved_as": "..."}`
- `GET /api/download/<job_id>` → the MP3
- `GET /health`

## Note
For personal use with content you have the right to download. Downloading may conflict with YouTube's Terms of Service.
