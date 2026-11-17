"""Branded HTML for every email the gateway sends, made from the plain-text body.

Each sender (receipts, verification codes, guest status codes, password resets, staff
notices) writes a plain-text body as before. This backend adds an HTML version in the
SecurePay look before handing the message to the real backend (SMTP to Mailpit on the
servers), so the text and HTML can never say different things and no sender changes.

Formatting rules, all from the text itself:
- blank lines separate paragraphs;
- "Label:   value" lines (a colon then two or more spaces) become a two-column table;
- a line that is only a URL becomes a button;
- "Items:" followed by indented "name  price" lines becomes an item table;
- a subject like "123456 is your SecurePay verification code" shows the code in a large box.
The body is HTML-escaped first, so nothing in it (a shop name, an item name) can inject
markup.

The header shows the SecurePay mark (frontend/brand, sprint 12 branding kit) as a small PNG
sent inside the email itself (multipart/related, cid:), so it shows without loading anything
from the internet, also in Mailpit.
"""
import re
from email.mime.image import MIMEImage
from functools import cache
from html import escape
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.mail.backends.base import BaseEmailBackend

NAVY, INK, SAFFRON, MUTED, LINE, PAPER = ("#0F2240", "#0A1830", "#F5A524", "#5B6475",
                                          "#E6E1D8", "#FAF8F4")
_FIELD = re.compile(r"^([A-Z][\w ()/'-]{0,30}):\s{2,}(.+)$")
_URL = re.compile(r"^https?://\S+$")
_ITEM = re.compile(r"^\s{2,}\S.*\S\s{2,}\S+$")
_CODE_SUBJECT = re.compile(r"^(\d{4,8}) is your ")

LOGO_CID = "securepay-mark"
LOGO_PATH = Path(__file__).resolve().parent / "brand" / "securepay-mark-56.png"

FOOTER = ("SecurePay is a payment gateway built for the CSIT321 final-year project. Payments "
          "are simulated: no real money moves. We never ask for your card details or a code "
          "by phone or message.")


def _button(url: str) -> str:
    url = escape(url.strip(), quote=True)
    return (f'<p style="margin:6px 0 8px"><a href="{url}" style="display:inline-block;'
            f'background:{NAVY};color:#ffffff;text-decoration:none;font-weight:600;'
            f'padding:11px 22px;border-radius:999px">Open the page</a></p>'
            f'<p style="margin:0 0 18px;font-size:12px;color:{MUTED};word-break:break-all">'
            f"{url}</p>")


def _text(lines: list[str]) -> str:
    text = "<br>".join(escape(line.strip()) for line in lines)
    return f'<p style="margin:0 0 16px;line-height:1.55">{text}</p>'


def _item_rows(lines: list[str]) -> str:
    rows = "".join(
        f'<tr><td style="padding:4px 0;color:{INK}">{escape(name)}</td>'
        f'<td style="padding:4px 0;color:{INK};text-align:right;white-space:nowrap">'
        f"{escape(price)}</td></tr>"
        for name, price in (re.split(r"\s{2,}", line.strip(), maxsplit=1) for line in lines))
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 16px;font-size:14px">{rows}</table>')


def _paragraph(lines: list[str]) -> str:
    fields = [m for m in (_FIELD.match(line) for line in lines) if m]
    if fields and len(fields) == len(lines):
        rows = "".join(
            f'<tr><td style="padding:6px 0;color:{MUTED};width:38%;vertical-align:top">'
            f'{escape(m.group(1))}</td><td style="padding:6px 0;color:{INK};font-weight:600">'
            f"{escape(m.group(2))}</td></tr>" for m in fields)
        return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                f'style="border-top:1px solid {LINE};border-bottom:1px solid {LINE};'
                f'margin:4px 0 18px;font-size:14px">{rows}</table>')
    # "Items:" then indented "name  price" lines (receipts).
    if (len(lines) > 1 and lines[0].rstrip().endswith(":")
            and all(_ITEM.match(line) for line in lines[1:])):
        return (f'<p style="margin:0 0 6px;font-weight:600">{escape(lines[0].strip())}</p>'
                + _item_rows(lines[1:]))
    out, run = [], []
    for line in lines:
        if _URL.match(line.strip()):
            if run:
                out.append(_text(run))
                run = []
            out.append(_button(line))
        else:
            run.append(line)
    if run:
        out.append(_text(run))
    return "".join(out)


