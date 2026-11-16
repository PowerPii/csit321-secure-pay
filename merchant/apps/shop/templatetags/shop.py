"""Template helpers for Volt & Co.: money, and the product illustrations.

The product pictures are simple SVG drawings made for this project, so the store needs no
image files, no stock-photo licences and no real brand's look.
"""
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def money(cents) -> str:
    """8990 -> "S$ 89.90"."""
    cents = int(cents or 0)
    return f"S$ {cents // 100:,}.{cents % 100:02d}"


INK = "#1d2433"
STEEL = "#8792a8"
LIGHT = "#e9edf5"
ACCENT = "#14b8a6"

# Each drawing sits on a 400 x 300 canvas.
_ART = {
    "laptop": f"""
      <rect x="95" y="62" width="210" height="140" rx="10" fill="{INK}"/>
      <rect x="107" y="74" width="186" height="116" rx="4" fill="{ACCENT}" opacity=".85"/>
      <path d="M107 160 160 118l30 22 40-36 63 56v30H107z" fill="#fff" opacity=".25"/>
      <path d="M60 206h280l-16 22H76z" fill="{STEEL}"/>
      <rect x="180" y="206" width="40" height="5" rx="2" fill="{INK}" opacity=".4"/>""",
    "headphones": f"""
      <path d="M120 175v-30a80 80 0 0 1 160 0v30" fill="none" stroke="{INK}" stroke-width="16"
        stroke-linecap="round"/>
      <rect x="100" y="150" width="48" height="80" rx="20" fill="{INK}"/>
      <rect x="252" y="150" width="48" height="80" rx="20" fill="{INK}"/>
      <rect x="132" y="162" width="22" height="56" rx="10" fill="{ACCENT}"/>
      <rect x="246" y="162" width="22" height="56" rx="10" fill="{ACCENT}"/>""",
    "earbuds": f"""
      <rect x="120" y="150" width="160" height="90" rx="40" fill="#fff" stroke="{STEEL}"
        stroke-width="4"/>
      <line x1="124" y1="190" x2="276" y2="190" stroke="{STEEL}" stroke-width="3"/>
      <circle cx="200" cy="215" r="5" fill="{ACCENT}"/>
      <circle cx="165" cy="95" r="26" fill="#fff" stroke="{INK}" stroke-width="5"/>
      <rect x="158" y="110" width="14" height="44" rx="7" fill="{INK}"/>
      <circle cx="235" cy="95" r="26" fill="#fff" stroke="{INK}" stroke-width="5"/>
      <rect x="228" y="110" width="14" height="44" rx="7" fill="{INK}"/>
      <circle cx="165" cy="95" r="9" fill="{ACCENT}"/><circle cx="235" cy="95" r="9"
        fill="{ACCENT}"/>""",
    "speaker": f"""
      <rect x="140" y="60" width="120" height="180" rx="50" fill="{INK}"/>
      <circle cx="200" cy="125" r="34" fill="{STEEL}"/><circle cx="200" cy="125" r="14"
        fill="{INK}"/>
      <circle cx="200" cy="195" r="20" fill="{STEEL}"/>
      <rect x="185" y="48" width="30" height="16" rx="6" fill="{ACCENT}"/>""",
    "keyboard": f"""
      <rect x="60" y="100" width="280" height="110" rx="14" fill="{INK}"/>
      {''.join(f'<rect x="{78 + c * 27}" y="{116 + r * 24}" width="20" height="18" rx="3" fill="#fff" opacity=".9"/>' for r in range(3) for c in range(9))}
      <rect x="105" y="188" width="170" height="14" rx="3" fill="#fff" opacity=".9"/>
      <circle cx="318" cy="122" r="9" fill="{ACCENT}"/>""",
    "monitor": f"""
      <rect x="70" y="50" width="260" height="160" rx="10" fill="{INK}"/>
      <rect x="82" y="62" width="236" height="136" rx="4" fill="{ACCENT}" opacity=".85"/>
      <circle cx="270" cy="100" r="18" fill="#fff" opacity=".35"/>
      <path d="M82 198v-36l60-40 50 34 46-26 80 50v18z" fill="#fff" opacity=".25"/>
      <rect x="188" y="210" width="24" height="34" fill="{STEEL}"/>
      <rect x="140" y="242" width="120" height="10" rx="5" fill="{STEEL}"/>""",
    "hub": f"""
      <rect x="110" y="120" width="180" height="60" rx="16" fill="{STEEL}"/>
      <rect x="130" y="140" width="22" height="12" rx="2" fill="{INK}"/>
      <rect x="162" y="140" width="22" height="12" rx="2" fill="{INK}"/>
      <rect x="194" y="141" width="14" height="10" rx="4" fill="{INK}"/>
      <rect x="218" y="140" width="28" height="12" rx="2" fill="{INK}"/>
      <rect x="256" y="143" width="18" height="6" rx="2" fill="{INK}"/>
      <path d="M290 150c40 0 40 50 70 50" fill="none" stroke="{INK}" stroke-width="7"
        stroke-linecap="round"/>
      <circle cx="140" cy="168" r="3" fill="{ACCENT}"/>""",
    "laptop-stand": f"""
      <path d="M90 225 300 110" stroke="{STEEL}" stroke-width="12" stroke-linecap="round"/>
      <path d="M150 225 270 160" stroke="{STEEL}" stroke-width="10" stroke-linecap="round"/>
      <rect x="80" y="220" width="240" height="10" rx="5" fill="{STEEL}"/>
      <path d="M120 170 300 72" stroke="{INK}" stroke-width="10" stroke-linecap="round"/>
      <circle cx="300" cy="110" r="6" fill="{ACCENT}"/>""",
    "charger": f"""
      <rect x="140" y="80" width="120" height="140" rx="20" fill="#fff" stroke="{INK}"
        stroke-width="5"/>
      <rect x="160" y="190" width="22" height="9" rx="3" fill="{INK}"/>
      <rect x="190" y="190" width="22" height="9" rx="3" fill="{INK}"/>
      <rect x="220" y="189" width="20" height="11" rx="2" fill="{INK}"/>
      <path d="M205 110l-22 38h18l-6 30 24-42h-18z" fill="{ACCENT}"/>
      <rect x="168" y="58" width="12" height="24" fill="{STEEL}"/>
      <rect x="220" y="58" width="12" height="24" fill="{STEEL}"/>""",
    "mouse": f"""
      <rect x="150" y="60" width="100" height="170" rx="50" fill="{INK}"/>
      <line x1="200" y1="62" x2="200" y2="125" stroke="#fff" stroke-width="3" opacity=".5"/>
      <line x1="152" y1="125" x2="248" y2="125" stroke="#fff" stroke-width="3" opacity=".5"/>
      <rect x="194" y="82" width="12" height="26" rx="6" fill="{ACCENT}"/>""",
    "phone-stand": f"""
      <path d="M150 230h120l-30-70" fill="none" stroke="{STEEL}" stroke-width="12"
        stroke-linecap="round" stroke-linejoin="round"/>
      <rect x="160" y="50" width="80" height="150" rx="12" fill="{INK}"
        transform="rotate(-12 200 125)"/>
      <rect x="168" y="62" width="64" height="122" rx="6" fill="{ACCENT}" opacity=".85"
        transform="rotate(-12 200 125)"/>""",
    "cable": f"""
      <path d="M110 90c120 0-40 150 90 150s100-110 80-150" fill="none" stroke="{INK}"
        stroke-width="10" stroke-linecap="round"/>
      <rect x="70" y="80" width="44" height="20" rx="8" fill="{STEEL}"/>
      <rect x="58" y="84" width="14" height="12" rx="4" fill="{INK}"/>
      <rect x="262" y="40" width="20" height="44" rx="8" fill="{STEEL}"/>
      <rect x="266" y="28" width="12" height="14" rx="4" fill="{INK}"/>
      <circle cx="92" cy="90" r="3" fill="{ACCENT}"/>""",
}


@register.simple_tag
def product_art(product, size: str = "card"):
    """The product's drawing as inline SVG, labelled with the product's name."""
    body = _ART.get(getattr(product, "art", ""), "")
    if not body:
        body = f'<rect x="150" y="90" width="100" height="120" rx="16" fill="{STEEL}"/>'
    return format_html(
        '<svg class="art art-{}" viewBox="0 0 400 300" role="img" aria-label="{}">'
        '<rect width="400" height="300" fill="{}"/>{}</svg>',
        size, product.name, LIGHT, mark_safe(body))  # our own constant markup


@register.filter
def gst_included(total_cents) -> int:
    from apps.shop.catalogue import gst_included_cents

    return gst_included_cents(int(total_cents or 0))
