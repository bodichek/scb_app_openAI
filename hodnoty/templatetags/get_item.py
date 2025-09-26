from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Vrátí hodnotu z dictu podle klíče, jinak '-'."""
    if not dictionary:
        return "-"
    return dictionary.get(key, "-")

@register.filter
def get_digit_diff(value, target):
    """
    Vrátí range rozdílu mezi target a value.
    Umožňuje dopočítat prázdné buňky v tabulce.
    """
    try:
        diff = target - int(value)
        return range(diff) if diff > 0 else range(0)
    except Exception:
        return range(0)
