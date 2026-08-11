bind = '0.0.0.0:8082'
workers = 4
worker_class = 'sync'
timeout = 300
daemon = 'false'
accesslog = 'logs/gunicorn_access.log'
errorlog = 'logs/gunicorn_error.log'
loglevel = 'info'
