from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('core', '0010_solicitacao_prazo_aprovacao_excepcional')]

    operations = [
        migrations.AddField(
            model_name='logaprovacao',
            name='gestor_na_aprovacao',
            field=models.ForeignKey(
                blank=True, editable=False, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+', to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
