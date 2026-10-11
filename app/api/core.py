"""Bearer authentication and a JSON error boundary, separate from session forms."""
import hashlib
import logging
import secrets
from datetime import timedelta
from functools import wraps
from uuid import uuid4
from django.db import transaction, DatabaseError
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from accounts.models import ApiToken

log = logging.getLogger('fsp.api')


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def require(condition, status=403, code='FORBIDDEN', message='Доступ запрещён.'):
    if not condition:
        raise ApiError(status, code, message)


def issue_token(user, name, kind, contacts=False, drafts=False):
    require(user.is_active and user.email_confirmed and user.has_processing_consent)
    require(user.role in {'candidate', 'employer'})
    require(kind in {'cli', 'mcp'}, 400, 'INVALID_KIND', 'Неверный тип подключения.')
    require(not (kind == 'mcp' and contacts), 400, 'INVALID_SCOPE', 'MCP не получает контакты.')
    scopes = [f'{user.role}.read']
    if contacts:
        scopes.append('contacts.read')
    if drafts:
        scopes.append(f'{user.role}.draft')
    secret = 'fsp_' + secrets.token_urlsafe(32)
    token = ApiToken.objects.create(user=user, name=name[:80], kind=kind, scopes=scopes,
        digest=hashlib.sha256(secret.encode()).hexdigest(), expires_at=timezone.now()+timedelta(days=30))
    return token, secret


def meta(request):
    return {'api_version': '1', 'data_mode': 'demo', 'request_id': request.api_request_id}


def reply(request, data, status=200, pagination=None):
    body = {'data': data, 'meta': meta(request)}
    if pagination is not None:
        body['pagination'] = pagination
    response = JsonResponse(body, safe=True, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    return response


def paged(request, rows):
    try:
        limit, offset = int(request.GET.get('limit', 20)), int(request.GET.get('offset', 0))
    except (TypeError, ValueError):
        raise ApiError(400, 'INVALID_PAGINATION', 'Неверная пагинация.')
    require(1 <= limit <= 100 and 0 <= offset <= 2**31-1, 400, 'INVALID_PAGINATION', 'Неверная пагинация.')
    total = len(rows) if isinstance(rows, list) else rows.count()
    selected = list(rows[offset:offset+limit])
    return selected, {'limit': limit, 'offset': offset, 'total': total}


def authenticate(request):
    value = request.headers.get('Authorization', '')
    require(value.startswith('Bearer ') and 10 < len(value) < 200, 401, 'UNAUTHORIZED', 'Требуется действующий токен.')
    digest = hashlib.sha256(value[7:].encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        token = ApiToken.objects.select_related('user').filter(digest=digest, revoked_at__isnull=True, expires_at__gt=now).first()
        require(token is not None, 401, 'UNAUTHORIZED', 'Требуется действующий токен.')
        user = token.user
        require(user.is_active and user.email_confirmed, 401, 'UNAUTHORIZED', 'Аккаунт недоступен.')
        require(user.has_processing_consent, 403, 'CONSENT_REQUIRED', 'Обновите согласие в веб-кабинете.')
        require(user.role in {'candidate', 'employer'} and f'{user.role}.read' in token.scopes)
        if token.window_start is None or token.window_start <= now-timedelta(minutes=1):
            token.window_start, token.request_count = now, 0
        require(token.request_count < 60, 429, 'RATE_LIMITED', 'Лимит: 60 запросов в минуту.')
        token.request_count += 1
        token.last_used_at = now
        token.save(update_fields=['window_start', 'request_count', 'last_used_at'])
    request.api_token, request.user = token, user


def endpoint(role=None, private=False, methods=('GET',)):
    def decorate(fn):
        @csrf_exempt
        @wraps(fn)
        def wrapped(request, *args, **kwargs):
            import time
            started = time.monotonic()
            request.api_request_id = str(uuid4())
            try:
                authenticate(request)
                require(request.method in methods, 405, 'METHOD_NOT_ALLOWED', 'Метод не поддерживается.')
                if role:
                    require(request.user.role == role)
                if private:
                    require(request.api_token.kind == 'cli' and 'contacts.read' in request.api_token.scopes)
                response = fn(request, *args, **kwargs)
            except Http404:
                response = failure(request, 404, 'NOT_FOUND', 'Объект не найден.')
            except ApiError as exc:
                response = failure(request, exc.status, exc.code, exc.message, exc.details)
            except ValidationError:
                response = failure(request, 400, 'VALIDATION_ERROR', 'Проверьте параметры запроса.')
            except DatabaseError:
                response = failure(request, 503, 'UNAVAILABLE', 'Сервис временно недоступен.')
            except Exception as exc:
                log.error('internal_error request=%s type=%s',request.api_request_id,type(exc).__name__)
                response = failure(request,500,'INTERNAL_ERROR','Сервис временно недоступен.')
            if response.status_code == 429:
                response['Retry-After'] = '60'
            if response.status_code == 401:
                response['WWW-Authenticate'] = 'Bearer'
            if response.status_code == 405:
                response['Allow'] = ', '.join(methods)
            response['Cache-Control'] = 'no-store'
            response['X-Request-ID'] = request.api_request_id
            log.info('request=%s token=%s route=%s status=%s ms=%.1f', request.api_request_id,
                getattr(getattr(request, 'api_token', None), 'pk', None), fn.__name__, response.status_code,
                (time.monotonic()-started)*1000)
            return response
        return wrapped
    return decorate


def failure(request, status, code, message, details=None):
    error = {'code': code, 'message': message}
    if details:
        error['details'] = details
    return JsonResponse({'error': error, 'meta': meta(request)}, status=status)
