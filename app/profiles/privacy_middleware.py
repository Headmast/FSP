from uuid import uuid4
from django.db import DatabaseError
from django.http import JsonResponse
from .privacy import reconcile,PrivacyUnavailable


class PrivacyGuardMiddleware:
    def __init__(self,get_response):self.get_response=get_response

    def __call__(self,request):
        try:reconcile()
        except (PrivacyUnavailable,DatabaseError):
            if request.path.startswith('/api/v1/'):
                from api.core import failure
                request.api_request_id=str(uuid4())
                response=failure(request,503,'PRIVACY_UNAVAILABLE','Восстановление приватности временно недоступно.')
                response['X-Request-ID']=request.api_request_id
            else:response=JsonResponse({'status':'unavailable'},status=503)
            response['Cache-Control']='no-store'
            return response
        response=self.get_response(request)
        if request.user.is_authenticated or request.path.startswith(('/profile/','/candidates/','/invitations/','/drafts/','/assessments/','/api/v1/')):
            response['Cache-Control']='no-store'
        return response
