from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect


def login_view(request):
    # If already logged in
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:

            login(request, user)

            if request.POST.get("remember_me"):
                request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
            else:
                request.session.set_expiry(0)  # Browser closes

            return redirect("dashboard")

        messages.error(request, "Invalid username or password.")

    return render(request, "accounts/login.html")


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")