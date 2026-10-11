"""Small constructors for authored track material, without assessment dependencies."""


def lesson(title, intro, sections, code, checklist, source):
    return {'title': title, 'intro': intro, 'sections': sections, 'code': code,
            'checklist': checklist, 'source': source}


def bank(track, topics, items):
    questions = []
    for (grade, topic), rows in items.items():
        for number, (prompt, options, correct, explanation) in enumerate(rows, 1):
            questions.append({'id': f'learn-{track}-{grade}-{topic}-{number}', 'track': track,
                              'grade': grade, 'topic': topic, 'area': topics[topic]['name'],
                              'prompt': prompt, 'options': options, 'correct': correct,
                              'explanation': explanation})
    return questions
