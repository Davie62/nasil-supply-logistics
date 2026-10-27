import hashlib
from decimal import Decimal
from io import BytesIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from accounts.models import User, EmployeeProfile
from accounts.services import EmployeeService
from core.business_rules import require_permission, validate_version, decimal_value
from core.models import AuditRecord
from quotations.models import Quote
from shipments.models import Shipment
from .models import BusinessSettings, InventoryItem, StockMovement, DeliveryProof, OperationsEvent


def managed_save(instance, **kwargs):
    instance._operations_write = True
    try:
        instance.save(**kwargs)
    finally:
        instance.__dict__.pop("_operations_write", None)


def event(actor, entity_type, entity_id, action, **details):
    return OperationsEvent.objects.create(actor=actor, actor_label=actor.get_username(), entity_type=entity_type, entity_id=str(entity_id), action=action, details=details)


def require_admin(actor):
    if not actor.is_superuser and not actor.groups.filter(name="Administrator").exists():
        raise PermissionDenied("Only an administrator may change business policy.")


@transaction.atomic
def save_settings(*, actor, data, expected_version):
    require_permission(actor, "operations.change_businesssettings")
    require_admin(actor)
    # Force INSERT so competing first creation cannot overwrite an existing policy.
    # Lock the singleton before checking the version or changing its values.
    if not BusinessSettings.objects.filter(pk=1).exists():
        try:
            with transaction.atomic():
                managed_save(BusinessSettings(pk=1), force_insert=True)
        except IntegrityError:
            pass
    policy = BusinessSettings.objects.select_for_update().get(pk=1)
    validate_version(policy, expected_version)
    allowed = {"local_currency", "international_currency", "ugx_approval_threshold", "usd_approval_threshold", "notify_quotations", "notify_enquiries", "notify_overdue"}
    if set(data) - allowed:
        raise ValidationError("Unsupported settings fields.")
    before = {key: str(getattr(policy, key)) for key in allowed}
    for key, value in data.items():
        setattr(policy, key, value)
    policy.updated_by = actor
    policy.version += 1
    policy.full_clean()
    managed_save(policy)
    event(actor, "settings", 1, "settings_updated", before=before, after={key: str(getattr(policy, key)) for key in allowed})
    return policy


@transaction.atomic
def save_inventory(*, actor, data, item_id=None, expected_version=None):
    require_permission(actor, "operations.change_inventoryitem" if item_id else "operations.add_inventoryitem")
    item = InventoryItem.objects.select_for_update().get(pk=item_id) if item_id else InventoryItem()
    validate_version(item, expected_version)
    if set(data) - {"sku", "name", "warehouse", "unit", "reorder_level", "is_active"}:
        raise ValidationError("Stock balances must be changed using stock movements.")
    if item_id and (data.get("warehouse", item.warehouse) != item.warehouse or data.get("unit", item.unit) != item.unit):
        raise ValidationError("Warehouse and unit cannot change after item creation.")
    before = {field: str(getattr(item, field)) for field in data} if item_id else {}
    for key, value in data.items():
        setattr(item, key, value)
    if not item.warehouse.is_active or item.warehouse.is_deleted:
        raise ValidationError("Choose an active warehouse.")
    item.sku = item.sku.strip().upper()
    if item_id:
        from inventory.models import StockLevel
        from inventory.services import reserved_for_item
        linked = StockLevel.objects.select_related("product").filter(item_id=item_id).first()
        if linked and (item.sku != linked.product.sku or item.unit != linked.product.unit):
            raise ValidationError("Linked catalogue SKU and unit cannot be changed through the legacy stock screen.")
        if not item.is_active and reserved_for_item(item.pk):
            raise ValidationError("Release order reservations before archiving this stock item.")
    item.version += 1
    item.full_clean()
    managed_save(item)
    event(actor, "inventory", item.pk, "item_updated" if item_id else "item_created", before=before, after={field: str(getattr(item, field)) for field in data})
    return item


