# NASIL Supply & Logistics Management System
## Security Architecture & Development Standards

Version: 1.0

Prepared By:
David Francis Ssebunya

---

# Purpose

This document defines the security architecture, coding standards, authentication strategy, scalability plan, and secure software development practices for the NASIL Supply & Logistics Management System.

Security is considered a core system requirement and is incorporated throughout the software development lifecycle rather than being implemented as an afterthought.

---

# Security Objectives

The system shall ensure:

- Confidentiality of customer and business data.
- Integrity of logistics records.
- Availability of services.
- Accountability through audit logging.
- Compliance with modern secure software development practices.

---

# Security Principles

The system follows the principle of Defence in Depth.

Security is enforced across multiple layers:

- Client
- Network
- Web Server
- Django Application
- Database
- Infrastructure

Every request must pass through multiple security controls before reaching protected resources.

---

# Authentication

The application uses Django's authentication framework.

Passwords are never stored in plain text.

Authentication features include:

- Secure password hashing
- Login sessions
- Logout
- Session timeout
- Password reset
- Account lockout after repeated failed login attempts (future enhancement)
- Multi-Factor Authentication (future enhancement)

---

# Authorisation

The system uses Role-Based Access Control (RBAC).

User roles include:

- Super Administrator
- Administrator
- Operations Officer
- Dispatcher
- Procurement Officer
- Finance Officer
- Customer (Future)
- Auditor (Future)

Permissions are assigned through Django Groups and Permissions.

Users may only access resources required for their role.

---

# Password Policy

Passwords must:

- Meet minimum length requirements.
- Contain uppercase characters.
- Contain lowercase characters.
- Include numbers.
- Include special characters.

Passwords shall be securely hashed using Django's built-in password hashing algorithms.

---

# Session Security

Production deployment shall enforce:

SESSION_COOKIE_SECURE = True

SESSION_COOKIE_HTTPONLY = True

SESSION_COOKIE_SAMESITE = Lax

CSRF_COOKIE_SECURE = True

Sessions expire after periods of inactivity.

---

# HTTPS

All production traffic must use HTTPS.

TLS certificates shall be provided through:

- Let's Encrypt
or
- Commercial SSL Provider

HTTP traffic shall redirect automatically to HTTPS.

---

# Input Validation

All incoming data must be validated.

Validation shall occur at:

- Forms
- Models
- APIs

Invalid data shall never reach the database.

---

# SQL Injection Protection

The application exclusively uses Django ORM.

Raw SQL shall only be used where absolutely necessary.

Parameterized queries shall always be used.

---

# Cross Site Scripting (XSS)

Django template auto-escaping shall remain enabled.

Unsafe HTML rendering shall be avoided.

The |safe template filter shall only be used for trusted content.

---

# Cross Site Request Forgery (CSRF)

Every HTML form must include:

{% csrf_token %}

CSRF Middleware shall remain enabled.

---

# Secure Configuration

Secrets shall never be committed to Git.

Sensitive values shall be loaded from environment variables.

Examples include:

- SECRET_KEY
- Database Password
- Email Credentials
- API Keys

---

# Audit Logging

The system shall maintain immutable audit logs for:

- User Login
- User Logout
- Quote Creation
- Quote Approval
- Shipment Updates
- User Creation
- User Deletion
- Password Changes
- Permission Changes

Each log shall include:

- User
- Timestamp
- IP Address
- Action
- Additional Details

---

# Error Handling

The system shall:

- Log server errors.
- Display user-friendly error pages.
- Avoid exposing stack traces in production.

---

# Logging

Application logs include:

- Authentication Events
- System Errors
- Quote Events
- Shipment Events
- Security Events

Future integration:

- Sentry
- Prometheus
- Grafana

---

# Data Protection

Sensitive customer information shall be protected.

Encryption shall be used where appropriate.

Backups shall be encrypted before off-site storage.

---

# Database Security

Development Database:

SQLite

Production Database:

PostgreSQL

Database users shall follow least privilege principles.

Indexes shall be created on high-frequency lookup fields.

---

# API Security

Future APIs shall implement:

- Authentication
- Authorisation
- Rate Limiting
- Request Validation
- Response Validation

Django REST Framework throttling shall be used.

---

# Rate Limiting

Future API limits include:

Anonymous Users

60 requests/hour

Authenticated Users

1000 requests/hour

Additional protection shall be applied for authentication endpoints.

---

# Background Processing

Long-running tasks shall execute asynchronously using:

- Celery
- Redis

Examples include:

- Email Notifications
- PDF Generation
- Bulk Processing

---

# Scalability

The application shall support:

- Redis Caching
- Horizontal Scaling
- Docker Containers
- Kubernetes Deployment
- Load Balancers

---

# Monitoring

Production monitoring includes:

- CPU Usage
- Memory Usage
- Database Performance
- Failed Logins
- Error Rates
- Response Times

Future tools:

- Prometheus
- Grafana

---

# Backup Strategy

Daily database backups.

Weekly full backups.

Encrypted backup storage.

Regular recovery testing.

---

# Dependency Management

Dependencies shall be updated regularly.

Security scanning tools include:

- pip-audit
- Safety

Known vulnerabilities shall be patched promptly.

---

# Coding Standards

Developers shall:

- Follow PEP 8.
- Use Django Best Practices.
- Document code.
- Write reusable modules.
- Avoid duplicated logic.
- Follow secure coding principles.

---

# Security Testing

The system shall undergo:

- Authentication Testing
- Authorisation Testing
- Input Validation Testing
- Session Testing
- Penetration Testing
- Load Testing

---

# Development Workflow

Every feature follows:

1. Requirements Analysis
2. Database Design
3. Security Review
4. Implementation
5. Testing
6. Code Review
7. Deployment

Security reviews are mandatory before deployment.

---

# Version History

Version 1.0

Initial security architecture document.