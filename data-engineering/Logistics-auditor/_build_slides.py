"""One-off slide deck for the Veridi delivery audit. Not part of the app."""

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
PDF = ROOT / "veridi_delivery_audit.pdf"

NAVY = HexColor("#053762")
ORANGE = HexColor("#ff5a00")
INK = HexColor("#3e3d3a")
MUTED = HexColor("#6f6c66")
BG = HexColor("#fafafa")
W, H = 792, 612


def new_page(c: canvas.Canvas, page: int, pages: int) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(NAVY)
    c.rect(0, H - 10, W, 10, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.rect(0, 0, W, 8, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("Times-Roman", 9)
    c.drawString(36, 18, "Veridi Logistics  ·  Last mile delivery audit")
    c.drawRightString(W - 36, 18, f"{page} / {pages}")


def heading(c: canvas.Canvas, title: str, subtitle: str = "") -> float:
    c.setFillColor(NAVY)
    c.setFont("Times-Bold", 26)
    c.drawString(36, H - 52, title)
    y = H - 74
    if subtitle:
        c.setFillColor(INK)
        c.setFont("Times-Roman", 12)
        c.drawString(36, y, subtitle)
        y -= 18
    return y


def bullets(c: canvas.Canvas, items: list[str], y: float, size: int = 13) -> float:
    c.setFillColor(INK)
    c.setFont("Times-Roman", size)
    for item in items:
        c.setFillColor(ORANGE)
        c.circle(44, y + 3, 2.4, fill=1, stroke=0)
        c.setFillColor(INK)
        c.drawString(56, y, item)
        y -= 20
    return y


def draw_image(c: canvas.Canvas, name: str, x: float, y: float, width: float) -> None:
    img = ImageReader(str(OUT / name))
    iw, ih = img.getSize()
    height = width * ih / iw
    c.drawImage(img, x, y, width=width, height=height, preserveAspectRatio=True, mask="auto")


def build() -> None:
    c = canvas.Canvas(str(PDF), pagesize=(W, H))
    c.setTitle("Veridi Logistics delivery audit")
    pages = 6

    new_page(c, 1, pages)
    c.setFillColor(NAVY)
    c.setFont("Times-Bold", 32)
    c.drawString(36, 360, "Last mile delivery audit")
    c.setFillColor(ORANGE)
    c.rect(36, 342, 120, 4, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont("Times-Roman", 16)
    c.drawString(36, 310, "Are we failing specific regions, or the whole country?")
    c.setFont("Times-Roman", 13)
    lines = [
        "Of 96,470 packages that arrived, 6.8% missed the promised day.",
        "The typical package still arrived 12 days early.",
        "The miss is regional: the Northeast and Rio, not Brazil as a whole.",
        "Late packages sit next to lower reviews. That is a pattern, not a cause.",
    ]
    bullets(c, lines, 250, 14)
    c.setFillColor(MUTED)
    c.setFont("Times-Roman", 11)
    c.drawString(36, 70, "Olist public orders, September 2016 to October 2018. Product of the delivery performance audit.")
    c.showPage()

    new_page(c, 2, pages)
    heading(c, "The country is mostly on time", "Late means the arrival calendar day is after the promised day. Super late means more than five days.")
    draw_image(c, "delivery_status.png", 150, 70, 500)
    c.showPage()

    new_page(c, 3, pages)
    heading(c, "The miss is in some states", "The dashed line is Brazil, 6.8% of arrived packages. São Paulo is 4.5% on 40,494. Rio is 12.1% on 12,350.")
    draw_image(c, "late_rate_by_state.png", 36, 48, 720)
    c.showPage()

    new_page(c, 4, pages)
    heading(c, "A missed day sits next to a lower score", "4.29 on time, 2.99 when one to five days late, 1.74 when more than five days late.")
    draw_image(c, "review_score_vs_delay.png", 46, 70, 700)
    c.showPage()

    new_page(c, 5, pages)
    y = heading(c, "The date was not widened for the longer trip", "Candidate’s choice: promised lead time against the days the trip actually took.")
    draw_image(c, "promise_vs_actual_by_region.png", 300, 70, 460)
    c.setFillColor(INK)
    c.setFont("Times-Roman", 12)
    notes = [
        "The Northeast was promised",
        "about 31 days for a trip",
        "of about 20. The cushion",
        "stayed near 11 days, the",
        "same as the Southeast,",
        "where the trip takes",
        "about 11 days.",
        "",
        "The North was given a",
        "wider day and misses",
        "less often (8.6%) on a",
        "longer road.",
    ]
    yy = y - 8
    for line in notes:
        c.drawString(40, yy, line)
        yy -= 16
    c.showPage()

    new_page(c, 6, pages)
    y = heading(c, "What to do first", "The file shows where the promised day fails. It does not show why the road is slow.")
    bullets(
        c,
        [
            "Give a later day in the Northeast and in Rio de Janeiro.",
            "Treat a package that leaves the seller’s state differently: 8.0% late, against 4.5% when it stays.",
            "Do not rank a state by rate alone. Alagoas is 21.4% on 397 deliveries. Roraima, Acre, and Amapá are under 100.",
            "A later date will not clear every weak review. Most 1- and 2-star reviews are still on time.",
            "2,971 orders have no arrival. They stay in the file and are left out of the 6.8% rate.",
        ],
        y - 10,
        14,
    )
    c.save()
    print(PDF, PDF.stat().st_size)


if __name__ == "__main__":
    build()
