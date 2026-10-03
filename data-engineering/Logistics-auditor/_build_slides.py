"""One-off slide deck for the Veridi delivery audit. Not part of the app."""

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
PDF = ROOT / "veridi_delivery_audit.pdf"
LOGO = ROOT / "assets" / "veridi-logo.png"

pdfmetrics.registerFont(TTFont("Segoe", r"C:\Windows\Fonts\segoeui.ttf"))
pdfmetrics.registerFont(TTFont("Segoe-Bold", r"C:\Windows\Fonts\segoeuib.ttf"))

NAVY = HexColor("#053762")
ORANGE = HexColor("#ff5a00")
INK = HexColor("#3e3d3a")
MUTED = HexColor("#6f6c66")
BG = HexColor("#f7f6f4")
CARD = white
W, H = 792, 612


def wrap(text: str, font: str, size: int, width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = word if not current else f"{current} {word}"
        if pdfmetrics.stringWidth(trial, font, size) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def centered(c: canvas.Canvas, text: str, y: float, font: str, size: int, color) -> None:
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawCentredString(W / 2, y, text)


def centered_block(c: canvas.Canvas, text: str, y: float, font: str, size: int, color, width: float, leading: float) -> float:
    for line in wrap(text, font, size, width):
        centered(c, line, y, font, size, color)
        y -= leading
    return y


def frame(c: canvas.Canvas, page: int | None, pages: int) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.rect(0, H - 8, W, 8, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.rect(0, 0, W, 6, fill=1, stroke=0)
    if page is None:
        return
    c.setFillColor(MUTED)
    c.setFont("Segoe", 9)
    c.drawString(36, 18, "Veridi Logistics")
    c.drawRightString(W - 36, 18, f"{page}  /  {pages}")


def content_title(c: canvas.Canvas, title: str, subtitle: str = "") -> float:
    centered(c, title, H - 48, "Segoe-Bold", 24, NAVY)
    c.setFillColor(ORANGE)
    c.rect(W / 2 - 28, H - 60, 56, 3, fill=1, stroke=0)
    y = H - 82
    if subtitle:
        y = centered_block(c, subtitle, y, "Segoe", 11, MUTED, 640, 15)
        y -= 8
    return y


def place_image(c: canvas.Canvas, name: str, top: float, bottom: float, side: float = 40) -> None:
    img = ImageReader(str(OUT / name))
    iw, ih = img.getSize()
    max_w = W - 2 * side
    max_h = top - bottom
    scale = min(max_w / iw, max_h / ih)
    width, height = iw * scale, ih * scale
    c.drawImage(
        img,
        (W - width) / 2,
        bottom + (max_h - height) / 2,
        width=width,
        height=height,
        preserveAspectRatio=True,
        mask="auto",
    )


def logo(c: canvas.Canvas, y: float, width: float = 210) -> None:
    img = ImageReader(str(LOGO))
    iw, ih = img.getSize()
    height = width * ih / iw
    c.drawImage(img, (W - width) / 2, y, width=width, height=height, mask="auto", preserveAspectRatio=True)


def build() -> None:
    c = canvas.Canvas(str(PDF), pagesize=(W, H))
    c.setTitle("Veridi Logistics delivery audit")
    pages = 6

    frame(c, None, pages)
    logo(c, 430, 230)
    centered(c, "DELIVERY PERFORMANCE AUDIT", 392, "Segoe", 11, ORANGE)
    centered(c, "Last mile delivery audit", 348, "Segoe-Bold", 32, NAVY)
    c.setFillColor(ORANGE)
    c.rect(W / 2 - 36, 328, 72, 3, fill=1, stroke=0)
    centered_block(
        c,
        "Are we failing specific regions, or the whole country?",
        300,
        "Segoe",
        15,
        INK,
        560,
        20,
    )
    stats = (
        ("6.8%", "missed the promised day"),
        ("12 days", "early, the typical package"),
        ("Regional", "the Northeast and Rio"),
    )
    for index, (value, label) in enumerate(stats):
        x = W / 2 + (index - 1) * 210
        c.setFillColor(NAVY)
        c.setFont("Segoe-Bold", 22)
        c.drawCentredString(x, 188, value)
        c.setFillColor(MUTED)
        c.setFont("Segoe", 10)
        c.drawCentredString(x, 168, label)
    centered(c, "Olist public orders  ·  September 2016 to October 2018", 78, "Segoe", 10, MUTED)
    c.showPage()

    frame(c, 2, pages)
    top = content_title(
        c,
        "The country is mostly on time",
        "Late means the arrival day is after the promised day. Super late means more than five days.",
    )
    place_image(c, "delivery_status.png", top, 40)
    c.showPage()

    frame(c, 3, pages)
    top = content_title(
        c,
        "The miss is in some states",
        "The dashed line is Brazil, 6.8% of arrived packages. São Paulo is 4.5% on 40,494. Rio is 12.1% on 12,350.",
    )
    place_image(c, "late_rate_by_state.png", top, 36)
    c.showPage()

    frame(c, 4, pages)
    top = content_title(
        c,
        "A missed day sits next to a lower score",
        "4.29 on time, 2.99 when one to five days late, and 1.74 when more than five days late.",
    )
    place_image(c, "review_score_vs_delay.png", top, 40)
    c.showPage()

    frame(c, 5, pages)
    top = content_title(
        c,
        "The longer trip was not given a later day",
        "The Northeast was promised about 31 days for a trip of about 20. The cushion stayed near 11 days, the same as the Southeast. The North was given a wider day and misses less often, 8.6%, on a longer road.",
    )
    place_image(c, "promise_vs_actual_by_region.png", top, 40)
    c.showPage()

    frame(c, None, pages)
    logo(c, 500, 150)
    centered(c, "WHAT TO DO FIRST", 458, "Segoe", 11, ORANGE)
    centered(c, "Widen the date where the trip is longer", 422, "Segoe-Bold", 26, NAVY)
    c.setFillColor(ORANGE)
    c.rect(W / 2 - 28, 404, 56, 3, fill=1, stroke=0)
    centered_block(
        c,
        "The promised day fails in the Northeast and in Rio. It does not fail for Brazil as a whole.",
        376,
        "Segoe",
        13,
        INK,
        560,
        18,
    )
    actions = (
        ("01", "Give a later day in the Northeast and in Rio de Janeiro."),
        ("02", "A package that leaves the seller’s state is 8.0% late, against 4.5% when it stays."),
        ("03", "Do not rank a small state by rate alone. Alagoas is 21.4% on 397 deliveries."),
        ("04", "A later date will not clear every weak review. Most weak reviews are still on time."),
    )
    y = 300
    block_w = 520
    left = (W - block_w) / 2
    for number, text in actions:
        c.setFillColor(ORANGE)
        c.setFont("Segoe-Bold", 12)
        c.drawString(left, y, number)
        c.setFillColor(INK)
        c.setFont("Segoe", 12)
        lines = wrap(text, "Segoe", 12, block_w - 36)
        for line in lines:
            c.drawString(left + 32, y, line)
            y -= 16
        y -= 10
    centered(c, "2,971 orders have no arrival. They stay in the file and are left out of the 6.8% rate.", 78, "Segoe", 10, MUTED)
    c.save()
    print(PDF, PDF.stat().st_size)


if __name__ == "__main__":
    build()
