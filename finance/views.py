from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from core.business_rules import require_permission
from .forms import ImportStatementForm
from .services import import_statement

@login_required
@require_http_methods(["GET", "POST"])
def statement_import(request):
    require_permission(request.user, "finance.add_reconciliation", "finance.view_reconciliation")
    form = ImportStatementForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if form.is_valid():
        try:
            statement = import_statement(actor=request.user, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error.messages if isinstance(error, ValidationError) else "Statement reference already exists or contains duplicate references.")
        else:
            return redirect("finance:reconciliations_detail", pk=statement.pk)
    return render(request, "dashboard/workflow_form.html", {"title": "Import bank statement", "eyebrow": "FINANCE", "form": form, "back_url": "finance:reconciliations_list", "multipart": True})
