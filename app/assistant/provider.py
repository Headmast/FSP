"""Explicit deterministic mock: no API key, network request or claim of real AI."""
def generate(mode,context):
    if mode=='profile':text=f"iOS разработчик: {context['skills'] or 'Swift'}. Создаю интерфейсы и работаю с данными."
    elif mode=='need':text=f"Ищем iOS разработчика категории {context['grade']}. Навыки: {context['skills'] or 'Swift'}. Следующий шаг — знакомство с командой."
    elif mode=='result':text=f"В завершённом тесте {context['grade']} правильных ответов: {context['correct']}/8. Категорию определяет сервер по общему порогу и каждой области."
    elif mode in {'matching','invitation'}:
        matches=', '.join(context['declared_matches']) or 'не найдены'
        gaps=', '.join(context['declared_gaps']) or 'не указаны'
        proof=context['confirmation']
        evidence=(f"Есть свидетельство {proof['grade']} от {proof['finished_at']}: {proof['correct_count']}/{proof['total']}. "
            'Оно не подтверждает каждый заявленный инструмент.') if proof else 'Сохранённого успешного свидетельства этой категории нет.'
        text=(f"Категория кандидата: {context['candidate_grade']}; потребность: {context['grade_requirement']}.\n"
            f"Совпадения самоописания: {matches}. Пробелы самоописания: {gaps}.\n{evidence}\n"
            + '\n'.join(context['unknown']))
        if mode=='invitation':
            text=(f"Предлагаем обсудить работу категории {context['grade_requirement']}: {context['salary_min']}–{context['salary_max']} ₽ до налогов / месяц, {context['work_format']}.\n"
                f"Уточним практический опыт по заявленным совпадениям: {matches}.\n"
                + (f"Дополнительно обсудим сведения по навыкам: {gaps}.\n" if context['declared_gaps'] else 'Новых пробелов в самоописании по выбранным навыкам нет.\n')
                + f"Доступно результатов для ручного выбора зачёта: {len(context['available_results'])}. {evidence}\n"
                'На встрече уточним задачи и следующие шаги. Выбор зачтённых результатов делает работодатель перед отправкой.')
        elif context['candidate_grade']!=context['grade_requirement']:
            text+='\nКатегории не совпадают; предложение этой потребности отправить нельзя.'
    elif mode=='conversation':
        if context['status']=='declined':text='Предложение отклонено. Контакты этим решением не открываются. Уважайте решение адресата; помощь не меняет статус и не отправляет сообщения.'
        else:
            results=context['accepted_results']
            text=(f"Обсуждаемые условия: {context['grade']}, {context['salary_min']}–{context['salary_max']} ₽ до налогов / месяц, {context['work_format']}.\n"
                f"Работодатель зачёл результатов: {len(results)}. Уточните, какие вопросы уже покрыты и что остаётся обсудить.\n"
                'Вопросы для разговора: какие задачи будут в первый месяц; какие навыки требуют уточнения; кто и когда сообщит следующий шаг.\n')
            text+=('Проверьте условия и примите или отклоните предложение самостоятельно. Контакты открываются только после принятия.' if context['status']=='sent' else
                'Согласуйте время встречи и критерии дальнейшего отбора. Помощник не бронирует встречу и не отправляет сообщения.')
    else:raise ValueError('Unsupported assistant mode')
    return 'Мок помощника · внешний AI не вызывался.\n\n'+text
