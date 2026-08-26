#!/usr/bin/env python
import os
import getpass
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from accounts.models import User

# Check if test user exists
try:
    user = User.objects.get(username='testuser')
    print(f"User 'testuser' already exists")
except User.DoesNotExist:
    password = os.environ.get('DJANGO_TESTUSER_PASSWORD') or getpass.getpass('Password for testuser: ')
    # Create test user
    user = User.objects.create_superuser(
        username='testuser',
        email='testuser@example.com',
        password=password
    )
    print("Created superuser 'testuser'.")
