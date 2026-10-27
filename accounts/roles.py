"""Conservative role defaults. User/group administration stays with superusers."""
from django.contrib.auth.models import Group, Permission

BUSINESS_MODELS = (
    "customers.customer", "quotations.quote", "shipments.shipment",
    "logistics.service", "logistics.carrier", "core.contactmessage",
)
ORGANIZATION_MODELS = (
    "organization.company", "organization.branch", "organization.department",
    "organization.warehouse", "accounts.employeeprofile",
)


def model_permissions(models, actions):
    return {f"{model.split('.')[0]}.{action}_{model.split('.')[1]}"
            for model in models for action in actions}


ROLE_PERMISSIONS = {
    "Administrator": model_permissions(BUSINESS_MODELS + ORGANIZATION_MODELS, ("view", "add", "change")),
    "Operations Manager": model_permissions(BUSINESS_MODELS, ("view", "add", "change")),
    "Dispatcher": model_permissions(("shipments.shipment",), ("view", "add", "change"))
        | model_permissions(("quotations.quote", "customers.customer", "logistics.carrier"), ("view",)),
    "Finance Officer": model_permissions(("quotations.quote", "shipments.shipment", "customers.customer"), ("view",)),
    "Warehouse Officer": model_permissions(("shipments.shipment", "organization.warehouse"), ("view",)),
    "Sales Officer": model_permissions(("quotations.quote", "customers.customer", "core.contactmessage"), ("view", "add", "change"))
        | model_permissions(("logistics.service",), ("view",)),
    "HR Officer": model_permissions(("accounts.employeeprofile",), ("view", "add", "change"))
        | model_permissions(ORGANIZATION_MODELS[:-1], ("view",)),
    "IT Support": model_permissions(ORGANIZATION_MODELS, ("view",)),
}

# Preparing quotations does not grant approval authority.
for role in ("Administrator", "Operations Manager", "Finance Officer"):
    ROLE_PERMISSIONS[role] |= {"quotations.approve_quote", "core.view_auditrecord"}
ROLE_PERMISSIONS["Administrator"] |= {"quotations.approve_high_value_quote"}
ROLE_PERMISSIONS["Administrator"] |= model_permissions(("operations.inventoryitem",), ("view", "add", "change")) | {
    "operations.adjust_inventory", "operations.view_deliveryproof", "operations.add_deliveryproof",
    "operations.view_reports", "operations.export_reports", "operations.view_businesssettings", "operations.change_businesssettings",
    "operations.view_operationsevent", "accounts.delete_employeeprofile",
}
ROLE_PERMISSIONS["Operations Manager"] |= model_permissions(("operations.inventoryitem",), ("view", "add", "change")) | {
    "operations.adjust_inventory", "operations.view_deliveryproof", "operations.add_deliveryproof", "operations.view_reports", "operations.export_reports", "operations.view_operationsevent",
}
ROLE_PERMISSIONS["Warehouse Officer"] |= model_permissions(("operations.inventoryitem",), ("view", "add", "change")) | {"operations.adjust_inventory", "operations.view_reports", "operations.export_reports"}
ROLE_PERMISSIONS["Dispatcher"] |= {"operations.view_deliveryproof", "operations.add_deliveryproof", "operations.view_reports", "operations.export_reports"}
ROLE_PERMISSIONS["HR Officer"] |= {"accounts.delete_employeeprofile", "operations.view_reports", "operations.export_reports", "operations.view_operationsevent"}
for role in ("Finance Officer", "Sales Officer"):
    ROLE_PERMISSIONS[role] |= {"operations.view_reports", "operations.export_reports"}
for role in ("Administrator", "Sales Officer"):
    ROLE_PERMISSIONS[role] |= {"customer_services.manage_access", "customer_services.view_customeraccess", "customer_services.view_customernotification"}
for role in ("Administrator", "Finance Officer"):
    ROLE_PERMISSIONS[role] |= model_permissions(("payments.invoice",), ("view", "add", "change"))


CATALOG_MODELS = ("inventory.product", "inventory.stocklevel", "inventory.warehouse")
ORDER_MODELS = ("orders.order", "orders.orderline")
PURCHASING_MODELS = ("procurement.supplier", "procurement.supplieraudit", "procurement.procurementrequest", "procurement.purchaseorder", "procurement.purchaseline", "procurement.goodsreceipt")
FLEET_MODELS = ("fleet.vehicle", "fleet.driver", "fleet.assignment", "fleet.routecheckpoint", "fleet.maintenance")
FINANCE_MODELS = ("finance.invoice", "finance.payment", "finance.reconciliation", "finance.statementline")
INTEGRATION_MODELS = ("integrations.connection", "integrations.integrationjob", "integrations.gatewayintent", "integrations.webhookevent")
ROLE_PERMISSIONS["Administrator"] |= model_permissions(CATALOG_MODELS + ORDER_MODELS + PURCHASING_MODELS + FLEET_MODELS + FINANCE_MODELS + INTEGRATION_MODELS, ("view", "add", "change")) | {
    "orders.approve_order", "orders.fulfill_order", "procurement.approve_procurementrequest", "procurement.approve_purchaseorder", "procurement.receive_purchaseorder", "finance.reverse_payment"}
ROLE_PERMISSIONS["Operations Manager"] |= model_permissions(CATALOG_MODELS + ORDER_MODELS + PURCHASING_MODELS + FLEET_MODELS, ("view", "add", "change")) | {"orders.fulfill_order", "procurement.receive_purchaseorder"}
ROLE_PERMISSIONS["Warehouse Officer"] |= model_permissions(CATALOG_MODELS, ("view", "add", "change")) | model_permissions(ORDER_MODELS + PURCHASING_MODELS, ("view",)) | {
    "orders.change_order", "orders.fulfill_order", "procurement.receive_purchaseorder", "quotations.view_quote", "shipments.add_shipment"}
ROLE_PERMISSIONS["Sales Officer"] |= model_permissions(ORDER_MODELS, ("view", "add", "change")) | model_permissions(CATALOG_MODELS, ("view",))
ROLE_PERMISSIONS["Dispatcher"] |= model_permissions(FLEET_MODELS + ORDER_MODELS, ("view",)) | {"fleet.add_assignment", "fleet.change_assignment", "fleet.add_routecheckpoint", "orders.change_order"}
ROLE_PERMISSIONS["Finance Officer"] |= model_permissions(FINANCE_MODELS, ("view", "add", "change")) | model_permissions(PURCHASING_MODELS, ("view",)) | {
    "integrations.view_connection", "integrations.view_integrationjob", "integrations.view_gatewayintent", "integrations.add_integrationjob", "integrations.add_gatewayintent"}
ROLE_PERMISSIONS["Procurement Officer"] = model_permissions(PURCHASING_MODELS, ("view", "add", "change")) | model_permissions(CATALOG_MODELS + ORDER_MODELS, ("view",)) | {"operations.view_reports", "operations.export_reports"}


def seed_role_permissions():
    for name, required in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=name)
        permissions = Permission.objects.select_related("content_type").filter(
            content_type__app_label__in={key.split('.')[0] for key in required},
        )
        # Add defaults without removing any deliberate administrator assignments.
        group.permissions.add(*(permission for permission in permissions
            if f"{permission.content_type.app_label}.{permission.codename}" in required))
