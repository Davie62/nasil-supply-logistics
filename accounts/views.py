from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import timedelta

from core.constants import ACCOUNT_LOCK_MINUTES, MAX_LOGIN_ATTEMPTS
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("password")
def login_view(request):
    # If already logged in
    if request.user.is_authenticated:
        return redirect("dashboard" if request.user.is_staff else "portal_dashboard")

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None and not user.is_staff:
            user = None

        if user is not None:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid username or password.")

    return render(request, "accounts/login.html")


@login_required
def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    return redirect("login")
