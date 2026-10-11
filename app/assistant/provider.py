"""Explicit deterministic mock: no API key, network request or claim of real AI."""
def generate(mode,context):
    if mode=='profile':text=f"iOS разработчик: {context['skills'] or 'Swift'}. Создаю интерфейсы и работаю с данными."
    elif mode=='need':text=f"Ищем iOS разработчика категории {context['grade']}. Навыки: {context['skills'] or 'Swift'}. Следующий шаг — знакомство с командой."
    else:text=f"В завершённом тесте {context['grade']} правильных ответов: {context['correct']}/8. Категорию определяет сервер по общему порогу и каждой области."
    return 'Мок помощника · внешний AI не вызывался.\n\n'+text