@transaction.atomic
def move_stock(*, actor, item_id, quantity_change, reason, expected_version):
    require_permission(actor, "operations.adjust_inventory")
    item = InventoryItem.objects.select_for_update().get(pk=item_id)
    validate_version(item, expected_version)
    if not item.is_active:
        raise ValidationError("Archived items cannot receive stock movements.")
    if not item.warehouse.is_active or item.warehouse.is_deleted:
        raise ValidationError("Stock movements require an active warehouse.")
    try:
        delta = Decimal(str(quantity_change))
    except Exception:
        raise ValidationError("Enter a valid stock quantity.")
    if not delta.is_finite() or abs(delta) > Decimal("999999999999.999") or delta == 0 or delta != delta.quantize(Decimal("0.001")) or not reason.strip():
        raise ValidationError("Enter a nonzero quantity with up to three decimals and a reason.")
    from inventory.services import reserved_for_item
    if item.quantity + delta < reserved_for_item(item.pk):
        raise ValidationError("This movement would consume stock reserved for approved orders.")
    item.quantity += delta
    item.version += 1
    item.full_clean()
    managed_save(item)
    movement = StockMovement(item=item, quantity_change=delta, balance_after=item.quantity, reason=reason.strip(), actor=actor)
    movement.full_clean()
    managed_save(movement)
    event(actor, "inventory", item.pk, "stock_moved", movement=str(movement.reference), quantity_change=str(delta), balance_after=str(item.quantity), reason=reason)
    return movement


def guard_staff_target(actor, user):
    privileged = user.is_superuser or user.groups.filter(name="Administrator").exists() or user.has_perm("accounts.change_user") or user.has_perm("auth.change_group")
    if privileged and not actor.is_superuser:
        raise PermissionDenied("Only a superuser may manage privileged staff accounts.")


@transaction.atomic
def save_staff(*, actor, data, profile_id=None, expected_version=None):
    require_permission(actor, "accounts.change_employeeprofile" if profile_id else "accounts.add_employeeprofile")
    profile = EmployeeProfile.objects.select_for_update().select_related("user").get(pk=profile_id) if profile_id else None
    if profile:
        user = User.objects.select_for_update().get(pk=profile.user_id)
        guard_staff_target(actor, user)
        if profile.updated_at.isoformat() != expected_version:
            raise ValidationError("This staff record changed. Reload before saving.")
        if not actor.is_superuser and (data.get("password") or data.get("username") != user.username or data.get("email", "").lower() != user.email.lower()):
            raise PermissionDenied("Only a superuser may change an existing staff member's login identity or password.")
    else:
        user = User()
        if not data.get("password"):
            raise ValidationError("A password is required for a new staff account.")
    before = {}
    if profile:
        before = {field: str(getattr(user, field)) for field in ("username", "email", "first_name", "last_name", "is_active")}
        before.update({field: str(getattr(profile, field)) for field in ("department_id", "position", "phone_number", "hire_date", "status")})
    if actor.pk == user.pk and data.get("status") in {"SUSPENDED", "TERMINATED"}:
        raise ValidationError("You cannot deactivate your own account.")
    allowed = {"username", "email", "first_name", "last_name", "department", "position", "phone_number", "hire_date", "status", "password"}
    if set(data) - allowed:
        raise ValidationError("User permissions and roles must be managed separately by a superuser.")
    for key in ("username", "email", "first_name", "last_name"):
        setattr(user, key, data[key])
    if data.get("password"):
        from django.contrib.auth.password_validation import validate_password
        validate_password(data["password"], user)
        user.set_password(data["password"])
    user.is_active = data["status"] in {"ACTIVE", "LEAVE"}
    user.full_clean(exclude=["password"])
    user.save()  # New users remain non-staff until their explicit profile exists.
    if not profile:
        profile = EmployeeProfile(user=user, employee_id=EmployeeService.generate_employee_id())
    for key in ("department", "position", "phone_number", "hire_date", "status"):
        setattr(profile, key, data.get(key))
    if not profile.department.is_active or profile.department.is_deleted or not profile.department.branch.is_active or profile.department.branch.is_deleted:
        raise ValidationError("Choose a department in an active branch.")
    profile.branch = profile.department.branch
    profile.full_clean()
    profile.save()
    if not user.is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    after = {field: str(getattr(user, field)) for field in ("username", "email", "first_name", "last_name", "is_active")}
    after.update({field: str(getattr(profile, field)) for field in ("department_id", "position", "phone_number", "hire_date", "status")})
    event(actor, "staff", profile.pk, "staff_updated" if profile_id else "staff_created", employee_id=profile.employee_id, before=before, after=after, password_changed=bool(data.get("password")))
    return profile


