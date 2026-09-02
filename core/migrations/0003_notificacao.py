from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0002_referencia_mensal'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notificacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo', models.CharField(choices=[
                    ('SOLICITACAO_ABERTA', 'Solicitação aberta'),
                    ('PENDENCIA_SECUNDARIO', 'Pendente de aceite'),
                    ('RESUMO_SEMANAL', 'Resumo semanal'),
                    ('APROVADA_DP', 'Aprovada pelo DP'),
                    ('RECUSADA', 'Solicitação recusada'),
                    ('COMENTARIO', 'Comentário adicionado'),
                    ('CANCELADA_SISTEMA', 'Cancelada pelo sistema'),
                ], max_length=30)),
                ('titulo', models.CharField(max_length=150)),
                ('mensagem', models.TextField()),
                ('criada_em', models.DateTimeField(auto_now_add=True)),
                ('visualizada_em', models.DateTimeField(blank=True, null=True)),
                ('chave', models.CharField(blank=True, max_length=180, null=True, unique=True)),
                ('destinatario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notificacoes', to=settings.AUTH_USER_MODEL,
                )),
                ('solicitacao', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name='notificacoes', to='core.solicitacao',
                )),
            ],
            options={
                'verbose_name': 'Notificação',
                'verbose_name_plural': 'Notificações',
                'ordering': ['-criada_em'],
                'indexes': [models.Index(
                    fields=['destinatario', 'visualizada_em', '-criada_em'],
                    name='core_notifi_destina_c7f949_idx',
                )],
            },
        ),
    ]
