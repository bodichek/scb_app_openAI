import json
from django import template

register = template.Library()

@register.filter
def tojson(value):
    """
    Převod Python objektu (dict/list) na JSON string pro vložení do šablony.
    Použití v template: {{ mydict|tojson }}
    """
    return json.dumps(value, ensure_ascii=False)