@transaction.atomic
def deactivate_staff(*, actor, profile_id, expected_version, reason):
    require_permission(actor, "accounts.delete_employeeprofile")
    profile = EmployeeProfile.objects.select_for_update().select_related("user").get(pk=profile_id)
    user = User.objects.select_for_update().get(pk=profile.user_id)
    guard_staff_target(actor, user)
    if actor.pk == user.pk:
        raise ValidationError("You cannot deactivate your own account.")
    if profile.updated_at.isoformat() != expected_version or not reason.strip():
        raise ValidationError("A current record version and a reason are required.")
    user.is_active = False
    user.save(update_fields=["is_active"])
    profile.status = "TERMINATED"
    profile.save(update_fields=["status", "updated_at"])
    event(actor, "staff", profile.pk, "staff_deactivated", reason=reason, employee_id=profile.employee_id)
    return profile


def validate_evidence(upload):
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError("Delivery evidence must be 5 MB or smaller.")
    content = upload.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024 or not content:
        raise ValidationError("Upload a nonempty file of 5 MB or smaller.")
    if content.startswith(b"%PDF-"):
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 30:
                raise ValueError()
        except Exception:
            raise ValidationError("Upload a valid unencrypted PDF with up to 30 pages.")
        return content, "application/pdf", "delivery-evidence.pdf"
    try:
        with Image.open(BytesIO(content)) as picture:
            if picture.format not in {"PNG", "JPEG"} or picture.width * picture.height > 16000000:
                raise ValueError()
            kind = picture.format
            picture.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError("Upload a valid PNG, JPEG, or PDF delivery document.")
    return content, "image/png" if kind == "PNG" else "image/jpeg", "delivery-evidence.png" if kind == "PNG" else "delivery-evidence.jpg"


@transaction.atomic
def record_delivery_proof(*, actor, shipment_id, recipient_name, delivered_at, notes, evidence):
    require_permission(actor, "operations.add_deliveryproof", "shipments.view_shipment")
    quote_id = Shipment.objects.values_list("quote_id", flat=True).get(pk=shipment_id)
    Quote.objects.select_for_update().get(pk=quote_id)
    shipment = Shipment.objects.select_for_update().get(pk=shipment_id)
    if shipment.status != "delivered":
        raise ValidationError("Delivery evidence can only be recorded for a delivered shipment.")
    if delivered_at > timezone.now() or delivered_at < shipment.created_at.replace(microsecond=0):
        raise ValidationError("Delivery time must fall between booking and now.")
    if DeliveryProof.objects.filter(shipment=shipment).exists():
        raise ValidationError("Delivery proof is already recorded and cannot be overwritten.")
    content, content_type, filename = validate_evidence(evidence)
    proof = DeliveryProof(shipment=shipment, recipient_name=recipient_name, delivered_at=delivered_at, notes=notes,
                          evidence=content, evidence_name=filename, evidence_type=content_type, evidence_sha256=hashlib.sha256(content).hexdigest(), recorded_by=actor)
    proof.full_clean()
    managed_save(proof)
    audit = AuditRecord.objects.create(quote=shipment.quote, shipment=shipment, actor=actor, actor_label=actor.get_username(), action="delivery_proof_recorded", from_status=shipment.status, to_status=shipment.status, object_version=shipment.version, changes={"delivery_proof": {"before": None, "after": str(proof.reference)}, "evidence_sha256": {"before": None, "after": proof.evidence_sha256}})
    event(actor, "proof", proof.pk, "proof_recorded", proof_reference=str(proof.reference), shipment=shipment.tracking_number, audit_id=audit.pk, sha256=proof.evidence_sha256)
    return proof
