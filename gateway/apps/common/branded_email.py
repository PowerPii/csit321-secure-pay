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
- a subject like "123456 is your SecurePay verification code" shows the code in a large box;
- a first paragraph that is one sentence (not a greeting such as "Hello,") is the headline,
  and the first line is also the hidden preview text inbox lists show under the subject;
- in an item table a "Total" row is bold, above a rule;
- a button says what the link does, from its path (status check, new password, confirm).
The body is HTML-escaped first, so nothing in it (a shop name, an item name) can inject
markup.

The header shows the securepay. wordmark (frontend/brand, Slate rebrand) as a small PNG
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

# Brand colours, the same as frontend/brand/tokens.json (Slate rebrand).
NAVY, INK, BRASS, BRASS_LIGHT, MUTED, LINE, SLATE, MIST = (
    "#13243F", "#0E1B30", "#B08A3E", "#D2AE63", "#4A5568", "#E1E6ED", "#DCE2EA", "#ECEFF4")
_FIELD = re.compile(r"^([A-Z][\w ()/'-]{0,30}):\s{2,}(.+)$")
_URL = re.compile(r"^https?://\S+$")
_ITEM = re.compile(r"^\s{2,}\S.*\S\s{2,}\S+$")
_CODE_SUBJECT = re.compile(r"^(\d{4,8}) is your ")

LOGO_CID = "securepay-wordmark"
LOGO_PATH = Path(__file__).resolve().parent / "brand" / "securepay-wordmark-email.png"

FOOTER = ("SecurePay is a payment gateway built for the CSIT321 final-year project. Payments "
          "are simulated: no real money moves. We never ask for your card details or a code "
          "by phone or message.")


BUTTON_LABELS = (  # (path ending, label); checked in order, the path without query or fragment
    ("/guest/status", "Check payment status"),
    ("/reset", "Choose a new password"),
    ("/reset-password", "Choose a new password"),
    ("/register/verify", "Confirm your email"),
    ("/login", "Sign in"),
)


def button_label(url: str) -> str:
    path = re.split(r"[?#]", url.strip(), maxsplit=1)[0].rstrip("/")
    return next((label for end, label in BUTTON_LABELS if path.endswith(end)), "Open the page")


def _button(url: str) -> str:
    label = button_label(url)
    url = escape(url.strip(), quote=True)
    return (f'<p style="margin:6px 0 8px"><a href="{url}" style="display:inline-block;'
            f'background:{NAVY};color:#ffffff;text-decoration:none;font-weight:600;'
            f'padding:11px 22px;border-radius:999px">{label}</a></p>'
            f'<p style="margin:0 0 18px;font-size:12px;color:{MUTED};word-break:break-all">'
            f"{url}</p>")


def _text(lines: list[str]) -> str:
    text = "<br>".join(escape(line.strip()) for line in lines)
    return f'<p style="margin:0 0 16px;line-height:1.55">{text}</p>'


def _item_row(name: str, price: str) -> str:
    if name == "Total":
        cell = f"padding:8px 0 4px;color:{INK};font-weight:700;border-top:1px solid {LINE}"
    else:
        cell = f"padding:4px 0;color:{INK}"
    return (f'<tr><td style="{cell}">{escape(name)}</td>'
            f'<td style="{cell};text-align:right;white-space:nowrap">{escape(price)}</td></tr>')


def _item_rows(lines: list[str]) -> str:
    rows = "".join(_item_row(*re.split(r"\s{2,}", line.strip(), maxsplit=1)) for line in lines)
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
        return (f'<img src="cid:{LOGO_CID}" width="128" height="24" alt="securepay." '
                f'style="display:inline-block;vertical-align:middle;border:0">')
    return (f'<span style="color:#ffffff;font-size:21px;font-weight:600;letter-spacing:-0.9px">'
            f'securepay<span style="color:{BRASS_LIGHT}">.</span></span>')


def html_for(subject: str, text: str, logo: bool = False) -> str:
    blocks: list[list[str]] = [[]]
    for line in text.splitlines():
        if line.strip():
            blocks[-1].append(line)
        elif blocks[-1]:
            blocks.append([])
    blocks = [b for b in blocks if b]
    headline = ""
    if blocks and len(blocks[0]) == 1 and not blocks[0][0].rstrip().endswith(","):
        line = blocks.pop(0)[0].strip()
        if not (_URL.match(line) or _FIELD.match(line)):
            headline = (f'<p style="margin:0 0 18px;font-size:20px;line-height:1.35;'
                        f'font-weight:700;color:{INK}">{escape(line)}</p>')
        else:
            blocks.insert(0, [line])
    body = "".join(_paragraph(b) for b in blocks)
    code = _CODE_SUBJECT.match(subject)
    if code:
        body = (f'<p style="margin:0 0 18px;text-align:center"><span style="display:inline-block;'
                f'font-family:Menlo,Consolas,monospace;font-size:30px;font-weight:700;'
                f'letter-spacing:8px;color:{INK};background:{MIST};border:1px solid {LINE};'
                f'border-radius:12px;padding:12px 22px">{escape(code.group(1))}</span></p>'
                + body)
    body = headline + body
    preview = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(subject)}</title></head>
<body style="margin:0;padding:0;background:{SLATE};font-family:'Hanken Grotesk',Segoe UI,Helvetica,Arial,sans-serif;color:{INK}">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{SLATE}">{escape(preview)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{SLATE}">
<tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
<tr><td style="background:{NAVY};border-radius:14px 14px 0 0;padding:18px 24px">
{_logo(logo)}
<span style="float:right;border:1px solid {BRASS_LIGHT};color:{BRASS_LIGHT};font-size:11px;font-weight:700;
letter-spacing:.5px;border-radius:999px;padding:3px 10px;margin-top:2px">TEST MODE</span>
</td></tr>
<tr><td style="background:#ffffff;border-top:2px solid {BRASS};border-radius:0 0 14px 14px;padding:26px 24px 10px;font-size:15px">
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
