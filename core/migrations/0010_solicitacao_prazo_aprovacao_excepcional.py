from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0009_senha_provisoria_definida_em')]

    operations = [
        migrations.AddField(
            model_name='solicitacao',
            name='prazo_aprovacao_excepcional',
            field=models.DateField(blank=True, editable=False, null=True),
        ),
    ]
