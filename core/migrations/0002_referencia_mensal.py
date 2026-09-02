from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def configurar_troca_plantao(apps, schema_editor):
    TipoDocumento = apps.get_model('core', 'TipoDocumento')
    for documento in TipoDocumento.objects.filter(nome_documento__iexact='Troca de Plantão'):
        schema = documento.definicao_formulario or []
        for campo in schema:
            if campo.get('name') in {'data_plantao_origem', 'data_plantao_destino'}:
                campo['is_event_date'] = True
                campo['reference_month_date'] = True
        documento.tipo_referencia = 'MENSAL'
        documento.dia_abertura_mes_anterior = 25
        documento.dia_limite_mes_referencia = 10
        documento.limite_dias_antecedencia = 2
        documento.restringir_datas_ao_mes_referencia = True
        documento.definicao_formulario = schema
        documento.save(update_fields=[
            'tipo_referencia', 'dia_abertura_mes_anterior',
            'dia_limite_mes_referencia', 'limite_dias_antecedencia',
            'restringir_datas_ao_mes_referencia', 'definicao_formulario',
        ])


def reverter_configuracao_troca_plantao(apps, schema_editor):
    TipoDocumento = apps.get_model('core', 'TipoDocumento')
    TipoDocumento.objects.filter(nome_documento__iexact='Troca de Plantão').update(
        tipo_referencia='NENHUMA', dia_abertura_mes_anterior=None,
        dia_limite_mes_referencia=None, restringir_datas_ao_mes_referencia=False,
    )


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='tipodocumento',
            name='tipo_referencia',
            field=models.CharField(
                choices=[('NENHUMA', 'Sem referência mensal'), ('MENSAL', 'Referência mensal')],
                default='NENHUMA', max_length=20, verbose_name='Tipo de referência',
                help_text='Use referência mensal para documentos cuja janela começa no mês anterior.',
            ),
        ),
        migrations.AddField(
            model_name='tipodocumento',
            name='dia_abertura_mes_anterior',
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(31)],
                verbose_name='Dia de abertura no mês anterior',
                help_text='Ex.: 25 abre solicitações para o mês seguinte.',
            ),
        ),
        migrations.AddField(
            model_name='tipodocumento',
            name='dia_limite_mes_referencia',
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(31)],
                verbose_name='Dia limite no mês de referência',
                help_text='Último dia para solicitar no próprio mês de referência.',
            ),
        ),
        migrations.AddField(
            model_name='tipodocumento',
            name='restringir_datas_ao_mes_referencia',
            field=models.BooleanField(
                default=False, verbose_name='Restringir datas ao mês de referência',
                help_text='Exige que os campos marcados no schema pertençam ao mês de referência.',
            ),
        ),
        migrations.AddField(
            model_name='solicitacao',
            name='mes_referencia',
            field=models.DateField(
                blank=True, null=True, verbose_name='Mês de referência',
                help_text='Armazenado como o primeiro dia do mês para preservar o histórico da regra aplicada.',
            ),
        ),
        migrations.RunPython(configurar_troca_plantao, reverter_configuracao_troca_plantao),
    ]
