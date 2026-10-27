"""Linux WSGI service: terminate HTTPS at a trusted local reverse proxy."""
bind = "127.0.0.1:8000"
workers = 2
timeout = 60
accesslog = "-"
errorlog = "-"
capture_output = True
