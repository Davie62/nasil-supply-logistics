# NASIL Supply & Logistics Management System
## System Architecture

Version: 1.0
Prepared by:
David Francis Ssebunya


---

# Overview

The NASIL Supply & Logistics Management System is a secure, scalable web application built with Django. It supports customer management, quotation processing, shipment coordination, staff administration, and future logistics services.

The architecture is modular to allow new features to be enabled as the business grows.

---

# Architectural Principles

The system is designed around the following principles:

- Modularity
- Security by Design
- Scalability
- Maintainability
- Separation of Concerns
- Reusability

---

# High-Level Architecture

                    Users
                      │
                      ▼
              HTTPS / TLS
                      │
                      ▼
                   NGINX
                      │
                      ▼
                 Gunicorn
                      │
                      ▼
              Django Application
                      │
      ┌───────────────┼────────────────┐
      ▼               ▼                ▼
 Authentication   Business Logic   Admin Panel
      │               │                │
      └───────────────┼────────────────┘
                      ▼
                 Django ORM
                      │
                      ▼
                PostgreSQL
                      │
                      ▼
             Backup & Recovery

---

# Application Layers

Presentation Layer

- HTML Templates
- Bootstrap
- CSS
- JavaScript

Application Layer

- Django Views
- Forms
- Authentication
- Permissions

Business Layer

- Quote Processing
- Shipment Management
- Customer Management

Data Layer

- Django ORM
- SQLite (Development)
- PostgreSQL (Production)

Infrastructure Layer

- Docker
- Redis
- Celery
- NGINX
- Kubernetes (Future)

---

# Project Structure

backend/

System configuration.

logistics/

Business logic.

templates/

HTML templates.

static/

CSS, JavaScript, images and fonts.

media/

User uploads.

---

# Core Modules

Customer Management

Stores customer information.

Quote Management

Handles quotation requests.

Shipment Management

Tracks shipment progress.

Contact Management

Stores customer enquiries.

Authentication

Staff login and permissions.

Administration

System configuration and management.

Reports

Business analytics.

Notifications

Email and SMS (future).

Payments

Future integration.

---

# Feature Availability

Available at Launch

- Customer Management
- Quote Requests
- Contact Messages
- Dashboard
- Authentication

Future Modules

- Shipment Tracking
- Customer Portal
- Online Payments
- Procurement Management
- Inventory
- Notifications

---

# Database Relationships

Customer
    │
    ├──────────────┐
    ▼              ▼
 Quote       ContactMessage
    │
    ▼
Shipment

Carrier

Used for logistics partners.

Service

Defines available company services.

---

# Technology Stack

Backend

Python

Django

Frontend

HTML

Bootstrap

CSS

JavaScript

Database

SQLite (Development)

PostgreSQL (Production)

Caching

Redis (Future)

Background Tasks

Celery (Future)

Containerisation

Docker (Future)

Monitoring

Prometheus

Grafana

---

# Security Architecture

Authentication

Django Authentication Framework

Authorisation

Role-Based Access Control

Data Protection

HTTPS

CSRF Protection

Input Validation

Django Forms

ORM Protection

SQL Injection Prevention

Logging

Audit Logging

---

# Scalability Strategy

Database indexing

Caching

Background processing

Load balancing

Horizontal scaling

Monitoring

---

# Development Lifecycle

Requirements

↓

Architecture

↓

Database Design

↓

Security Review

↓

Implementation

↓

Testing

↓

Deployment

↓

Maintenance

---

# Future Expansion

REST API

Mobile Application

Supplier Portal

Customer Portal

AI Route Optimisation

Real-Time Tracking

Business Intelligence Dashboard

Warehouse Management

Electronic Proof of Delivery

---

# Version History

Version 1.0

Initial architecture.