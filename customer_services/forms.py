from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm
from django.urls import reverse
from accounts.models import User
from operations.forms import StyledFormMixin
from .models import CustomerAccess, CustomerNotification, NotificationPreference, RegistrationVerification


class PortalLoginForm(StyledFormMixin, forms.Form):
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autocomplete": "username"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class ActivationForm(StyledFormMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "password1", "password2"]


class RegistrationForm(StyledFormMixin, UserCreationForm):
    full_name = forms.CharField(max_length=255, label="Full name")
    email = forms.EmailField(max_length=254)
    phone = forms.CharField(max_length=20, min_length=5, label="Phone number")
    company_name = forms.CharField(max_length=255, required=False, label="Company (optional)")

    class Meta:
        model = User
        fields = ["full_name", "email", "phone", "company_name", "username", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.pop("autofocus", None)
        self.fields["username"].widget.attrs.update(autocapitalize="none", spellcheck="false")
        for name, autocomplete in {"full_name": "name", "email": "email", "phone": "tel", "company_name": "organization", "username": "username"}.items():
            self.fields[name].widget.attrs["autocomplete"] = autocomplete

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email already has an account. Sign in or contact NASIL for help. Staff accounts use the staff login.")
        return email


class VerificationForm(StyledFormMixin, forms.Form):
    code = forms.RegexField(r"^\d{6}$", label="Verification code", error_messages={"invalid": "Enter the six-digit code from your email."},
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "maxlength": "6", "pattern": "[0-9]{6}"}))


class PreferenceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = ["preferred_channel", "sms_number", "sms_consent", "enabled", "quotation_updates", "shipment_updates", "delivery_updates"]
        labels = {"sms_consent": "I consent to receiving shipment-related SMS at this number", "enabled": "Enable email/SMS notifications"}
        help_texts = {"sms_number": "Include country code, for example +256700000000. Email remains your verified account address."}


class PortalPasswordResetForm(StyledFormMixin, PasswordResetForm):
    def get_users(self, email):
        for user in super().get_users(email):
            verified = user.is_verified and CustomerAccess.objects.filter(user=user, enabled=True, verified_email__iexact=email, customer__email__iexact=email).exists()
            pending = not user.is_verified and RegistrationVerification.objects.filter(user=user, completed_at__isnull=True, customer__email__iexact=email).exists()
            if not user.is_staff and not user.is_superuser and (verified or pending):
                yield user

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        import uuid
        from .notifications import schedule
        user = context["user"]
        access = CustomerAccess.objects.filter(user=user, enabled=True).first()
        customer = access.customer if access else RegistrationVerification.objects.get(user=user, completed_at__isnull=True).customer
        notification = CustomerNotification.objects.create(customer=customer, event_key="password-reset:" + uuid.uuid4().hex,
            kind="password_reset", title="Reset your NASIL portal password", body=f"Your NASIL username is {user.username}. Use the secure link to reset your customer portal password. If you did not request this, ignore this message.",
            channel="email", recipient=user.email, payload={"uid": context["uid"], "token": context["token"]})
        schedule(notification)
