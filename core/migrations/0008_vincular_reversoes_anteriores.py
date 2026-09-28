from django.db import migrations


ACOES_DECISAO = {
    'ACEITE_SECUNDARIO', 'RECUSA_SECUNDARIO',
    'APROVADO_GESTOR', 'RECUSADO_GESTOR',
    'APROVADO_DIRETOR', 'RECUSADO_DIRETOR',
    'APROVADO_DP', 'RECUSADO_DP', 'LANCADO',
}


def vincular_reversoes(apps, schema_editor):
    Log = apps.get_model('core', 'LogAprovacao')
    logs = Log.objects.using(schema_editor.connection.alias)
    rotulos = dict(Log._meta.get_field('acao').choices)
    for reversao in logs.filter(acao='REVERSAO', decisao_anulada__isnull=True).iterator():
        # O serviço antigo escolhia a última decisão bruta, não uma pilha
        # de decisões válidas. Reproduzir isso evita inferir outra decisão.
        anteriores = logs.filter(
            solicitacao_id=reversao.solicitacao_id,
            acao__in=ACOES_DECISAO, data_acao__lte=reversao.data_acao,
        )
        decisao = anteriores.order_by('-data_acao', '-pk').first()
        if not decisao or decisao.data_acao == reversao.data_acao:
            continue
        if anteriores.filter(data_acao=decisao.data_acao).count() != 1:
            continue
        if logs.filter(decisao_anulada_id=decisao.pk).exists():
            continue
        prefixo = f"Status revertido. A decisão anterior ('{rotulos[decisao.acao]}') foi desfeita."
        if not reversao.detalhes.startswith(prefixo):
            continue
        logs.filter(pk=reversao.pk).update(decisao_anulada_id=decisao.pk)


class Migration(migrations.Migration):
    dependencies = [('core', '0007_logaprovacao_decisao_anulada')]
    operations = [migrations.RunPython(vincular_reversoes, migrations.RunPython.noop)]
