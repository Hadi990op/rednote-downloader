"""
RedNote Video Downloader — SEO-optimized self-hosted tool.
Flask backend with yt-dlp for video extraction/download.
Serves the downloader tool + SEO content pages.
"""
import os
import re
import uuid
import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse, unquote

import urllib.request

from flask import (
    Flask, render_template, request, jsonify,
    send_file, after_this_request, abort,
)

import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "rednote_downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

REDNOTE_HOSTS = {
    "www.xiaohongshu.com",
    "xiaohongshu.com",
    "xhslink.com",
    "www.xhslink.com",
}

# Cookie configuration for higher quality (1080p/4K)
_COOKIES_BROWSER = os.environ.get("XHS_COOKIES_BROWSER", "").strip() or None
_COOKIES_FILE = os.environ.get("XHS_COOKIES_FILE", "").strip() or None


def _ydl_base_opts() -> dict:
    opts: dict = {"quiet": True, "no_warnings": True}
    if _COOKIES_BROWSER:
        opts["cookiesfrombrowser"] = (_COOKIES_BROWSER,)
    elif _COOKIES_FILE:
        opts["cookiefile"] = _COOKIES_FILE
    return opts


def _auth_configured() -> bool:
    return bool(_COOKIES_BROWSER or _COOKIES_FILE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_url(raw: str) -> str | None:
    """Extract a RedNote URL from arbitrary input (share text, short links)."""
    raw = raw.strip()
    pattern = r"https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+"
    for match in re.findall(pattern, raw):
        match = match.rstrip(".,;:!?）)】》")
        try:
            from urllib.parse import urlparse
            host = urlparse(match).netloc.lower()
            if host in REDNOTE_HOSTS:
                return match
        except Exception:
            continue
    if raw.startswith("http"):
        return raw
    return None


def human_size(n: int | None) -> str:
    if not n:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def quality_label(f: dict) -> str:
    if f.get("format_id") == "direct":
        return "Original (source quality)"
    height = f.get("height")
    if height:
        if height >= 2160:
            tag = "4K · 2160p"
        elif height >= 1440:
            tag = f"2K · {height}p"
        elif height >= 1080:
            tag = f"Full HD · {height}p"
        elif height >= 720:
            tag = f"HD · {height}p"
        else:
            tag = f"{height}p"
    else:
        tag = f.get("format_note") or f.get("format_id") or "Unknown"
    parts = [tag]
    tbr = f.get("tbr")
    if tbr:
        parts.append(f"{tbr:.0f} kbps")
    ext = (f.get("ext") or "mp4").upper()
    parts.append(ext)
    vcodec = f.get("vcodec") or ""
    if vcodec and vcodec != "none":
        codec_short = vcodec.split(".")[0]
        if codec_short not in ("avc1", "mp4v", "h264"):
            parts.append(codec_short)
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Live Photo / image-stream fallback
# Xiaohongshu "Live Photos" store video inside imageList[].stream,
# NOT in note.video. yt-dlp only checks note.video, so it misses these.
# ---------------------------------------------------------------------------

_NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item)/([0-9a-f]+)")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _fetch_page_html(url: str) -> str:
    """Fetch the raw HTML of a Xiaohongshu post page."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _extract_live_photo_streams(url: str) -> dict | None:
    """
    Scrape a Xiaohongshu post page and extract Live Photo video streams
    from window.__INITIAL_STATE__.note.noteDetailMap.<id>.note.imageList[].stream.

    Returns a dict shaped like yt-dlp's info dict, or None if no video found.
    """
    m = _NOTE_ID_RE.search(url)
    if not m:
        return None
    note_id = m.group(1)

    try:
        html = _fetch_page_html(url)
    except Exception:
        return None

    # Extract __INITIAL_STATE__ JSON
    m = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*(.*?)(?:</script>)", html, re.DOTALL
    )
    if not m:
        return None
    raw_js = m.group(1)
    # JS → JSON cleanup
    raw_js = raw_js.replace("undefined", "null")
    try:
        state = json.loads(raw_js)
    except json.JSONDecodeError:
        return None

    note = (
        state.get("note", {})
        .get("noteDetailMap", {})
        .get(note_id, {})
        .get("note")
    )
    if not note:
        return None

    title = note.get("title") or note.get("desc") or "RedNote Live Photo"
    user = note.get("user", {})
    uploader = user.get("nickname", "")

    formats = []
    image_list = note.get("imageList") or []
    for img in image_list:
        stream = img.get("stream")
        if not stream:
            continue
        for codec_name, streams in stream.items():
            if not isinstance(streams, list):
                continue
            for s in streams:
                master = s.get("masterUrl")
                if not master:
                    continue
                # Unescape JSON unicode escapes if present
                master = master.replace("\\u002F", "/").replace("\\/", "/")
                quality = s.get("qualityType", codec_name.upper())
                fmt = {
                    "format_id": f"live_{codec_name}_{quality}",
                    "url": master,
                    "ext": "mp4",
                    "vcodec": codec_name,
                    "acodec": "none",  # Live photos are video-only
                    "height": None,
                    "width": None,
                    "format_note": f"Live Photo · {quality}",
                    "quality": 0,
                    "is_live_photo": True,
                    "backup_urls": [
                        b.replace("\\u002F", "/").replace("\\/", "/")
                        for b in (s.get("backupUrls") or [])
                    ],
                }
                formats.append(fmt)

    if not formats:
        return None

    # Sort: h264 first (most compatible), then by quality
    formats.sort(key=lambda f: (0 if f["vcodec"] == "h264" else 1))

    thumbnail = None
    if image_list and isinstance(image_list[0].get("urlDefault"), str):
        thumbnail = image_list[0]["urlDefault"].replace("\\u002F", "/")

    return {
        "id": note_id,
        "title": title,
        "uploader": uploader,
        "thumbnail": thumbnail,
        "duration": None,
        "formats": formats,
        "is_live_photo": True,
    }


def _download_live_photo(info: dict, format_id: str, output_path: Path) -> Path:
    """
    Download a Live Photo video stream directly via urllib.
    Returns the path to the downloaded file.
    """
    fmt = None
    for f in info["formats"]:
        if f["format_id"] == format_id:
            fmt = f
            break
    if not fmt:
        fmt = info["formats"][0]

    urls_to_try = [fmt["url"]] + fmt.get("backup_urls", [])
    last_err = None
    for u in urls_to_try:
        if not u:
            continue
        try:
            req = urllib.request.Request(
                u,
                headers={"User-Agent": _UA, "Referer": "https://www.xiaohongshu.com/"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            output_path.write_bytes(data)
            return output_path
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"Failed to download live photo: {last_err}")


# ---------------------------------------------------------------------------
# SEO Content Pages
# ---------------------------------------------------------------------------

SITE = {
    "name": "RedNote Video Downloader",
    "url": "https://cheese-leader-wink-fantasy.2n6.me/rnd/",
    "domain": "cheese-leader-wink-fantasy.2n6.me",
}


@app.route("/")
def index():
    """Main downloader tool page — targets 'rednote video downloader'."""
    return render_template(
        "index.html",
        site=SITE,
        auth_configured=_auth_configured(),
        active_page="home",
    )


@app.route("/without-watermark")
def without_watermark():
    """SEO page targeting 'rednote video downloader without watermark'."""
    return render_template(
        "without-watermark.html",
        site=SITE,
        active_page="without-watermark",
    )


@app.route("/download-4k")
def download_4k():
    """SEO page targeting 'rednote video download 4k' / 'rednote video downloader 4k'."""
    return render_template(
        "download-4k.html",
        site=SITE,
        active_page="download-4k",
    )


@app.route("/download-hd")
def download_hd():
    """SEO page targeting 'rednote video download hd'."""
    return render_template(
        "download-hd.html",
        site=SITE,
        active_page="download-hd",
    )


@app.route("/how-to-download")
def how_to_download():
    """SEO guide page targeting 'rednote video download' / 'how to download'."""
    return render_template(
        "how-to-download.html",
        site=SITE,
        active_page="how-to-download",
    )


@app.route("/faq")
def faq():
    """FAQ page for SEO long-tail + featured snippets."""
    return render_template(
        "faq.html",
        site=SITE,
        active_page="faq",
    )


@app.route("/about")
def about():
    return render_template(
        "about.html",
        site=SITE,
        active_page="about",
    )


# ---------------------------------------------------------------------------
# Legal Pages (AdSense requirement)
# ---------------------------------------------------------------------------

@app.route("/privacy-policy")
def privacy_policy():
    return render_template(
        "privacy-policy.html",
        site=SITE,
        active_page="privacy-policy",
    )


@app.route("/terms-of-service")
def terms_of_service():
    return render_template(
        "terms-of-service.html",
        site=SITE,
        active_page="terms-of-service",
    )


@app.route("/dmca")
def dmca():
    return render_template(
        "dmca.html",
        site=SITE,
        active_page="dmca",
    )


@app.route("/contact")
def contact():
    return render_template(
        "contact.html",
        site=SITE,
        active_page="contact",
    )


@app.route("/disclaimer")
def disclaimer():
    return render_template(
        "disclaimer.html",
        site=SITE,
        active_page="disclaimer",
    )


# ---------------------------------------------------------------------------
# Blog / Content Pages
# ---------------------------------------------------------------------------

@app.route("/blog")
def blog():
    return render_template(
        "blog.html",
        site=SITE,
        active_page="blog",
    )


@app.route("/blog/rednote-vs-tiktok-downloader")
def blog_rednote_vs_tiktok():
    return render_template(
        "blog/rednote-vs-tiktok-downloader.html",
        site=SITE,
        active_page="blog",
    )


@app.route("/blog/how-to-save-rednote-videos-iphone")
def blog_iphone():
    return render_template(
        "blog/how-to-save-rednote-videos-iphone.html",
        site=SITE,
        active_page="blog",
    )


@app.route("/blog/how-to-save-rednote-videos-android")
def blog_android():
    return render_template(
        "blog/how-to-save-rednote-videos-android.html",
        site=SITE,
        active_page="blog",
    )


@app.route("/blog/rednote-live-photo-download")
def blog_live_photo():
    return render_template(
        "blog/rednote-live-photo-download.html",
        site=SITE,
        active_page="blog",
    )


@app.route("/blog/rednote-video-formats-explained")
def blog_formats():
    return render_template(
        "blog/rednote-video-formats-explained.html",
        site=SITE,
        active_page="blog",
    )


@app.route("/blog/rednote-downloader-alternatives")
def blog_alternatives():
    return render_template(
        "blog/rednote-downloader-alternatives.html",
        site=SITE,
        active_page="blog",
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    """Health check endpoint for deployment platforms (Render, Koyeb, etc.)."""
    return jsonify({"status": "healthy"}), 200


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "auth_configured": _auth_configured(),
        "cookies_source": (
            f"browser:{_COOKIES_BROWSER}" if _COOKIES_BROWSER
            else f"file:{_COOKIES_FILE}" if _COOKIES_FILE
            else None
        ),
    })


@app.route("/api/info", methods=["POST"])
def api_info():
    body = request.get_json(force=True, silent=True) or {}
    raw = body.get("url", "").strip()
    if not raw:
        return jsonify({"error": "No URL provided."}), 400

    url = extract_url(raw)
    if not url:
        return jsonify({"error": "Could not find a valid RedNote URL in the input."}), 400

    ydl_opts = {**_ydl_base_opts(), "skip_download": True}

    info = None
    ydl_error = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        ydl_error = re.sub(r"ERROR:\s*\[.*?\]\s*", "", str(exc)).strip()
    except Exception as exc:
        ydl_error = str(exc)

    # Fallback: try Live Photo scraping if yt-dlp failed or found no formats
    if not info or not (info.get("formats") or []):
        live_info = _extract_live_photo_streams(url)
        if live_info:
            return _format_live_photo_response(url, live_info)

    if not info:
        return jsonify({"error": ydl_error or "Failed to extract video."}), 400

    raw_formats = info.get("formats") or []
    video_formats = sorted(
        (
            f for f in raw_formats
            if (f.get("vcodec") or "none") != "none" or f.get("format_id") == "direct"
        ),
        key=lambda f: (f.get("quality") or 0, f.get("height") or 0, f.get("tbr") or 0),
        reverse=True,
    )

    formats = [
        {
            "format_id": "direct/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            "label": "Best Available (auto-merge)",
            "height": None,
            "ext": "mp4",
            "filesize_str": "Varies",
            "has_audio": True,
            "is_best": True,
        }
    ]

    for f in video_formats:
        is_direct = f.get("format_id") == "direct"
        has_audio = is_direct or (f.get("acodec") or "none") != "none"
        formats.append(
            {
                "format_id": f["format_id"],
                "label": quality_label(f),
                "height": f.get("height"),
                "ext": f.get("ext") or "mp4",
                "filesize_str": human_size(f.get("filesize") or f.get("filesize_approx")),
                "has_audio": has_audio,
                "is_best": False,
            }
        )

    return jsonify(
        {
            "url": url,
            "title": info.get("title") or "Untitled",
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader") or info.get("creator") or "",
            "formats": formats,
            "auth_configured": _auth_configured(),
        }
    )


def _format_live_photo_response(url: str, live_info: dict):
    """Convert scraped Live Photo info into the API response format."""
    formats = []
    for i, f in enumerate(live_info["formats"]):
        is_best = i == 0
        formats.append({
            "format_id": f["format_id"],
            "label": f["format_note"] or f"Live Photo · {f.get('vcodec', 'h264').upper()}",
            "height": f.get("height"),
            "ext": f.get("ext") or "mp4",
            "filesize_str": "Varies",
            "has_audio": False,
            "is_best": is_best,
        })

    return jsonify({
        "url": url,
        "title": live_info["title"],
        "thumbnail": live_info.get("thumbnail"),
        "duration": live_info.get("duration"),
        "uploader": live_info.get("uploader") or "",
        "formats": formats,
        "auth_configured": _auth_configured(),
        "is_live_photo": True,
    })


@app.route("/api/download", methods=["POST"])
def api_download():
    body = request.get_json(force=True, silent=True) or {}
    url = body.get("url", "").strip()
    format_id = body.get("format_id") or "direct/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    title = body.get("title") or "rednote_video"

    if not url:
        return jsonify({"error": "No URL provided."}), 400

    # Check if this is a Live Photo download (format_id starts with "live_")
    if format_id.startswith("live_"):
        live_info = _extract_live_photo_streams(url)
        if not live_info:
            return jsonify({"error": "Could not extract Live Photo video stream."}), 400

        token = uuid.uuid4().hex
        output_path = DOWNLOAD_DIR / f"{token}.mp4"
        try:
            _download_live_photo(live_info, format_id, output_path)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)[:100].strip()
        download_name = f"{safe_title}.mp4" if safe_title else "rednote_live_photo.mp4"

        @after_this_request
        def _cleanup(response):
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return response

        return send_file(
            output_path,
            as_attachment=True,
            download_name=download_name,
            mimetype="video/mp4",
        )

    # Standard yt-dlp download path
    token = uuid.uuid4().hex
    output_tmpl = str(DOWNLOAD_DIR / f"{token}.%(ext)s")

    ydl_opts = {
        **_ydl_base_opts(),
        "format": format_id,
        "outtmpl": output_tmpl,
        "merge_output_format": "mp4",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        msg = re.sub(r"ERROR:\s*\[.*?\]\s*", "", str(exc)).strip()
        # Fallback: try Live Photo download
        live_info = _extract_live_photo_streams(url)
        if live_info:
            output_path = DOWNLOAD_DIR / f"{token}.mp4"
            try:
                _download_live_photo(live_info, live_info["formats"][0]["format_id"], output_path)
                safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)[:100].strip()
                download_name = f"{safe_title}.mp4" if safe_title else "rednote_live_photo.mp4"

                @after_this_request
                def _cleanup_live(response):
                    try:
                        os.unlink(output_path)
                    except OSError:
                        pass
                    return response

                return send_file(
                    output_path,
                    as_attachment=True,
                    download_name=download_name,
                    mimetype="video/mp4",
                )
            except Exception:
                pass
        return jsonify({"error": msg}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    candidates = list(DOWNLOAD_DIR.glob(f"{token}.*"))
    if not candidates:
        return jsonify({"error": "Download completed but output file was not found."}), 500

    file_path = candidates[0]
    ext = file_path.suffix.lstrip(".")
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)[:100].strip()
    download_name = f"{safe_title}.{ext}" if safe_title else f"rednote_video.{ext}"

    @after_this_request
    def _cleanup(response):
        try:
            os.unlink(file_path)
        except OSError:
            pass
        return response

    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="video/mp4",
    )


# ---------------------------------------------------------------------------
# SEO Files
# ---------------------------------------------------------------------------

@app.route("/robots.txt")
def robots():
    return app.send_static_file("robots.txt")


@app.route("/sitemap.xml")
def sitemap():
    return app.send_static_file("sitemap.xml")


@app.route("/llms.txt")
def llms_txt():
    return app.send_static_file("llms.txt")


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5050)
