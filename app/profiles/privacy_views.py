from uuid import uuid4
from django import forms
from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.db import DatabaseError
from django.shortcuts import render,redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from accounts.identifiers import parse_identifier
from .privacy import ACTIONS,request_action,status_data,PrivacyUnavailable


class PrivacyActionForm(forms.Form):
    action=forms.ChoiceField(choices=[(v,v) for v in sorted(ACTIONS)],widget=forms.HiddenInput)
    request_id=forms.UUIDField(widget=forms.HiddenInput)
    company=forms.CharField(required=False,widget=forms.HiddenInput)
    acknowledge=forms.BooleanField(label='Подтверждаю выбранное действие и прочитал, какие данные изменятся')
    password=forms.CharField(required=False,strip=False,widget=forms.PasswordInput,label='Текущий пароль (для очистки или удаления)')

    def clean(self):
        values=super().clean()
        if values.get('action') in {'clear_profile','delete_account'} and not values.get('password'):
            self.add_error('password','Для очистки или удаления введите текущий пароль.')
        if values.get('action')=='revoke_company':
            values['company']=parse_identifier(values.get('company'))
        return values


@login_required
@require_http_methods(['GET','POST'])
def dashboard(request):
    if request.user.role!='candidate' or not request.user.is_active:raise PermissionDenied
    status=200
    form=PrivacyActionForm(request.POST if request.method=='POST' else None)
    if request.method=='POST':
        if form.is_valid():
            values=form.cleaned_data
            if values['action'] in {'clear_profile','delete_account'} and not request.user.check_password(values['password']):
                form.add_error('password','Неверный пароль. Данные не изменены.')
            else:
                try:request_action(request.user,values['action'],values['request_id'],values.get('company'))
                except ValidationError as exc:form.add_error(None,exc)
                except (PrivacyUnavailable,DatabaseError):
                    return HttpResponse('Запрос не завершён. Данные не выдаются до восстановления журнала приватности.',status=503)
                else:
                    if values['action'] in {'clear_profile','delete_account'}:
                        logout(request)
                        messages.success(request,'Профиль очищен; войдите заново.' if values['action']=='clear_profile' else 'Профиль и аккаунт удалены.')
                        return redirect('home')
                    messages.success(request,'Открытый контактный доступ отозван. Повтор не открывает его снова.')
                    return redirect('profile-privacy')
        status=400
    data=status_data(request.user)
    return render(request,'profiles/privacy.html',{'privacy':data,'form':form,'request_id':uuid4()},status=status)
