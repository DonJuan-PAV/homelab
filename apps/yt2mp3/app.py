"""
You Link to MP3 - a small self-hosted YouTube -> MP3 converter.
Uses yt-dlp for downloading and ffmpeg for audio extraction.
Converted songs (or whole playlists) can be added to a music library folder that Navidrome streams from.
"""
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import Flask, jsonify, render_template, request, send_file, abort
import yt_dlp

try:
    from yt_dlp.postprocessor.metadataparser import MetadataParserPP
except ImportError:  # very old yt-dlp; tag fallbacks are skipped
    MetadataParserPP = None

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/data"))
LIBRARY_DIR = Path(os.environ.get("LIBRARY_DIR", "/music"))
LIBRARY_SUBDIR = os.environ.get("LIBRARY_SUBDIR", "You Link")      # folder inside the library
DEFAULT_ALBUM = os.environ.get("DEFAULT_ALBUM", "You Link")        # album tag when YouTube has none
AUTO_ADD = os.environ.get("AUTO_ADD_TO_LIBRARY", "false").lower() in ("1", "true", "yes")
NAVIDROME_URL = os.environ.get("NAVIDROME_URL", "")                 # optional; page guesses :4533 otherwise
PUID = int(os.environ.get("PUID", 1000))                            # owner of files added to the library
PGID = int(os.environ.get("PGID", 1000))
MAX_DURATION = int(os.environ.get("MAX_DURATION_SECONDS", 3 * 60 * 60))  # 3h default, per song
MAX_PLAYLIST_ITEMS = int(os.environ.get("MAX_PLAYLIST_ITEMS", 100))
FILE_TTL = int(os.environ.get("FILE_TTL_SECONDS", 60 * 60))              # keep temp files 1h
DEFAULT_BITRATE = os.environ.get("DEFAULT_BITRATE", "192")
ALLOWED_BITRATES = {"128", "192", "256", "320"}

YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?"
    r"(youtube\.com/(watch\?v=[\w\-]{6,}|shorts/[\w\-]{6,}|live/[\w\-]{6,}|playlist\?list=[\w\-]{2,})"
    r"|youtu\.be/[\w\-]{6,})",
    re.IGNORECASE,
)

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)

jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()
library_lock = threading.Lock()


def update_job(job_id: str, **fields):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(fields)


def clean_error(e: Exception) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e))  # strip ANSI colors from yt-dlp errors
    return msg.replace("ERROR: ", "")[:500]


def playlist_id(url: str) -> str | None:
    if not url.startswith("http"):
        url = "https://" + url
    return (parse_qs(urlparse(url).query).get("list") or [None])[0]


def safe_folder_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", name or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "Playlist"


def tmpl_literal(text: str) -> str:
    """Escape text so yt-dlp's output-template engine treats it as plain text."""
    return text.replace("%", "%%")


# ---------- library ----------

def library_available() -> bool:
    return LIBRARY_DIR.is_dir() and os.access(LIBRARY_DIR, os.W_OK)


def _chown(path: Path):
    try:
        os.chown(path, PUID, PGID)
    except (PermissionError, OSError):
        pass  # not running as root; file keeps the container user's ownership


def add_to_library(src: Path, *subdirs: str) -> str:
    """Move a finished MP3 into the music library. Returns the name it was saved as."""
    target_dir = LIBRARY_DIR / LIBRARY_SUBDIR
    for part in subdirs:
        target_dir = target_dir / part
    with library_lock:
        target_dir.mkdir(parents=True, exist_ok=True)
        d = target_dir
        while d != LIBRARY_DIR and LIBRARY_DIR in d.parents:
            _chown(d)
            d = d.parent
        dest = target_dir / src.name
        n = 1
        while dest.exists():  # never overwrite: "Song.mp3" -> "Song (1).mp3"
            dest = target_dir / f"{src.stem} ({n}){src.suffix}"
            n += 1
        shutil.move(str(src), dest)
        _chown(dest)
    return dest.name


# ---------- yt-dlp ----------

def build_opts(out_dir: Path, bitrate: str, progress_hook, tag_actions=None, name_prefix=""):
    def duration_filter(info, *, incomplete):
        duration = info.get("duration")
        if duration and duration > MAX_DURATION:
            return f"Too long ({duration // 60} min, limit is {MAX_DURATION // 60} min)."
        return None

    postprocessors = []
    if MetadataParserPP is not None:
        actions = tag_actions if tag_actions is not None else [
            # Keep YouTube Music's album/artist when present; otherwise fall back to
            # DEFAULT_ALBUM and the channel name so the music player groups songs nicely.
            (MetadataParserPP.Actions.INTERPRET, f"%(album|{tmpl_literal(DEFAULT_ALBUM)})s", "%(album)s"),
            (MetadataParserPP.Actions.INTERPRET, "%(artist|uploader)s", "%(artist)s"),
        ]
        postprocessors.append({"key": "MetadataParser", "when": "pre_process", "actions": actions})
    postprocessors += [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate},
        {"key": "FFmpegMetadata", "add_metadata": True},
        {"key": "EmbedThumbnail"},
    ]
    return {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / f"{tmpl_literal(name_prefix)}%(title).150s.%(ext)s"),
        "noplaylist": True,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
        "match_filter": duration_filter,
        "writethumbnail": True,
        "postprocessors": postprocessors,
    }


