from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0003_notificacao')]

    operations = [
        migrations.AddField(
            model_name='notificacao',
            name='excluida_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
