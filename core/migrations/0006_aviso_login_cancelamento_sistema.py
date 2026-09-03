from django.db import migrations, models
from django.utils import timezone


def marcar_notificacoes_anteriores(apps, schema_editor):
    Notificacao = apps.get_model('core', 'Notificacao')
    Notificacao.objects.filter(
        tipo__in=['RECUSADA', 'CANCELADA_SISTEMA'],
        aviso_login_exibido_em__isnull=True,
    ).update(aviso_login_exibido_em=timezone.now())


class Migration(migrations.Migration):
    dependencies = [('core', '0005_alter_logaprovacao_acao_alter_solicitacao_status')]

    operations = [
        migrations.AddField(
            model_name='notificacao',
            name='aviso_login_exibido_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='logaprovacao',
            name='acao',
            field=models.CharField(
                choices=[
                    ('CRIACAO', 'Criação da Solicitação'),
                    ('EDICAO', 'Edição da Solicitação'),
                    ('CANCELAMENTO', 'Cancelado pelo Solicitante'),
                    ('CANCELAMENTO_SISTEMA', 'Cancelado automaticamente pelo Sistema'),
                    ('ACEITE_SECUNDARIO', 'Aceite pelo Colega'),
                    ('RECUSA_SECUNDARIO', 'Recusado pelo Colega'),
                    ('APROVADO_GESTOR', 'Aprovado pelo Gestor'),
                    ('RECUSADO_GESTOR', 'Recusado pelo Gestor'),
                    ('APROVADO_DIRETOR', 'Aprovado pelo Diretor'),
                    ('RECUSADO_DIRETOR', 'Recusado pelo Diretor'),
                    ('APROVADO_DP', 'Documento recebido pelo DP (aguardando a aprovação final)'),
                    ('RECUSADO_DP', 'Recusado pelo DP'),
                    ('LANCADO', 'Aprovado pelo DP'),
                    ('COMENTARIO', 'Comentário Adicionado'),
                    ('REVERSAO', 'Reversão de Decisão'),
                ],
                max_length=50,
            ),
        ),
        migrations.RunPython(marcar_notificacoes_anteriores, migrations.RunPython.noop),
    ]