def download_one(url: str, out_dir: Path, bitrate: str, progress_hook, **kw) -> tuple[Path, dict]:
    """Download + convert a single video. Returns (mp3 path, info). Raises on failure."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with yt_dlp.YoutubeDL(build_opts(out_dir, bitrate, progress_hook, **kw)) as ydl:
        info = ydl.extract_info(url, download=True)
    if info is None:
        raise RuntimeError("Could not read video info.")
    mp3s = list(out_dir.glob("*.mp3"))
    if not mp3s:
        # match_filter skipped it (too long) or conversion failed
        raise RuntimeError(f"Too long (limit is {MAX_DURATION // 60} min)."
                           if (info.get("duration") or 0) > MAX_DURATION
                           else "No MP3 was produced.")
    return mp3s[0], info


def make_progress_hook(job_id: str, on_pct=None):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = round(done / total * 100, 1) if total else 0
            eta = d.get("eta")  # seconds left, calculated by yt-dlp from the download speed
            update_job(job_id, status="downloading", progress=pct,
                       eta=int(eta) if isinstance(eta, (int, float)) else None)
            if on_pct:
                on_pct(pct)
        elif d["status"] == "finished":
            update_job(job_id, status="converting", progress=100, eta=None)
    return hook


# ---------- jobs ----------

def run_single(job_id: str, url: str, bitrate: str):
    job_dir = DOWNLOAD_DIR / job_id
    try:
        mp3, info = download_one(url, job_dir, bitrate, make_progress_hook(job_id))
        title = info.get("title", "audio")
        if AUTO_ADD and library_available():
            saved = add_to_library(mp3)
            update_job(job_id, status="done", progress=100, title=title, file=None, saved_as=saved)
        else:
            update_job(job_id, status="done", progress=100, title=title, file=str(mp3))
    except Exception as e:  # noqa: BLE001 - report any failure to the UI
        update_job(job_id, status="error", error=clean_error(e))
        shutil.rmtree(job_dir, ignore_errors=True)


def run_playlist(job_id: str, url: str, bitrate: str):
    job_dir = DOWNLOAD_DIR / job_id
    try:
        list_id = playlist_id(url)
        list_url = f"https://www.youtube.com/playlist?list={list_id}" if list_id else url
        flat_opts = {"extract_flat": "in_playlist", "playlistend": MAX_PLAYLIST_ITEMS,
                     "quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(list_url, download=False)
        entries = [e for e in (info or {}).get("entries") or [] if e and e.get("id")]
        entries = entries[:MAX_PLAYLIST_ITEMS]
        if not entries:
            raise RuntimeError("That playlist is empty, private, or couldn't be read.")

        name = (info.get("title") or "Playlist").strip()
        folder = safe_folder_name(name)
        total = len(entries)
        width = max(2, len(str(total)))
        update_job(job_id, playlist_title=name, folder=folder, total=total, title=name)

        added, skipped = 0, []
        started = time.time()
        for i, entry in enumerate(entries, start=1):
            song_title = entry.get("title") or f"Song {i}"
            update_job(job_id, status="downloading", index=i, current_title=song_title,
                       progress=0, eta=None, overall=round((i - 1) / total * 100, 1),
                       overall_eta=_overall_eta(started, i - 1, total))

            def on_pct(pct, i=i):
                update_job(job_id, overall=round((i - 1 + pct / 100) / total * 100, 1))

            tag_actions = None
            if MetadataParserPP is not None:
                # Every song in the playlist becomes one album, in playlist order.
                tag_actions = [
                    (MetadataParserPP.Actions.INTERPRET, tmpl_literal(name), "%(album)s"),
                    (MetadataParserPP.Actions.INTERPRET, "Various Artists", "%(album_artist)s"),
                    (MetadataParserPP.Actions.INTERPRET, str(i), "%(track_number)s"),
                    (MetadataParserPP.Actions.INTERPRET, "%(artist|uploader)s", "%(artist)s"),
                ]
            song_dir = job_dir / str(i)
            try:
                mp3, song_info = download_one(
                    f"https://www.youtube.com/watch?v={entry['id']}", song_dir, bitrate,
                    make_progress_hook(job_id, on_pct), tag_actions=tag_actions,
                    name_prefix=f"{i:0{width}d} - ")
                add_to_library(mp3, folder)
                added += 1
                update_job(job_id, added=added, current_title=song_info.get("title") or song_title)
            except Exception as e:  # noqa: BLE001 - skip this song, keep going
                skipped.append({"title": song_title, "reason": clean_error(e)})
                update_job(job_id, skipped=skipped)
            finally:
                shutil.rmtree(song_dir, ignore_errors=True)

        if added == 0:
            raise RuntimeError("None of the songs in this playlist could be converted.")
        update_job(job_id, status="done", progress=100, overall=100, eta=None, overall_eta=None,
                   saved_as=folder, added=added, skipped=skipped)
    except Exception as e:  # noqa: BLE001 - report any failure to the UI
        update_job(job_id, status="error", error=clean_error(e))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _overall_eta(started: float, finished: int, total: int):
    if finished == 0:
        return None
    per_song = (time.time() - started) / finished
    return int(per_song * (total - finished))


def cleanup_loop():
    """Delete finished jobs and their temp files after FILE_TTL seconds (library files are kept)."""
    while True:
        now = time.time()
        expired = []
        with jobs_lock:
            for jid, job in list(jobs.items()):
                if now - job["created"] > FILE_TTL and job["status"] in ("done", "error"):
                    expired.append(jid)
                    del jobs[jid]
        for jid in expired:
            shutil.rmtree(DOWNLOAD_DIR / jid, ignore_errors=True)
        # Also clear orphaned folders (e.g. after a restart)
        for d in DOWNLOAD_DIR.iterdir():
            if d.is_dir() and now - d.stat().st_mtime > FILE_TTL and d.name not in jobs:
                shutil.rmtree(d, ignore_errors=True)
        time.sleep(300)


# ---------- routes ----------

@app.get("/")
def index():
    return render_template("index.html", default_bitrate=DEFAULT_BITRATE,
                           library=library_available(), navidrome_url=NAVIDROME_URL,
                           max_playlist=MAX_PLAYLIST_ITEMS)


@app.post("/api/convert")
def convert():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    bitrate = str(data.get("bitrate") or DEFAULT_BITRATE)
    mode = data.get("mode") or "single"

    if not YOUTUBE_RE.match(url):
        return jsonify(error="Please enter a valid YouTube video or playlist link."), 400
    if bitrate not in ALLOWED_BITRATES:
        bitrate = DEFAULT_BITRATE

    is_playlist_only = "/playlist" in url.lower()
    if is_playlist_only:
        mode = "playlist"
    if mode == "playlist":
        if not playlist_id(url):
            return jsonify(error="That link doesn't contain a playlist."), 400
        if not library_available():
            return jsonify(error="Playlists go straight to the music library, "
                                 "and the library folder isn't set up on the server."), 503

    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {"kind": mode, "status": "queued", "progress": 0, "title": None, "file": None,
                        "error": None, "created": time.time(), "saved_as": None, "eta": None}
        if mode == "playlist":
            jobs[job_id].update(index=0, total=None, current_title=None, overall=0,
                                overall_eta=None, added=0, skipped=[], folder=None)

    target = run_playlist if mode == "playlist" else run_single
    threading.Thread(target=target, args=(job_id, url, bitrate), daemon=True).start()
    return jsonify(job_id=job_id, mode=mode), 202


@app.get("/api/status/<job_id>")
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify(error="Job not found or expired."), 404
        return jsonify({k: v for k, v in job.items() if k != "file"})


@app.post("/api/library/<job_id>")
def save_to_library(job_id):
    if not library_available():
        return jsonify(error="The music library folder isn't set up on the server."), 503
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job["status"] != "done":
            return jsonify(error="This song isn't ready or has expired. Convert it again."), 404
        if job.get("saved_as"):
            return jsonify(saved_as=job["saved_as"])
        path = Path(job["file"]) if job["file"] else None
        job["file"] = None  # claim it so a double-click can't move it twice
    if not path or not path.exists():
        return jsonify(error="The converted file is gone. Convert it again."), 404
    try:
        saved = add_to_library(path)
    except OSError as e:
        update_job(job_id, file=str(path))
        return jsonify(error=f"Couldn't add it to the library: {e.strerror or e}"), 500
    update_job(job_id, saved_as=saved)
    return jsonify(saved_as=saved)


@app.get("/api/download/<job_id>")
def download(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done" or not job["file"]:
        abort(404)
    path = Path(job["file"])
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name, mimetype="audio/mpeg")


@app.get("/health")
def health():
    return {"ok": True}


threading.Thread(target=cleanup_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
