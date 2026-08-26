from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import timedelta

from core.constants import ACCOUNT_LOCK_MINUTES, MAX_LOGIN_ATTEMPTS


def login_view(request):
    # If already logged in
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None and user.locked_until and user.locked_until > timezone.now():
            user = None

        if user is not None:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_login_attempts", "locked_until"])
            login(request, user)

            if request.POST.get("remember_me"):
                request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
            else:
                request.session.set_expiry(0)  # Browser closes

            return redirect("dashboard")

        if username:
            from .models import User
            existing_user = User.objects.filter(username=username).first()
            if existing_user:
                existing_user.failed_login_attempts += 1
                if existing_user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                    existing_user.locked_until = timezone.now() + timedelta(minutes=ACCOUNT_LOCK_MINUTES)
                existing_user.save(update_fields=["failed_login_attempts", "locked_until"])
        messages.error(request, "Invalid username or password.")

    return render(request, "accounts/login.html")


@login_required
def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    return redirect("login")