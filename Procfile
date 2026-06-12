web: gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 1 --worker-class sync --timeout 300 --graceful-timeout 30 app:app
