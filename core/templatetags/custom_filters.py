import datetime
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def string_to_date(value):
    """Converte string YYYY-MM-DD para DD/MM/YYYY"""
    if not value: return ""
    try:
        data_obj = datetime.datetime.strptime(str(value), '%Y-%m-%d')
        return data_obj.strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return value