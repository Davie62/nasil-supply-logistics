# Internal operations

Implemented on 27 October 2026 in the existing Django application. The dashboard retains the Dasher Bootstrap layout. All examples below refer to executable project code.

## Screens and navigation

| Area | URLs | Capabilities |
| --- | --- | --- |
| Quotations | `/quotations/`, `/quotations/<id>/` | Server-side search/status filters, 25-row pages, commercial summary and paginated audit history; authorized users can open the existing approval/edit workflow. |
| Shipments | `/shipments/`, `/shipments/<id>/` | Server-side search/status/overdue filters, detail screens, route/carrier/timestamps, linked quotation and delivery proof; workflow actions retain existing rules. |
| Inventory | `/operations/inventory/` | Warehouse/SKU items, detail/edit/archive screens, receive/issue stock, current balances, reorder indicators and movement history. |
| Staff | `/operations/staff/` | Search/status filter, detail, create, edit, suspend/terminate/reactivate, and explicit deactivation confirmation. Superusers have a link to account role management. |
| Reports | `/operations/reports/` | Quotations, shipments, inventory, staff and delivery-proof reports, date/status/staff filters and CSV/PDF exports. |
| Settings | `/operations/settings/` | Approval thresholds, supported local/international currency assignment, dashboard alert preferences, optimistic version checks and audit events. |

Navigation and module search expose modules according to permissions. Existing `/dashboard/employees/`, `/dashboard/reports/`, and `/dashboard/settings/` links redirect to the implemented screens. Orders remain planned.

Customer, carrier, service and enquiry lists also use server-side search and pagination. Queries use deterministic ordering; related records are loaded using `select_related`. Lists materialize only the current page. Report audit references use SQL subqueries, avoiding one lookup per row.

## Inventory semantics

`InventoryItem` represents one SKU in one warehouse. The same SKU can exist in different warehouses. Each item has an immutable warehouse and unit, a nonnegative current quantity, reorder level, active/archive state and version.

`move_stock` locks the item, checks its version, rejects zero/nonfinite/oversized quantities, requires a reason, and records a `StockMovement` with signed quantity change and balance after the movement. The balance, ledger entry and audit event commit together. A failure rolls all three back. Negative stock and stock movements on archived items are rejected. Archive instead of deleting items; received/issued units must match the item's unit.

This is a stock ledger for manual receipts and issues. Purchase orders, inventory valuation, lot/serial tracking, reservations, warehouse transfers and automatic shipment consumption are future extensions.

```python
from operations.services import save_inventory, move_stock

item = save_inventory(actor=request.user, data={
    "sku": "PACK-001", "name": "Shipping crates", "warehouse": warehouse,
    "unit": "crates", "reorder_level": 5, "is_active": True,
})
movement = move_stock(actor=request.user, item_id=item.pk,
                      quantity_change="20.000", reason="Supplier receipt",
                      expected_version=item.version)
```

## Staff lifecycle and access

Staff CRUD uses the existing `User`, `EmployeeProfile`, department/branch models and employee ID sequence. Profiles always follow their department's branch. New staff get a validated password and **no role grants**; a superuser assigns roles using the linked account administration page. Role/group and superuser fields are never accepted by the staff form or service.

Deactivation is the delete operation: it marks employment terminated and disables authentication, retaining the user, employee ID, linked business records and audit history. Suspension also disables login. Active and on-leave staff retain login eligibility. Deactivation requires an explicit POST, current record version and reason; users cannot deactivate themselves. A non-superuser cannot manage a privileged account or change an existing staff member's login identity/password.

| Role | New defaults |
| --- | --- |
| Administrator | Inventory management/adjustment, delivery proof, reports/exports, settings, staff deactivation, operations audit register. |
| Operations Manager | Inventory management/adjustment, delivery proof, reports/exports, operations audit register. |
| Dispatcher | Delivery proof and reports/exports within existing shipment permissions. |
| Warehouse Officer | Inventory management/adjustment and inventory reports/exports. |
| HR Officer | Staff lifecycle including deactivation, staff reports/exports and operations audit register. |
| Finance / Sales Officer | Reports/exports restricted to their existing model viewing permissions. |

All routes require active staff and explicit model permissions. Report viewing and exporting are separate permissions (`operations.view_reports` and `operations.export_reports`). Each report additionally requires its model's viewing permission; delivery evidence also requires shipment viewing. Existing branch/customer isolation limitations remain unchanged: this is a single-organization internal application.

## Settings and currencies

Defaults remain local **UGX**, international **USD**, Admin approval above **UGX 50,000,000** or **USD 15,000**. The settings page is limited to a superuser or Administrator with the relevant viewing/change permissions. The maker/approver separation remains mandatory, including for administrators.

Before the first settings save, the environment-based threshold policy is used. Once saved, the database singleton becomes authoritative. Threshold changes affect subsequent approval decisions; completed approvals are not retrospectively revoked.

Currency assignments support UGX and USD, with distinct choices for local and international work. Existing quotations retain their recorded currency when their terms are edited. New quotations, or drafts whose trade scope changes, use the current currency assignment. A currency change is an explicit policy decision, not a foreign-exchange conversion; reprice scope changes before approval.

