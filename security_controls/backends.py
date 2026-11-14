from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db import transaction
from django.utils import timezone
from core.constants import MAX_LOGIN_ATTEMPTS, ACCOUNT_LOCK_MINUTES


class GuardedModelBackend(ModelBackend):
    """One lockout policy for customer login, staff login and Django admin."""
    @transaction.atomic
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        username = username or kwargs.get(User.USERNAME_FIELD)
        if not username or not password or len(username) > 150 or len(password) > 1024:
            return None
        user = User.objects.select_for_update().filter(**{User.USERNAME_FIELD: username}).first()
        if user is None:
            User().set_password(password)  # Match Django's unknown-account timing mitigation.
            return None
        if user.locked_until and user.locked_until > timezone.now():
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            user.failed_login_attempts, user.locked_until = 0, None
            user.save(update_fields=["failed_login_attempts", "locked_until"])
            return user
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            user.locked_until = timezone.now()+timedelta(minutes=ACCOUNT_LOCK_MINUTES)
        user.save(update_fields=["failed_login_attempts", "locked_until"])
        return None
