# RedNote Video Downloader

Free tool to download Xiaohongshu (RedNote / 小红书) videos without watermark. Supports regular videos AND Live Photos.

## Features

- ✅ Download RedNote videos without watermark
- ✅ Live Photo support (video streams embedded in image posts)
- ✅ 720p without login, 1080p/4K with cookies
- ✅ SEO-optimized pages (FAQ, How-To, 4K, HD, About)
- ✅ Docker support — deploy anywhere

## Tech Stack

- **Backend**: Python Flask + gunicorn
- **Video extraction**: yt-dlp + ffmpeg
- **Live Photo fallback**: Custom page scraper for `imageList[].stream`

## Quick Start (Local)

```bash
pip install -r requirements.txt
sudo apt install ffmpeg
python app.py
# Open http://localhost:5050
```

## Docker

```bash
docker build -t rednote-downloader .
docker run -p 5050:5050 rednote-downloader
```

## Deploy on Free Hosting

### Koyeb (Recommended — always on, no sleep)

1. Sign up at [koyeb.com](https://www.koyeb.com) with GitHub
2. Create Service → Select this GitHub repo
3. Builder: **Docker**
4. Port: **5050**
5. Deploy — your site will be live in 2-3 minutes!

### Render (Free tier — sleeps after 15 min idle)

1. Sign up at [render.com](https://render.com) with GitHub
2. New → Web Service → Select this repo
3. Runtime: **Docker**
4. Deploy

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `XHS_COOKIES_BROWSER` | Browser name for cookie extraction (e.g. `chrome`) | No — for 1080p/4K |
| `XHS_COOKIES_FILE` | Path to cookies.txt file | No — for 1080p/4K |

Without cookies: 720p works. With cookies: 1080p and 4K available.

## License

MIT — Free to use, modify, and distribute.