Notification preferences control existing dashboard alerts for pending quotations, unread enquiries and overdue shipments. They do not send email/SMS/push messages. Settings and stock changes use version checks to reject stale forms.

## Proof of delivery

On a delivered shipment's detail screen, authorized staff can upload a signature image or signed delivery document. Required fields are recipient, delivery time and evidence; notes are optional. Delivery time uses Africa/Kampala and second precision, between booking and the present. Evidence accepts structurally validated PNG, JPEG, or unencrypted PDF (up to 30 pages), maximum 5 MB.

Evidence is stored privately as database binary data, linked one-to-one to the shipment, with a UUID proof reference, SHA-256 digest, recorder and recording time. It has no public media URL. Authenticated attachment downloads require both proof and shipment permissions, use no-store headers, and create audit events. Include this evidence in database backup/retention planning.

Recorded proof cannot be overwritten through normal ORM, UI or admin writes. A shipment audit record and an operations event capture its reference and file digest. PDF exports embed image-based signatures; uploaded PDF originals remain available as a separate authenticated download. This is uploaded signature/document capture, not a cryptographic signing service.

## Reports and export utilities

Date filters use record creation time, or proof recording time, inclusive of both selected dates in Africa/Kampala. Staff filters mean quotation preparer, shipment booker, stock movement actor, employee account, or proof recorder respectively. Inventory quantities are current balances for matching items, not reconstructed historical stock. Status filters use each report's own allowed statuses. Invalid filters return no data and block exporting.

CSV and PDF use the same filtered QuerySet as the on-screen report, independent of the current page. CSV supports up to 10,000 rows; PDF supports 1,000. Larger result sets must be narrowed; exports never silently truncate. Quotation totals are shown per currency rather than mixing UGX/USD.

Exports include NASIL branding, generation timestamp, filters/creator, export audit UUID and per-record audit references. CSV uses UTF-8 with BOM, standard quoting and formula-injection neutralization. PDFs use ReportLab, embedded fonts, repeated table headers, wrapped cells, page numbers and audit-reference footers. Original signed evidence can be downloaded separately. Legacy staff with no operations events are labelled accordingly.

```python
from operations.exports import export_csv, export_pdf
from operations.services import event

audit = event(request.user, "report", "inventory", "report_exported",
              format="csv", count=queryset.count())
return export_csv(
    title="Inventory report", columns=["SKU", "Quantity", "Warehouse"],
    rows=queryset.values_list("sku", "quantity", "warehouse__name").iterator(),
    reference=audit.reference,
)
# export_pdf accepts the same columns/rows/reference, with optional metadata.
```

## Reusable views and template partials

```python
from django.urls import reverse
from django.shortcuts import render
from core.permissions import staff_permission_required
from operations.models import InventoryItem
from operations.querysets import search, paginate

@staff_permission_required("operations.view_inventoryitem")
def inventory_list(request):
    queryset = search(
        InventoryItem.objects.select_related("warehouse").order_by("sku", "pk"),
        request.GET.get("q"), ("sku", "name", "warehouse__name"),
    )
    page, context = paginate(request, queryset)
    return render(request, "dashboard/workflow_list.html", {
        "title": "Inventory", "columns": ["SKU", "Item", "Quantity"],
        "rows": [{"values": [item.sku, item.name, item.quantity],
                  "url": reverse("inventory_detail", args=[item.pk])}
                 for item in page], **context,
    })
```

```django
{% include "operations/components/search.html" %}
{% include "operations/components/table.html" %}
{% include "operations/components/pagination.html" %}
```

Pagination preserves search and filter parameters with the `querystring` template tag. The detail template exposes `record_summary`, `record_extra`, and `record_history` blocks. Shared partials render fields, form errors, audit history, tables and pagination. Upload forms explicitly use multipart encoding.

## Audit and write boundaries

Existing `AuditRecord` remains the quotation/shipment register. `OperationsEvent` covers stock, staff, settings, report exports and evidence access using actor snapshots and UUID references. Events are append-only through normal ORM/admin interfaces. Guarded inventory/settings/proof saves reject normal direct/bulk writes; use services. Raw SQL, `_base_manager`, raw fixture saves and private write flags are trusted developer/database escape hatches, not authorized business entry points.

## Rollout and verification

```powershell
$env:DJANGO_DEBUG = 'true'  # local development only
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_roles
python manage.py test
python manage.py makemigrations --check --dry-run
```

Back up before migration and restart the running application after updating dependencies/schema. `seed_roles` adds the new default permissions without changing user memberships or removing deliberate existing grants. No QA/sample stock is added to the business database.

The local suite covers allowed/denied workflows, stale forms, rollback, file validation, private downloads, export headers/audit references, filters, pagination and bounded query counts. Concurrency tests require PostgreSQL and skip on SQLite; run them on an isolated PostgreSQL database before production. PDF QA uses a separate fixture database and PyMuPDF rendering; PyMuPDF is a verification tool, not a runtime requirement.

Primary references: [Django pagination](https://docs.djangoproject.com/en/6.0/topics/pagination/), [PDF responses](https://docs.djangoproject.com/en/6.0/howto/outputting-pdf/), [multipart uploads](https://docs.djangoproject.com/en/6.0/topics/http/file-uploads/).
