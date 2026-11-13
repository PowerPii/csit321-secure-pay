from django import template

register = template.Library()


@register.filter
def money(cents) -> str:
    """8990 -> "S$ 89.90"."""
    cents = int(cents or 0)
    return f"S$ {cents // 100:,}.{cents % 100:02d}"
