from django.shortcuts import render, redirect
from django.contrib import messages
from core.models import ContactMessage
from customers.models import Customer
from quotations.models import Quote

from django.contrib.auth.decorators import login_required


def home(request):
    return render(request, "home.html")


def about(request):
    return render(request, "about.html")


def services(request):
    return render(request, "services.html")


def quote(request):
    if request.method == "POST":
        # Extract Customer Info
        full_name = request.POST.get("full_name")
        company_name = request.POST.get("company_name", "")
        phone = request.POST.get("phone")
        email = request.POST.get("email")

        # Extract Shipment Info
        pickup_location = request.POST.get("pickup_location")
        destination = request.POST.get("destination")
        cargo_description = request.POST.get("cargo_description")
        weight = request.POST.get("weight")
        transport_mode = request.POST.get("transport_mode", "")
        special_instructions = request.POST.get("special_instructions", "")

        if full_name and email and pickup_location and destination and weight:
            # Get or create customer by email
            customer, created = Customer.objects.get_or_create(
                email=email,
                defaults={
                    'full_name': full_name,
                    'company_name': company_name,
                    'phone': phone,
                }
            )
            # If exists but new info provided, you could optionally update here.

            # Create Quote
            new_quote = Quote.objects.create(
                customer=customer,
                pickup_location=pickup_location,
                destination=destination,
                transport_mode=transport_mode,
                cargo_description=cargo_description,
                weight=weight,
                special_instructions=special_instructions
            )
            
            messages.success(request, f"Quote request (Ref: {new_quote.quote_number}) submitted successfully. We will get back to you shortly.")
            return redirect("quote")
        else:
            messages.error(request, "Please fill in all required fields.")

    return render(request, "quote.html")


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone", "")
        subject = request.POST.get("subject")
        message = request.POST.get("message")
        
        if name and email and subject and message:
            ContactMessage.objects.create(
                name=name,
                email=email,
                phone=phone,
                subject=subject,
                message=message
            )
            messages.success(request, "Thank you for reaching out! Your message has been sent successfully.")
            return redirect("contact")
        else:
            messages.error(request, "Please fill in all required fields.")
            
    return render(request, "contact.html")


def faq(request):
    return render(request, "faq.html")