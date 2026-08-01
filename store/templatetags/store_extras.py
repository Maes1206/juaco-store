from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def cop(value):
    """Formatea un valor como pesos colombianos: 430000 -> $430.000 COP."""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    formatted = f"{amount:,.0f}".replace(",", ".")
    return f"${formatted} COP"


@register.filter
def duration_minutes(value):
    """Redondea un timedelta hacia arriba a minutos completos, para mostrarlo al usuario."""
    try:
        seconds = value.total_seconds()
    except AttributeError:
        return value
    return max(1, -(-int(seconds) // 60))
