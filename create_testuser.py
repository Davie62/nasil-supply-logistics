#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from accounts.models import User

# Check if test user exists
try:
    user = User.objects.get(username='testuser')
    print(f"User 'testuser' already exists")
except User.DoesNotExist:
    # Create test user
    user = User.objects.create_superuser(
        username='testuser',
        email='testuser@example.com',
        password='testpass123'
    )
    print(f"Created superuser 'testuser' with password 'testpass123'")
