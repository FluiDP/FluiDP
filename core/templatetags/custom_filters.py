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
    
@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """
    Atualiza a querystring atual mesclando com novos parâmetros.
    Ex: {% query_transform sort='-data' %}
    """
    query = context['request'].GET.copy()
    for k, v in kwargs.items():
        query[k] = v

    if 'page' in query and 'sort' in kwargs:
        del query['page']
    return query.urlencode()