from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

def role_required(role):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.role != role or not request.user.email_confirmed:
                raise PermissionDenied
            if not request.user.has_processing_consent:
                return redirect('consent')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
