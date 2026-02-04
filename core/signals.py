from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import CustomUser
from . import services

@receiver(post_save, sender=CustomUser)
def send_new_collaborators_email(sender, instance, created, **kwargs):
    """
    Sempre que um usuário é criado (created=True), agenda o envio do e-mail.
    """
    if created and instance.is_active:
        def send():
            try:
                services.new_collaborator_email(instance)
            except Exception as e:
                print(f"Erro ao enviar e-mail de boas-vindas para {instance.email}: {e}")

        transaction.on_commit(send)
