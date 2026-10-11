from django import forms
from profiles.skills import validate_skills


class NeedPromptForm(forms.Form):
    grade=forms.ChoiceField(choices=[('Junior','Junior'),('Middle','Middle')],required=False,label='Категория черновика')
    skills=forms.CharField(max_length=200,required=False,label='Желаемые навыки через запятую')
    def clean_skills(self):return validate_skills(self.cleaned_data['skills'])


class ProfileDraftForm(forms.Form):
    description=forms.CharField(max_length=3000,label='Описание профиля (приватный черновик)',widget=forms.Textarea)
