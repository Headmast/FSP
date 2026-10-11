from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from api.core import issue_token, ApiError
from .models import ApiToken


class TokenForm(forms.Form):
    name = forms.CharField(max_length=80, label='Название подключения')
    kind = forms.ChoiceField(choices=[('cli', 'CLI'), ('mcp', 'MCP')], label='Тип')
    contacts = forms.BooleanField(required=False, label='Разрешить контакты и скрытые сведения (только CLI)')
    drafts = forms.BooleanField(required=False, label='Разрешить подготовку черновиков (применение только в браузере)')

    def clean(self):
        values = super().clean()
        if values.get('kind') == 'mcp' and values.get('contacts'):
            raise forms.ValidationError('MCP не получает контакты.')
        return values


@login_required
@require_http_methods(['GET', 'POST'])
def integrations(request):
    if not request.user.has_processing_consent:
        return redirect('consent')
    from django.core.exceptions import PermissionDenied
    if not request.user.is_active or not request.user.email_confirmed:
        raise PermissionDenied
    form = TokenForm(request.POST if request.method == 'POST' and request.POST.get('action') == 'create' else None)
    secret = None
    status = 200
    if request.method == 'POST':
        if request.POST.get('action') == 'revoke':
            from .identifiers import parse_identifier
            token = get_object_or_404(ApiToken, pk=parse_identifier(request.POST.get('id')), user=request.user)
            token.revoked_at = timezone.now()
            token.save(update_fields=['revoked_at'])
            return redirect('integrations')
        if form.is_valid():
            try:
                _, secret = issue_token(request.user, **form.cleaned_data)
            except ApiError:
                raise PermissionDenied
        else:
            status = 400
    response = render(request, 'accounts/integrations.html', {'form': form, 'secret': secret,
        'client_version': __import__('api.views',fromlist=['client_version']).client_version(),
        'tokens': ApiToken.objects.filter(user=request.user).order_by('-pk')}, status=status)
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response
