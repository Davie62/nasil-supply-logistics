from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import User, EmployeeProfile
from organization.models import Department
from .models import BusinessSettings, InventoryItem


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control")


class InventoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ["sku", "name", "warehouse", "unit", "reorder_level", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["warehouse"].queryset = self.fields["warehouse"].queryset.filter(is_active=True)
        if self.instance.pk:
            self.fields["warehouse"].disabled = True
            self.fields["unit"].disabled = True
            self.fields["record_version"] = forms.IntegerField(initial=self.instance.version, widget=forms.HiddenInput)


class StockMovementForm(StyledFormMixin, forms.Form):
    quantity_change = forms.DecimalField(max_digits=15, decimal_places=3, help_text="Positive to receive; negative to issue. Stock cannot fall below zero.")
    reason = forms.CharField(max_length=255)
    record_version = forms.IntegerField(widget=forms.HiddenInput)


class StaffForm(StyledFormMixin, forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    department = forms.ModelChoiceField(queryset=Department.objects.filter(branch__is_active=True))
    position = forms.CharField(max_length=100)
    phone_number = forms.CharField(max_length=20, required=False)
    hire_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(choices=EmployeeProfile.STATUS)
    password = forms.CharField(required=False, widget=forms.PasswordInput, help_text="Required for new staff. Leave blank to keep an existing password.")
    record_version = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, profile=None, **kwargs):
        self.profile = profile
        super().__init__(*args, **kwargs)
        if profile:
            self.initial.update({field: getattr(profile.user, field) for field in ("username", "email", "first_name", "last_name")})
            self.initial.update({field: getattr(profile, field) for field in ("position", "phone_number", "hire_date", "status")})
            self.initial.update(department=profile.department_id, record_version=profile.updated_at.isoformat())
        else:
            self.fields["password"].required = True
            self.initial["status"] = "ACTIVE"

    def clean(self):
        data = super().clean()
        excluded = self.profile.user_id if self.profile else None
        for field in ("username", "email"):
            value = data.get(field)
            if value and User.objects.filter(**{field + "__iexact": value}).exclude(pk=excluded).exists():
                self.add_error(field, "This value is already in use.")
        phone = data.get("phone_number") or None
        if phone and EmployeeProfile.objects.filter(phone_number=phone).exclude(pk=self.profile.pk if self.profile else None).exists():
            self.add_error("phone_number", "This phone number is already in use.")
        if data.get("password"):
            user = User(**{key: data.get(key, "") for key in ("username", "email", "first_name", "last_name")})
            try:
                validate_password(data["password"], user)
            except ValidationError as error:
                self.add_error("password", error)
        data["phone_number"] = phone
        if data.get("email"):
            data["email"] = data["email"].lower()
        return data


class SettingsForm(StyledFormMixin, forms.ModelForm):
    record_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = BusinessSettings
        fields = ["local_currency", "international_currency", "ugx_approval_threshold", "usd_approval_threshold", "notify_quotations", "notify_enquiries", "notify_overdue"]
        labels = {"ugx_approval_threshold": "UGX approval threshold", "usd_approval_threshold": "USD approval threshold", "notify_quotations": "Show pending quotation alerts", "notify_enquiries": "Show unread enquiry alerts", "notify_overdue": "Show overdue shipment alerts"}


class DeliveryProofForm(StyledFormMixin, forms.Form):
    recipient_name = forms.CharField(max_length=200)
    delivered_at = forms.DateTimeField(initial=timezone.now, widget=forms.DateTimeInput(attrs={"type": "datetime-local", "step": "1"}, format="%Y-%m-%dT%H:%M:%S"))
    notes = forms.CharField(max_length=4000, required=False, widget=forms.Textarea(attrs={"rows": 3}))
    evidence = forms.FileField(help_text="Signed delivery note or signature image: PDF, PNG or JPEG, up to 5 MB. Stored privately.")


class ReportFilterForm(StyledFormMixin, forms.Form):
    q = forms.CharField(required=False, max_length=150, label="Search")
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    status = forms.ChoiceField(required=False)
    staff = forms.ModelChoiceField(required=False, queryset=User.objects.filter(is_staff=True).order_by("username"), label="Staff responsible")

    def __init__(self, *args, statuses=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [("", "All statuses"), *statuses]

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            raise ValidationError("Start date must be before or equal to end date.")
        if data.get("date_to") and data["date_to"].year == 9999:
            raise ValidationError("Choose an end date before year 9999.")
        return data
