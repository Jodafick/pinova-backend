import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pinova_backend.settings')

app = Celery('pinova')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(related_name='tasks')
