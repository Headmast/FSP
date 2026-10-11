from django import forms
from profiles.skills import SKILLS,validate_skills,canonical_skill
from .models import Need

class NeedForm(forms.ModelForm):
    company_name=forms.CharField(max_length=120,label='Название компании')
    company_email=forms.EmailField(required=False,label='Контакт компании для кандидата')
    class Meta:
        model=Need
        fields=('title','grade','skills','tasks','salary_min','salary_max','work_format','next_step')
        labels={'title':'Роль','grade':'Категория','skills':'Желаемые навыки через запятую','tasks':'Задачи',
            'salary_min':'Зарплата от, ₽ до налогов / месяц','salary_max':'Зарплата до, ₽ до налогов / месяц',
            'work_format':'Формат работы','next_step':'Следующий шаг'}
    def clean_skills(self):return validate_skills(self.cleaned_data['skills'])
    def clean(self):
        data=super().clean()
        if data.get('salary_min') and data.get('salary_max') and data['salary_min']>data['salary_max']:
            raise forms.ValidationError('Нижняя граница зарплаты не должна превышать верхнюю.')
        return data

class SkillChoiceField(forms.ChoiceField):
    def to_python(self,value):
        return canonical_skill(super().to_python(value))

class SearchForm(forms.Form):
    need=forms.ModelChoiceField(queryset=Need.objects.none(),required=False,label='Потребность')
    grade=forms.ChoiceField(choices=[('Junior','Junior'),('Middle','Middle')],label='Категория')
    skill=SkillChoiceField(choices=[('','Любой навык')]+[(s,s) for s in SKILLS],required=False,label='Навык')
    fsp=forms.ChoiceField(choices=[('','Любая история ФСП'),('no_history','Без истории'),('demo_history','Демо история')],required=False,label='ФСП')
    def __init__(self,*args,company,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['need'].queryset=Need.objects.filter(company=company)
        self.fields['need'].label_from_instance=lambda obj:f'{obj.title} · {obj.grade}'
    def clean(self):
        data=super().clean()
        if data.get('need') and data.get('grade') and data['need'].grade!=data['grade']:
            raise forms.ValidationError('Категория фильтра должна совпадать с потребностью.')
        return data
