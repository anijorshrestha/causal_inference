from django import template
from itertools import groupby

register = template.Library()

@register.filter
def grouper_to_list(grouper):
    print(list(grouper))
    return list(grouper)

@register.filter
def all_causal(dict_obj):
    is_causal=True
    for i in dict_obj['instances']:
        is_causal=i['is_causal']
    #print(is_causal)
    return is_causal
