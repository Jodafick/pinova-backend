from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from fotos.models import Foto

from .services import ensure_user_referral_code, on_first_foto_created, on_referee_first_login


@receiver(post_save, sender=User)
def referrals_ensure_code_on_user_created(sender, instance, created, **kwargs):
    if created:
        def _run():
            ensure_user_referral_code(instance)

        transaction.on_commit(_run)


@receiver(user_logged_in)
def referrals_first_login(sender, request, user, **kwargs):
    def _run():
        on_referee_first_login(user)

    transaction.on_commit(_run)


@receiver(post_save, sender=Foto)
def referrals_first_pin(sender, instance, created, **kwargs):
    if not created or not instance.author_id:
        return
    n = Foto.objects.filter(author_id=instance.author_id).count()
    if n == 1:
        on_first_foto_created(instance.author)
