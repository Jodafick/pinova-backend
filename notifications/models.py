from django.db import models
from django.contrib.auth.models import User

class Notification(models.Model):
    TYPES = (
        ('like', 'Like'),
        ('save', 'Save'),
        ('follow', 'Follow'),
        ('comment', 'Comment'),
        ('welcome', 'Welcome'),
    )
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_notifications', null=True, blank=True)
    notification_type = models.CharField(max_length=20, choices=TYPES)
    message = models.CharField(max_length=255)
    pin_id = models.IntegerField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sender.username} {self.notification_type} for {self.recipient.username}"
