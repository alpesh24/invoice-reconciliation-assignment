"""Render the generated fictional invoices from data/generated/invoice-records.json (Pillow).

Extends data/inputs/render_invoices.py to several lines. Same canvas, fonts, colours and header band; the two
layouts stay recognisable. Writes data/generated/images/<file_id>.png. Deterministic: no randomness.
Run: python scripts/render_generated.py
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
font = ImageFont.load_default(size=22)
title = ImageFont.load_default(size=32)


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def table(d, x: int, y: int, lines: list[dict]) -> int:
    """Draw header + one row per line; return the y below the last row."""
    cols = [x, x + 190, x + 300, x + 500]
    for cx, text in zip(cols, ["SKU", "Qty", "Unit price (USD)", "Line total (USD)"]):
        d.text((cx, y), text, font=font, fill="black")
    d.line((x, y + 32, x + 700, y + 32), fill="black", width=1)
    y += 45
    for ln in lines:
        for cx, text in zip(cols, [ln["sku"], str(ln["quantity"]), money(ln["unit_cents"]), money(ln["line_total_cents"])]):
            d.text((cx, y), text, font=font, fill="black")
        y += 42
    return y


def render(inv: dict) -> Image.Image:
    b = inv["layout"] == "b"
    im = Image.new("RGB", (950, 650), "#ffffff")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 950, 100), fill="#e4edf5" if b else "#edf0e6")
    d.text((40, 30), "FICTIONAL INVOICE - " + inv["invoice_number"], font=title, fill="black")
    head = [("Supplier", inv["supplier_id"]), ("Purchase order", inv["po_id"] or "(missing)")]
    if not b:  # layout a: vertical header fields, then table, then total
        for i, (k, v) in enumerate(head):
            d.text((60, 140 + i * 50), f"{k}: {v}", font=font, fill="black")
        y = table(d, 60, 260, inv["lines"])
        d.text((60, y + 30), f"Total (USD): {money(inv['total_cents'])}", font=font, fill="black")
    else:  # layout b: two-column header fields, then line rows, then total
        for i, (k, v) in enumerate(head):
            d.text((40 if i == 0 else 480, 155), f"{k}: {v}", font=font, fill="black")
        y = table(d, 40, 260, inv["lines"])
        d.text((480, y + 30), f"Total (USD): {money(inv['total_cents'])}", font=font, fill="black")
    return im


def main() -> None:
    out = GEN / "images"
    out.mkdir(exist_ok=True)
    for inv in json.loads((GEN / "invoice-records.json").read_text(encoding="utf-8")):
        render(inv).save(out / (inv["file_id"] + ".png"))
        print("rendered", inv["file_id"])


if __name__ == "__main__":
    main()
