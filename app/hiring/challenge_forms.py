from django import forms
from profiles.skills import SKILLS


class ChallengeOfferForm(forms.Form):
    request_id=forms.UUIDField(widget=forms.HiddenInput)
    skill=forms.ChoiceField(choices=[(v,v) for v in SKILLS],label='Конкретный навык потребности')
    title=forms.CharField(max_length=120,label='Название короткого задания')
    instructions=forms.CharField(max_length=4000,widget=forms.Textarea,label='Что сделать и что отправить')
    criteria=forms.CharField(max_length=1000,widget=forms.Textarea,label='Критерии — по одному на строке',
        help_text='1–5 конкретных критериев, до 180 символов каждый. Для каждого: 0 — не показано, 1 — частично, 2 — полностью.')
    pass_points=forms.IntegerField(min_value=1,max_value=10,label='Порог достаточного результата',help_text='Не больше двух баллов на каждый критерий.')
    duration_minutes=forms.IntegerField(min_value=5,max_value=60,label='Бюджет после начала, минут')
    deadline_at=forms.DateTimeField(label='Отправить не позже (московское время)',
        widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'))
    acknowledge=forms.BooleanField(label='Проверил условия: отправленное задание нельзя редактировать')

    def __init__(self,*args,invitation=None,**kwargs):
        super().__init__(*args,**kwargs)
        if invitation:
            from profiles.skills import normalized
            values=normalized(invitation.need.skills)
            self.fields['skill'].choices=[(v,v) for v in SKILLS if v.casefold() in values]

    def clean_criteria(self):
        values=[v.strip() for v in self.cleaned_data['criteria'].splitlines() if v.strip()]
        if not 1<=len(values)<=5 or any(len(v)>180 for v in values) or len(set(values))!=len(values):
            raise forms.ValidationError('Укажите 1–5 разных критериев до 180 символов.')
        return values

    def clean(self):
        values=super().clean()
        if values.get('criteria') and values.get('pass_points',0)>2*len(values['criteria']):
            self.add_error('pass_points','Порог превышает максимум объявленной шкалы.')
        return values


class ChallengeActionForm(forms.Form):
    action=forms.ChoiceField(choices=[(v,v) for v in ['accept','decline','save','submit','revoke','withdraw','credit']],widget=forms.HiddenInput)
    revision=forms.IntegerField(min_value=0,max_value=2**31-1,widget=forms.HiddenInput)
    answer=forms.CharField(max_length=12000,required=False,widget=forms.Textarea,label='Ваш ответ или код',
        help_text='Код не выполняется. Черновик до отправки видите только вы.')
    acknowledge=forms.BooleanField(required=False,label='Подтверждаю выбранное действие')

    def clean(self):
        values=super().clean()
        if values.get('action') not in {'save','decline'} and not values.get('acknowledge'):
            self.add_error('acknowledge','Нужно явное подтверждение.')
        if values.get('action')=='submit' and not values.get('answer'):
            self.add_error('answer','Заполните ответ перед отправкой.')
        return values


class ChallengeReviewForm(forms.Form):
    action=forms.ChoiceField(choices=[('review','review')],widget=forms.HiddenInput,initial='review')
    revision=forms.IntegerField(min_value=0,max_value=2**31-1,widget=forms.HiddenInput)
    note=forms.CharField(max_length=2000,widget=forms.Textarea,label='Почему выставлены эти баллы')
    credit=forms.BooleanField(required=False,label='Явно зачесть достаточный результат для этой потребности')
    acknowledge=forms.BooleanField(label='Подтверждаю оценку компании; она не меняет общий грейд')

    def __init__(self,*args,challenge=None,**kwargs):
        super().__init__(*args,**kwargs)
        for index in range(len(challenge.criteria) if challenge else 5):
            label=challenge.criteria[index] if challenge else f'Критерий {index+1}'
            self.fields[f'score_{index}']=forms.IntegerField(min_value=0,max_value=2,widget=forms.Select(choices=[(0,'0 — не показано'),(1,'1 — частично'),(2,'2 — полностью')]),
                required=challenge is not None,label=label)

    def scores(self,challenge):
        return [self.cleaned_data[f'score_{index}'] for index in range(len(challenge.criteria))]
