"""A small PDF writer for one-page documents such as receipts (no third-party library).

Text uses the PDF standard fonts Helvetica and Helvetica-Bold, which every PDF reader has, so
nothing is embedded. Characters outside Latin-1 are replaced with "?".
"""
from dataclasses import dataclass, field

PAGE_W, PAGE_H = 595, 842  # A4 in points


def _hex_rgb(colour: str) -> str:
    colour = colour.lstrip("#")
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return f"{r:.3f} {g:.3f} {b:.3f}"


def _text(value: str) -> str:
    raw = str(value).encode("latin-1", "replace").decode("latin-1")
    return raw.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_width(value: str, size: float, bold: bool = False) -> float:
    """Close enough for right-aligning amounts: Helvetica digits are 0.556 em wide."""
    narrow = set("il.,:;'|!I ")
    wide = set("MWmw@%")
    em = sum(0.28 if c in narrow else 0.83 if c in wide else 0.556 for c in str(value))
    return em * size * (1.05 if bold else 1.0)


@dataclass
class Page:
    """Draw on one A4 page; y is measured from the top, as on screen."""

    ops: list[str] = field(default_factory=list)

    def rect(self, x, y, w, h, fill="#000000"):
        self.ops.append(f"{_hex_rgb(fill)} rg {x:.1f} {PAGE_H - y - h:.1f} {w:.1f} {h:.1f} re f")

    def line(self, x1, y, x2, colour="#E1E6ED", width=0.8):
        self.ops.append(f"{_hex_rgb(colour)} RG {width} w {x1:.1f} {PAGE_H - y:.1f} m "
                        f"{x2:.1f} {PAGE_H - y:.1f} l S")

    def text(self, x, y, value, size=10.0, bold=False, colour="#0E1B30", align="left"):
        if align == "right":
            x -= text_width(value, size, bold)
        font = "F2" if bold else "F1"
        self.ops.append(f"BT {_hex_rgb(colour)} rg /{font} {size} Tf "
                        f"{x:.1f} {PAGE_H - y:.1f} Td ({_text(value)}) Tj ET")


def render(page: Page, title: str = "") -> bytes:
    """The page as a complete PDF file."""
    content = "\n".join(page.ops).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
         "/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>").encode(),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        (b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
         b"/Encoding /WinAnsiEncoding >>"),
        f"<< /Title ({_text(title)}) /Producer (SecurePay) >>".encode("latin-1"),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, len(objects), xref))
    return bytes(out)
