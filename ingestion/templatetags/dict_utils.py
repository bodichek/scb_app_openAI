from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Vrátí hodnotu z dictu podle klíče, jinak prázdný string."""
    if dictionary and key in dictionary:
        return dictionary.get(key, "")
    return ""
