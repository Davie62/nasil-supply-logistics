from django.urls import path
from operations.module_ui import resource_urls, home_view, Action, EmptyActionForm
from .models import Connection, IntegrationJob, GatewayIntent
from .forms import ConnectionForm, DocumentForm
from .services import save_connection, queue_document, retry_job, recheck_intent
from .views import customer_pay, customer_payment, flutterwave_webhook

app_name = "integrations"
urlpatterns = [path("", home_view("Integration hub", [("Provider connections", "integrations:connections_list", "integrations.view_connection"),
    ("Delivery queue", "integrations:jobs_list", "integrations.view_integrationjob"), ("Gateway payments", "integrations:intents_list", "integrations.view_gatewayintent")],
    lambda request: [("Configured connections", Connection.objects.filter(is_active=True).count()), ("Pending jobs", IntegrationJob.objects.filter(status__in=["queued", "retry"]).count()),
        ("Payments requiring review", GatewayIntent.objects.filter(status="review").count())]), name="home"),
    path("pay/<int:pk>/", customer_pay, name="customer_pay"), path("payment/<uuid:reference>/", customer_payment, name="customer_payment"),
    path("webhooks/flutterwave/", flutterwave_webhook, name="flutterwave_webhook")]
urlpatterns += resource_urls(model=Connection, slug="connections", form_class=ConnectionForm, save=save_connection,
    columns=["Connection", "Provider", "Type", "URL", "Credential environment variable", "Active"], fields=["name", "code", "kind", "base_url", "credential_env", "is_active"], search_fields=["name", "code"],
    actions={"sync": Action("Queue accounting document", "integrations.add_integrationjob", lambda obj: DocumentForm, queue_document)})
urlpatterns += resource_urls(model=IntegrationJob, slug="jobs", columns=["Job", "Connection", "Operation", "Status", "Attempts", "Next attempt", "Error code", "Remote reference"],
    fields=["reference", "connection", "operation", "get_status_display", "attempts", "next_attempt_at", "error_code", "remote_reference"], search_fields=["event_key", "connection__name", "error_code"], select=["connection"],
    actions={"retry": Action("Retry failed delivery", "integrations.change_integrationjob", lambda obj: EmptyActionForm, retry_job)})
urlpatterns += resource_urls(model=GatewayIntent, slug="intents", columns=["Payment request", "Invoice", "Provider", "Amount", "Currency", "Status", "Provider reference", "Error code"],
    fields=["reference", "invoice", "connection", "amount", "currency", "get_status_display", "provider_transaction", "error_code"], search_fields=["invoice__number", "provider_transaction", "error_code"], select=["invoice", "connection"],
    actions={"recheck": Action("Recheck provider payment (Admin)", "integrations.change_gatewayintent", lambda obj: EmptyActionForm, recheck_intent)})
