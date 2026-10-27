from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import ContactMessage
from .permissions import staff_permission_required
from operations.querysets import paginate, search


@staff_permission_required("core.view_contactmessage")
def contact_message_list(request):
    records = ContactMessage.objects.order_by("-created_at")
    active_filter = "Unread enquiries" if request.GET.get("unread") == "1" else ""
    if active_filter:
        records = records.filter(is_read=False)
    page, pagination = paginate(request, search(records, request.GET.get("q"), ("name", "email", "subject")))
    rows = [{
        "values": [record.name, record.email, record.subject, "Read" if record.is_read else "Unread"],
        "url": f"/messages/{record.pk}/read/",
    } for record in page]
    return render(request, "dashboard/workflow_list.html", {
        "title": "Contact messages", "active_filter": active_filter, "clear_filter_url": "contact_message_list", "eyebrow": "CUSTOMER COMMUNICATION",
        **pagination,
        "description": "Review enquiries submitted through the public contact form.",
        "columns": ["Name", "Email", "Subject", "Status"], "rows": rows, "status_column": 3,
    })


@staff_permission_required("core.view_contactmessage")
@require_http_methods(["GET", "POST"])
def contact_message_read(request, pk):
    message = get_object_or_404(ContactMessage, pk=pk)
    if request.method == "POST":
        if not request.user.has_perm("core.change_contactmessage"):
            raise PermissionDenied
        message.is_read = True
        message.save(update_fields=["is_read"])
        return redirect("contact_message_read", pk=pk)
    return render(request, "dashboard/message_detail.html", {"message": message})
