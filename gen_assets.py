"""Generate social share (OG) image and favicon for RedNote Video Downloader."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STATIC_IMG = Path(__file__).resolve().parent / "static" / "img"
STATIC_IMG.mkdir(parents=True, exist_ok=True)

W, H = 1200, 630


def load_font(size, bold=True):
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_og():
    img = Image.new("RGB", (W, H), (17, 19, 38))
    draw = ImageDraw.Draw(img)

    # Accent gradient bar top
    draw.rectangle([0, 0, W, 12], fill=(255, 79, 110))

    # Card
    rounded_rect(draw, [80, 150, W - 80, H - 150], 28, (30, 33, 58))

    # Logo badge
    draw.ellipse([120, 200, 200, 280], fill=(255, 79, 110))
    draw.text((160 - 28, 240 - 34), "R", font=load_font(64), fill=(255, 255, 255))

    # Title
    draw.text((240, 205), "RedNote Video Downloader", font=load_font(54), fill=(255, 255, 255))
    draw.text((240, 280), "Download Xiaohongshu videos", font=load_font(34), fill=(200, 206, 235))
    draw.text((240, 330), "without watermark - HD & 4K", font=load_font(34), fill=(200, 206, 235))

    # Badges
    badges = ["No Watermark", "HD & 4K", "Free Forever", "No Signup"]
    bx = 120
    by = H - 230
    for b in badges:
        tw = draw.textlength(b, font=load_font(26))
        rounded_rect(draw, [bx, by, bx + tw + 40, by + 52], 26, (45, 49, 82))
        draw.text((bx + 20, by + 11), b, font=load_font(26), fill=(255, 255, 255))
        bx += tw + 70

    img.save(STATIC_IMG / "og-image.png", "PNG")
    print("Wrote", STATIC_IMG / "og-image.png")


def make_favicon():
    size = 64
    img = Image.new("RGBA", (size, size), (17, 19, 38, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([6, 6, size - 6, size - 6], fill=(255, 79, 110, 255))
    draw.text((size / 2 - 18, size / 2 - 22), "R", font=load_font(40), fill=(255, 255, 255, 255))
    img.save(STATIC_IMG / "favicon.ico", "ICO", sizes=[(64, 64)])
    print("Wrote", STATIC_IMG / "favicon.ico")


if __name__ == "__main__":
    make_og()
    make_favicon()
