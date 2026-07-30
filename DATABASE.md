
Database Design

Version: 1.0

---

# Overview

The database is designed using a relational model to support procurement, logistics operations, quotation management, customer management and future system expansion.

Development Database

SQLite

Production Database

PostgreSQL

---

 Entity Relationship Overview

Customer
    │
    ├───────────────┐
    ▼               ▼
 Quote      ContactMessage
    │
    ▼
Shipment

Carrier

Service

---

# Customer

Purpose

Stores customer information.

Fields

- id
- full_name
- company_name
- email
- phone
- address
- city
- country
- created_at

Indexes

- email

---

# Service

Purpose

Stores company services displayed on the website and used in quotations.

Fields

- id
- name
- description
- icon
- is_active

Indexes

- name

---

# Carrier

Purpose

Stores third-party logistics partners used by NASIL.

Fields

- id
- name
- contact_person
- phone
- email
- is_active

Indexes

- name

---

# Quote

Purpose

Stores quotation requests submitted by customers.

Fields

- id
- quote_number
- customer
- service
- pickup_location
- destination
- transport_mode
- cargo_description
- weight
- cargo_value
- special_instructions
- status
- created_at

Relationships

Customer → One to Many

Service → One to Many

Indexes

- quote_number
- status
- created_at

---

# Shipment

Purpose

Represents approved quotations that become active shipments.

Fields

- id
- tracking_number
- quote
- carrier
- current_location
- estimated_delivery
- status
- created_at

Relationships

Quote → One to One

Carrier → One to Many

Indexes

- tracking_number
- status

---

# ContactMessage

Purpose

Stores enquiries submitted through the Contact page.

Fields

- id
- name
- email
- phone
- subject
- message
- is_read
- created_at

Indexes

- email
- created_at

---

# Future Tables

The following tables are planned but will remain disabled until required.

## Payment

Purpose

Online payment integration.

Status

Future

---

## Notification

Purpose

Email and SMS notifications.

Status

Future

---

## Customer Portal

Purpose

Customer self-service dashboard.

Status

Future

---

## AuditLog

Purpose

System audit logging.

Status

To be implemented after authentication.

---

# Relationships

Customer

1 → Many Quotes

Customer

1 → Many Contact Messages

Service

1 → Many Quotes

Quote

1 → 1 Shipment

Carrier

1 → Many Shipments

---

# Naming Standards

Primary Keys

id

Foreign Keys

<model_name>

Example

customer

quote

carrier

Table Names

Singular model names

Customer

Quote

Shipment

---

# Database Optimisation

The production database will use:

- Indexes on frequently queried fields
- Django ORM
- Query optimisation
- Database migrations
- Transaction management

Future enhancements include:

- Redis caching
- Read replicas
- Connection pooling

---

# Migration Strategy

All schema changes shall be managed using Django migrations.

Manual database modifications are not permitted.

---

# Version History

Version 1.0

Initial database design.

FINAL DATABASE DESIGN

NASIL Logistics Database

Authentication
│
├── CustomUser
├── Department
├── Role
├── AuditLog
└── ActivityLog

Business
│
├── Customer
├── Service
├── Carrier
├── Quote
├── Shipment
└── ContactMessage

System
│
├── Notification
├── Attachment
├── Payment
├── FeatureFlag
└── SystemSetting