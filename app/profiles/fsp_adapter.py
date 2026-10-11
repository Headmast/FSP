"""Application-owned mock contract. It is not an official FSP API schema."""
import re


class SourceUnavailable(Exception):
    pass


def valid_demo_id(value):
    return bool(re.fullmatch(r'DEMO-(?:(?!000)[0-9]{3}|EMPTY|DOWN)',value))


def fetch(external_id):
    if not valid_demo_id(external_id):raise ValueError('Некорректный demo ID.')
    if external_id=='DEMO-DOWN':raise SourceUnavailable()
    if external_id=='DEMO-EMPTY':return {'source':'mock','status':'no_history','events':[]}
    number=int(external_id[-3:])
    return {'source':'mock','status':'demo_history','events':[{
        'event_id':f'event-{number}', 'source':'mock', 'event_name':'Демонстрационный турнир',
        'occurred_on':'2026-10-09','discipline':'iOS / Swift',
        'result':'1 место' if number%2 else 'Участие','team':bool(number%2), 'prize':bool(number%2)}]}
