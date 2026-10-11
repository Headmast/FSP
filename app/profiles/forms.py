import re
from django import forms
from .models import Profile, Experience, ROLES, SOFT_SKILLS
from .skills import validate_skills

class ProfileForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(choices=ROLES, required=False, label='Роли в команде (самоописание)', widget=forms.CheckboxSelectMultiple)
    soft_skills = forms.MultipleChoiceField(choices=SOFT_SKILLS, required=False, label='Софт-скиллы (самоописание)', widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = Profile
        fields = ("name", "city", "skills", "specialization", "experience_months", "roles", "soft_skills", "description", "contact_email", "contact_phone", "desired_grade", "published")
        labels = {"name": "Имя", "city": "Город", "skills": "Навыки через запятую", "contact_email": "Контактный email (скрыт)",
                  "contact_phone": "Телефон (скрыт)", "desired_grade": "Категория для теста", "published": "Разрешаю публикацию профиля",
                  "specialization": "Специализация", "experience_months": "Общий стаж, месяцев (самоописание)", "description": "О себе / черновик помощника (скрыт до согласия)"}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['specialization'].required = False

    def clean_specialization(self):
        return self.cleaned_data.get('specialization') or 'ios_swift'

    def clean_experience_months(self):
        return self.cleaned_data.get('experience_months') or 0
    def clean_skills(self):
        return validate_skills(self.cleaned_data["skills"])

    def public_name(self, value):
        if value and not re.fullmatch(r"[^\W\d_]+(?:[ -][^\W\d_]+)*", value, flags=re.UNICODE):
            raise forms.ValidationError("Только имя или город: буквы, пробел и дефис. Контакты укажите в скрытых полях.")
        return value

    def clean_name(self):
        return self.public_name(self.cleaned_data["name"].strip())

    def clean_city(self):
        return self.public_name(self.cleaned_data["city"].strip())

    def clean(self):
        data = super().clean()
        if data.get("published") and not data.get("name"):
            raise forms.ValidationError("Для публикации заполните имя.")
        return data


class OwnedExperienceFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.forms:
            item = form.cleaned_data.get('id')
            if item and item.profile_id != self.instance.pk:
                raise forms.ValidationError('Этот опыт не принадлежит вашему профилю.')


ExperienceFormSet = forms.inlineformset_factory(Profile, Experience, formset=OwnedExperienceFormSet,
    fields=('organization', 'role', 'months', 'description'), extra=1,
    max_num=20, validate_max=True, can_delete=True, labels={
        'organization':'Организация / проект (скрыто)', 'role':'Роль в проекте (скрыто)',
        'months':'Длительность, месяцев', 'description':'Задачи и результаты (скрыто)'})
