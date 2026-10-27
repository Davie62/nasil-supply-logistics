"""Access rules shared by the internal management views."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def staff_permission_required(*permissions):
    """Redirect guests to login; deny staff without every required permission."""
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_active or not request.user.is_staff:
                raise PermissionDenied
            if not request.user.has_perms(permissions):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
