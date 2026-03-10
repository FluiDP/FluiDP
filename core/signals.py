from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import CustomUser
from . import services
from django_q.tasks import async_task

@receiver(post_save, sender=CustomUser)
def send_new_collaborators_email(sender, instance, created, **kwargs):
    if created and instance.is_active:
        def send():
            try:
                async_task('core.services.enviar_email_boas_vindas_task', instance.id)
            except Exception as e:
                print(f"Erro ao colocar o e-mail na fila: {e}")

        transaction.on_commit(send)
