from django import forms
from profiles.skills import SKILLS,validate_skills,canonical_skill
from .models import Need,Company,Recruiter
from profiles.forms import CatalogChoices
from profiles.conditions import TASK_TYPES, CONDITION_FILTERS

class CompanyForm(forms.ModelForm):
    class Meta:
        model=Company
        fields=('name','industry','description','contact_email')
        labels={'name':'Название компании','industry':'Направление деятельности','description':'О компании',
                'contact_email':'Email для связи (обязателен перед отправкой предложения)'}

class NeedForm(forms.ModelForm):
    task_types=CatalogChoices(choices=TASK_TYPES,required=False,label='Типы задач',widget=forms.CheckboxSelectMultiple,
        help_text='Выберите все существенные типы. Пустое поле означает неизвестное условие; свободное описание не распознаётся автоматически.')
    company_name=forms.CharField(max_length=120,label='Название компании')
    company_email=forms.EmailField(required=False,label='Контакт компании для кандидата')
    class Meta:
        model=Need
        fields=('title','grade','skills','tasks','salary_min','salary_max','work_format','employment_type','task_types','next_step','recruiter')
        labels={'title':'Роль','grade':'Категория','skills':'Желаемые навыки через запятую','tasks':'Задачи',
            'salary_min':'Зарплата от, ₽ до налогов / месяц','salary_max':'Зарплата до, ₽ до налогов / месяц',
            'work_format':'Формат работы','employment_type':'Занятость (не указано — неизвестно)','next_step':'Следующий шаг','recruiter':'Ответственный HR'}
    def __init__(self,*args,company=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['recruiter'].queryset=Recruiter.objects.filter(company=company).order_by('name','pk') if company else Recruiter.objects.none()
        self.fields['recruiter'].empty_label='Без ответственного'
        self.fields['recruiter'].help_text='Список HR настраивается на дашборде владельца.'
    def clean_skills(self):return validate_skills(self.cleaned_data['skills'])
    def clean(self):
        data=super().clean()
        if data.get('salary_min') and data.get('salary_max') and data['salary_min']>data['salary_max']:
            raise forms.ValidationError('Нижняя граница зарплаты не должна превышать верхнюю.')
        return data

class RecruiterForm(forms.ModelForm):
    class Meta:
        model=Recruiter
        fields=('name',)
        labels={'name':'Имя HR'}

class AssignmentForm(forms.Form):
    need=forms.ModelChoiceField(queryset=Need.objects.none(),label='Потребность')
    recruiter=forms.ModelChoiceField(queryset=Recruiter.objects.none(),required=False,label='Ответственный HR',empty_label='Без ответственного')

    def __init__(self,*args,company,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['need'].queryset=Need.objects.filter(company=company).order_by('title','pk')
        self.fields['need'].label_from_instance=lambda obj:obj.title
        self.fields['recruiter'].queryset=Recruiter.objects.filter(company=company).order_by('name','pk')

class SkillChoiceField(forms.ChoiceField):
    def to_python(self,value):
        return canonical_skill(super().to_python(value))

class SearchForm(forms.Form):
    conditions=forms.ChoiceField(choices=CONDITION_FILTERS,required=False,label='Совпадение условий')
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
        if data.get('conditions') and not data.get('need'):
            raise forms.ValidationError('Для фильтра условий выберите потребность.')
        return data
