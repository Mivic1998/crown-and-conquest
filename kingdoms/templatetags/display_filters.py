import math
from django import template

register = template.Library()


@register.filter
def floor_value(value):
    """Display a numeric value using its floor without mutating stored data."""
    try:
        return math.floor(float(value))
    except (TypeError, ValueError):
        return value
