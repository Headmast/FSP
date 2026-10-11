from django import forms
from profiles.skills import validate_skills
from django.db.models import Q
from profiles.models import Profile
from hiring.models import Need,Invitation


class NeedPromptForm(forms.Form):
    grade=forms.ChoiceField(choices=[('Junior','Junior'),('Middle','Middle')],required=False,label='Категория черновика')
    skills=forms.CharField(max_length=200,required=False,label='Желаемые навыки через запятую')
    def clean_skills(self):return validate_skills(self.cleaned_data['skills'])


class ProfileDraftForm(forms.Form):
    description=forms.CharField(max_length=3000,label='Описание профиля (приватный черновик)',widget=forms.Textarea)


class MatchingContextForm(forms.Form):
    need=forms.ModelChoiceField(queryset=Need.objects.none(),label='Ваша потребность')
    candidate=forms.ModelChoiceField(queryset=Profile.objects.none(),label='Кандидат из доступных профилей')
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['need'].queryset=Need.objects.filter(company__user=user).order_by('pk')
        grants=Invitation.objects.filter(company__user=user,status='accepted').values('candidate_id')
        self.fields['candidate'].queryset=Profile.objects.filter(Q(published=True)|Q(pk__in=grants)).exclude(confirmed_grade='').order_by('pk')
        self.fields['need'].label_from_instance=lambda n:f'{n.title} · {n.grade}'
        self.fields['candidate'].label_from_instance=lambda p:f'{p.name or "Кандидат без имени"} · {p.confirmed_grade}'


class ConversationContextForm(forms.Form):
    invitation=forms.ModelChoiceField(queryset=Invitation.objects.none(),label='Ваше предложение')
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        query=Invitation.objects.filter(candidate__user=user) if user.role=='candidate' else Invitation.objects.filter(company__user=user)
        self.fields['invitation'].queryset=query.order_by('-created_at','-pk')
        self.fields['invitation'].label_from_instance=lambda i:f'{i.snapshot.get("title","Предложение")} · {i.get_status_display()}'
