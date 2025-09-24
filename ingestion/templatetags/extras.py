from django import template

register = template.Library()

@register.filter
def get_item(d: dict, key: str):
    if isinstance(d, dict):
        return d.get(key)
    return None
