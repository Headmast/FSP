"""Stated preferences, never a skill assessment or a contact-bearing free-text field."""
WORK_FORMATS = [('remote', 'Удалённо'), ('office', 'Офис'), ('hybrid', 'Гибрид')]
EMPLOYMENT_TYPES = [('full_time', 'Полная занятость'), ('part_time', 'Частичная занятость'),
                    ('project', 'Проектная работа'), ('internship', 'Стажировка')]
TASK_TYPES = [('development', 'Разработка'), ('testing', 'Тестирование'), ('support', 'Поддержка'),
              ('architecture', 'Архитектура'), ('mentoring', 'Наставничество')]
CONDITION_FILTERS = [('', 'Любые условия'), ('compatible', 'Нет известных противоречий (неизвестные допустимы)'),
                     ('matched', 'Все три условия известны и совпадают'), ('conflicts', 'Есть противоречия')]
NOTE = 'Предпочтения заявлены кандидатом; они не подтверждают навыки и не меняют категорию или рейтинг.'


def codes(value, choices):
    if not isinstance(value, list):
        return []
    # Fixed catalog order; reject arbitrary text even in legacy/corrupted database values.
    return [key for key, _ in choices if key in value]


def preferences(profile):
    return {'work_formats': codes(profile.preferred_work_formats, WORK_FORMATS),
            'employment_types': codes(profile.preferred_employment_types, EMPLOYMENT_TYPES),
            'task_types': codes(profile.preferred_task_types, TASK_TYPES)}


def labels(value, choices):
    return [dict(choices)[key] for key in codes(value, choices)]


def compare_values(candidate, demand):
    result = {'version': 'conditions-v1', 'matches': [], 'conflicts': [], 'unknown': [], 'note': NOTE}
    dimensions = [('work_format', 'Формат работы', 'work_formats', WORK_FORMATS),
                  ('employment_type', 'Занятость', 'employment_types', EMPLOYMENT_TYPES),
                  ('task_types', 'Типы задач', 'task_types', TASK_TYPES)]
    for key, title, candidate_key, choices in dimensions:
        wanted = codes(candidate.get(candidate_key), choices)
        required = codes(demand.get(candidate_key), choices)
        if not wanted or not required:
            status = 'unknown'
            reason = ('Кандидат не указал предпочтения.' if not wanted else
                      'Работодатель не указал условия или потребность не выбрана.')
            if not wanted and not required:
                reason = 'Условия не указаны обеими сторонами или потребность не выбрана.'
        elif set(required).issubset(wanted):
            status, reason = 'matches', 'Указанные условия входят в предпочтения кандидата.'
        else:
            status, reason = 'conflicts', 'Часть или все условия не входят в указанные предпочтения кандидата; требуется уточнение.'
        result[status].append({'key': key, 'label': title, 'candidate': wanted, 'required': required,
                               'candidate_labels': labels(wanted, choices), 'required_labels': labels(required, choices),
                               'reason': reason})
    return result


def demand(need):
    return {'work_formats': [need.work_format], 'employment_types': [need.employment_type],
            'task_types': need.task_types} if need else {}


def compare_conditions(profile, need=None):
    return compare_values(preferences(profile), demand(need))


def snapshot_conditions(snapshot):
    """Rebuild controlled projections, including unknown preferences on old invitations."""
    candidate = snapshot.get('candidate_preferences', {})
    if not isinstance(candidate, dict):
        candidate = {}
    work_format = snapshot.get('work_format_code')
    if not isinstance(work_format,str) or work_format not in dict(WORK_FORMATS):
        legacy = snapshot.get('work_format')
        work_format = next((key for key, text in WORK_FORMATS if legacy in (key, text)), '')
    return compare_values(candidate, {'work_formats': [work_format],
        'employment_types': [snapshot.get('employment_type', '')], 'task_types': snapshot.get('task_types', [])})


def filter_conditions(comparison, value):
    if value == 'matched':
        return len(comparison['matches']) == 3
    if value == 'compatible':
        return not comparison['conflicts']
    if value == 'conflicts':
        return bool(comparison['conflicts'])
    return True
