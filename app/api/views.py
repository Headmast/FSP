from .core import endpoint, reply


@endpoint()
def me(request):
    token = request.api_token
    return reply(request, {'id': request.user.pk, 'role': request.user.role, 'token_kind': token.kind,
        'scopes': token.scopes, 'expires_at': token.expires_at.isoformat()})
