"""عبوري داونلودر — Social media & YouTube downloader backend.

FastAPI + yt-dlp. Endpoints:
  GET  /                      -> frontend
  GET  /api/search?q=...      -> search YouTube, return candidates
  GET  /api/info?url=...      -> title/thumbnail/duration for a pasted link
  GET  /api/formats?url=...   -> available format presets for a URL
  POST /api/download          -> {url, preset} -> downloads & streams the file
"""
import asyncio
import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import yt_dlp

# ---------------------------------------------------------------- presets
# preset id -> (label, yt-dlp format selector, needs_merge, postprocessors)
# نستخدم محددات متساهلة + تحويل ffmpeg مضمّن، مع بدائل تلقائية عند الفشل.
PRESETS = {
    "video_best": (
        "🎬 فيديو — أعلى جودة (MP4)",
        "bv*+ba/b",
        True,
        [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    ),
    "video_1080": (
        "🎬 فيديو — 1080p (MP4)",
        "bv*[height<=1080]+ba/b[height<=1080]",
        True,
        [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    ),
    "video_720": (
        "🎬 فيديو — 720p (MP4)",
        "bv*[height<=720]+ba/b[height<=720]",
        True,
        [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    ),
    "video_480": (
        "🎬 فيديو — 480p (MP4)",
        "bv*[height<=480]+ba/b[height<=480]",
        True,
        [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
    ),
    "audio_mp3": (
        "🎵 صوت — MP3",
        "ba/b",
        False,
        [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
    ),
    "audio_m4a": (
        "🎵 صوت — M4A (أصلي بدون تحويل)",
        "ba[ext=m4a]/ba/b",
        False,
        [],
    ),
}

# بدائل تلقائية إذا رفض يوتيوب المحدد الأساسي
FORMAT_FALLBACKS = {
    "video_best": ["b[ext=mp4]/b", "b"],
    "video_1080": ["b[height<=1080][ext=mp4]/b[height<=1080]", "b[height<=1080]", "b"],
    "video_720": ["b[height<=720][ext=mp4]/b[height<=720]", "b[height<=720]", "b"],
    "video_480": ["b[height<=480][ext=mp4]/b[height<=480]", "b[height<=480]", "b"],
    "audio_mp3": ["ba[ext=m4a]/ba", "b"],
    "audio_m4a": ["ba", "b"],
}

app = FastAPI(title="عبوري داونلودر")

BASE_YDL = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "socket_timeout": 30,
    # تحمّل خنق يوتيوب المؤقت للـ IP
    "retries": 10,
    "fragment_retries": 10,
    "retry_sleep": {"http": "exp=1:10", "fragment": "exp=1:10"},
    "geo_bypass": True,
    # يلتف حول فحص "Sign in to confirm you're not a bot" من يوتيوب
    "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
}

# دعم ملف كوكيز (يفك حظر "Sign in to confirm you're not a bot" من يوتيوب) —
# يُقرأ من متغير البيئة COOKIES_FILE، أو تلقائياً من /etc/secrets/cookies.txt
# (ملف سري بـ Render) أو ./cookies.txt بجانب التطبيق.
def _find_cookies():
    env = os.environ.get("COOKIES_FILE", "").strip()
    for cand in [env, "/etc/secrets/cookies.txt",
                 str(Path(__file__).parent / "cookies.txt")]:
        if cand and os.path.exists(cand):
            # ملفات Render السرية للقراءة فقط، وyt-dlp يحاول الكتابة عليها —
            # ننسخها لمجلد مؤقت قابل للكتابة أولاً.
            if cand.startswith("/etc/secrets/"):
                dest = os.path.join(tempfile.gettempdir(), "cookies.txt")
                try:
                    shutil.copyfile(cand, dest)
                    return dest
                except Exception:
                    continue
            return cand
    return None


_COOKIES = _find_cookies()
if _COOKIES:
    BASE_YDL["cookiefile"] = _COOKIES


# ffmpeg مضمّن عبر imageio-ffmpeg (ضروري للدمج والتحويل على Render)
def _find_ffmpeg():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


_FFMPEG = _find_ffmpeg()
if _FFMPEG:
    BASE_YDL["ffmpeg_location"] = _FFMPEG


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "Sign in to confirm" in msg or "not a bot" in msg:
        return ("يوتيوب حظر السيرفر مؤقتاً (فحص بوت). الحل: أضف ملف كوكيز "
                "بـ Render (Secret Files ← cookies.txt) ثم أعد النشر.")
    # نظّف بادئة ERROR: [youtube] المزعجة
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"\[youtube\]\s*\S*:\s*", "", msg)
    return msg.strip() or "تعذر قراءة الرابط"

SAFE_NAME = re.compile(r"[^A-Za-z0-9\u0600-\u06FF _.\-()\[\]]+")


def safe_filename(name: str, ext: str, limit: int = 120) -> str:
    name = SAFE_NAME.sub("", name).strip() or "download"
    if len(name) > limit:
        name = name[:limit].rstrip()
    return f"{name}.{ext}"


def _search_sync(query: str, limit: int = 8):
    opts = {**BASE_YDL, "extract_flat": "in_playlist"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    out = []
    for e in (data.get("entries") or []):
        if not e or e.get("_type") == "playlist":
            continue
        vid = e.get("id") or ""
        out.append(
            {
                "id": vid,
                "title": e.get("title") or "بدون عنوان",
                "channel": e.get("channel") or e.get("uploader") or "",
                "duration": e.get("duration"),
                "thumbnail": (e.get("thumbnails") or [{}])[-1].get("url") if e.get("thumbnails") else e.get("thumbnail"),
                "url": e.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else ""),
            }
        )
    return out


def _info_sync(url: str):
    opts = {**BASE_YDL, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        raise ValueError("تعذر قراءة الرابط")
    thumb = None
    if info.get("thumbnails"):
        thumb = info["thumbnails"][-1].get("url")
    return {
        "title": info.get("title") or "بدون عنوان",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": info.get("duration"),
        "thumbnail": thumb or info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or url,
    }


def _download_sync(url: str, preset_id: str):
    label, fmt, _merge, postprocessors = PRESETS[preset_id]
    if not _FFMPEG and postprocessors:
        # بدون ffmpeg لا دمج ولا تحويل — نحمّل أفضل ملف جاهز مباشرة
        postprocessors = []
    selectors = [fmt] + FORMAT_FALLBACKS.get(preset_id, ["b"])
    last_exc = None
    for sel in selectors:
        try:
            return _try_download(url, sel, postprocessors)
        except Exception as exc:
            if "format" in str(exc).lower() and "not available" in str(exc).lower():
                last_exc = exc
                continue
            raise
    raise last_exc if last_exc else ValueError("فشل التحميل")


def _try_download(url: str, fmt: str, postprocessors):
    tmpdir = tempfile.mkdtemp(prefix="aboury_dl_")
    try:
        opts = {
            **BASE_YDL,
            "format": fmt,
            "outtmpl": os.path.join(tmpdir, "%(title).80s.%(ext)s"),
            "postprocessors": postprocessors,
            "restrictfilenames": False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # postprocessor may change the extension (e.g. mp3 conversion)
            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                for ext in ("mp3", "m4a", "mp4", "webm", "mkv"):
                    cand = base + "." + ext
                    if os.path.exists(cand):
                        filename = cand
                        break
            if not os.path.exists(filename):
                # fall back: take the newest file in tmpdir
                files = sorted(Path(tmpdir).glob("*"), key=os.path.getmtime)
                files = [f for f in files if f.is_file()]
                if not files:
                    raise ValueError("فشل التحميل: لم يتم إنشاء ملف")
                filename = str(files[-1])
        return tmpdir, filename, info.get("title") or "download"
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise


class DownloadRequest(BaseModel):
    url: str
    preset: str


# ------------------------------------------------------------------ routes
@app.get("/api/search")
async def search(q: str = Query(..., min_length=2, max_length=200)):
    try:
        results = await asyncio.to_thread(_search_sync, q)
    except Exception as exc:
        raise HTTPException(502, f"خطأ في البحث: {exc}")
    return {"results": results}


@app.get("/api/info")
async def info(url: str = Query(..., min_length=8, max_length=2000)):
    try:
        data = await asyncio.to_thread(_info_sync, url)
    except Exception as exc:
        raise HTTPException(502, _friendly_error(exc))
    return data


@app.get("/api/formats")
async def formats(url: str = Query(..., min_length=8, max_length=2000)):
    # Validate the URL is readable first, then return the preset list.
    try:
        data = await asyncio.to_thread(_info_sync, url)
    except Exception as exc:
        raise HTTPException(502, _friendly_error(exc))
    return {
        "info": data,
        "presets": [{"id": pid, "label": label} for pid, (label, *_rest) in PRESETS.items()],
    }


@app.post("/api/download")
async def download(req: DownloadRequest):
    if req.preset not in PRESETS:
        raise HTTPException(400, "صيغة غير مدعومة")
    if len(req.url) > 2000:
        raise HTTPException(400, "الرابط طويل جداً")
    try:
        tmpdir, filepath, title = await asyncio.to_thread(_download_sync, req.url, req.preset)
    except Exception as exc:
        raise HTTPException(502, f"فشل التحميل: {_friendly_error(exc)}")

    ext = os.path.splitext(filepath)[1].lstrip(".") or "bin"
    dl_name = safe_filename(title, ext)

    from starlette.background import BackgroundTask

    response = FileResponse(filepath, filename=dl_name)
    response.background = BackgroundTask(shutil.rmtree, tmpdir, True)
    return response


@app.get("/api/health")
async def health():
    return {"ok": True}


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
