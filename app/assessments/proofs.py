"""Public evidence excludes questions, answer keys and submitted answers."""
RULES = {'rules-v1': {'min_correct':6,'min_per_area':1,'duration_minutes':15,'question_count':8}}


def witness(attempt):
    if attempt.status!='finished':raise ValueError('Активная попытка не является свидетельством.')
    return {'attempt_id':attempt.pk,'specialization':'iOS / Swift','grade':attempt.grade,
        'finished_at':attempt.finished_at.isoformat(),'bank_version':attempt.bank_version,
        'rules_version':attempt.rules_version,'variant':attempt.variant,
        'areas':dict(attempt.area_scores),'correct_count':attempt.correct_count,'total':len(attempt.tasks),
        'passed':attempt.passed,'expired':attempt.expired,'criteria':dict(RULES[attempt.rules_version]),
        'limitations':'Короткий тест без прокторинга; не подтверждает опыт и софт-скиллы. Валидность уровня на реальных людях не доказана.'}