@cache
def _logo_bytes() -> bytes:
    return LOGO_PATH.read_bytes()


def _logo(with_image: bool) -> str:
    if with_image:
        return (f'<img src="cid:{LOGO_CID}" width="28" height="28" alt="" '
                f'style="display:inline-block;vertical-align:middle;border:0;margin:-3px 8px 0 0">')
    return f'<span style="color:{SAFFRON}">&#9670;</span> '


def html_for(subject: str, text: str, logo: bool = False) -> str:
    blocks: list[list[str]] = [[]]
    for line in text.splitlines():
        if line.strip():
            blocks[-1].append(line)
        elif blocks[-1]:
            blocks.append([])
    body = "".join(_paragraph(b) for b in blocks if b)
    code = _CODE_SUBJECT.match(subject)
    if code:
        body = (f'<p style="margin:0 0 18px;text-align:center"><span style="display:inline-block;'
                f'font-family:Menlo,Consolas,monospace;font-size:30px;font-weight:700;'
                f'letter-spacing:8px;color:{INK};background:{PAPER};border:1px solid {LINE};'
                f'border-radius:12px;padding:12px 22px">{escape(code.group(1))}</span></p>'
                + body)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{PAPER};font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;color:{INK}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}">
<tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
<tr><td style="background:{NAVY};border-radius:14px 14px 0 0;padding:18px 24px">
<span style="color:#ffffff;font-size:19px;font-weight:700;letter-spacing:-0.2px">
{_logo(logo)}SecurePay</span>
<span style="float:right;background:{SAFFRON};color:{INK};font-size:11px;font-weight:700;
letter-spacing:.5px;border-radius:999px;padding:3px 10px;margin-top:2px">TEST MODE</span>
</td></tr>
<tr><td style="background:#ffffff;border:1px solid {LINE};border-top:0;border-radius:0 0 14px 14px;padding:26px 24px 10px;font-size:15px">
{body}
</td></tr>
<tr><td style="padding:16px 8px;font-size:12px;line-height:1.5;color:{MUTED};text-align:center">
{escape(FOOTER)}</td></tr>
</table></td></tr></table></body></html>"""


class BrandedEmailBackend(BaseEmailBackend):
    """Adds the HTML version, then sends through EMAIL_INNER_BACKEND."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.inner = get_connection(settings.EMAIL_INNER_BACKEND, fail_silently=fail_silently,
                                    **kwargs)

    def open(self):
        return self.inner.open()

    def close(self):
        return self.inner.close()

    def send_messages(self, email_messages):
        return self.inner.send_messages([with_html(m) for m in email_messages])


def with_html(message):
    if getattr(message, "alternatives", None) or message.content_subtype != "plain":
        return message
    branded = EmailMultiAlternatives(
        subject=message.subject, body=message.body, from_email=message.from_email,
        to=message.to, cc=message.cc, bcc=message.bcc, attachments=message.attachments,
        headers=message.extra_headers, reply_to=message.reply_to)
    # The mark goes inside the email only when nothing else is attached: multipart/related is
    # for parts the HTML uses, and a real attachment needs multipart/mixed.
    logo = not message.attachments
    branded.attach_alternative(html_for(message.subject, message.body, logo=logo), "text/html")
    if logo:
        branded.mixed_subtype = "related"
        image = MIMEImage(_logo_bytes(), "png")
        image.add_header("Content-ID", f"<{LOGO_CID}>")
        image.add_header("Content-Disposition", "inline", filename="securepay.png")
        branded.attach(image)
    return branded
