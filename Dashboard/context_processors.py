from .presentation import operational_notifications


def dashboard_shell(request):
    internal_paths = ("/finance/", "/inventory/", "/orders/", "/procurement/", "/fleet/", "/integrations/", "/customer-services/", "/operations/", "/dashboard/", "/shipments/", "/quotations/", "/customers/", "/messages/", "/services/manage/", "/carriers/")
    if not request.path.startswith(internal_paths) or not request.user.is_authenticated or not request.user.is_staff:
        return {}
    return operational_notifications(request)
