# Nasil Supply and Logistics

A secure web-based logistics management system built with **Python (Django)**, **PostgreSQL**, **Bootstrap 5**, and **JavaScript**.

## Features

* Customer registration and login
* Shipment tracking
* Quote request management
* Secure online payments
* Admin dashboard
* Role-based access control (RBAC)
* Multi-factor authentication (MFA)
* Audit logging
* REST API support

## Technology Stack

### Frontend

* HTML5
* CSS3
* Bootstrap 5
* JavaScript

### Backend

* Python 3
* Django
* Django REST Framework

### Database

* PostgreSQL

### Security

* HTTPS / TLS
* CSRF protection
* XSS protection
* SQL injection prevention
* Argon2 password hashing
* Secure cookies
* Rate limiting
* AES-256 encryption (where applicable)

## Project Structure

* `backend/` – Django project configuration
* `accounts/` – Authentication and user management
* `shipments/` – Shipment operations
* `tracking/` – Shipment tracking
* `quotations/` – Quote requests
* `payments/` – Payment processing
* `dashboard/` – Admin and customer dashboards
* `logistics/` – Core logistics operations
* `audit_logs/` – Security and activity logging

## Local Setup

```bash
# Create virtual environment
python -m venv venv

# Activate environment (Git Bash)
source venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py migrate

# Run the development server
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

## Author

**Ssebunya David**

Computer Science / IT Student • Rugby Athlete • Aspiring Software Developer/Network Engineer/Data science & ML
