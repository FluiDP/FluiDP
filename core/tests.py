from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from .models import Cargo, CustomUser, Lotacao, Notificacao, Solicitacao, TipoDocumento
from .services import (
    criar_solicitacao,
    criar_resumo_semanal_usuario,
    deve_enviar_email_notificacao,
    editar_solicitacao,
    obter_status_relatorio,
    preparar_aviso_login,
)


class DatasTrocaTests(TestCase):
    def setUp(self):
        self.sebastiao = CustomUser.objects.create_user(username='sebastiao_troca', cpf='11122233396')
        self.ramom = CustomUser.objects.create_user(username='ramom_troca', cpf='52998224725')
        self.outro = CustomUser.objects.create_user(username='outro_troca', cpf='12345678909')
        self.schema = [
            {'name': name, 'type': 'date', 'label': name, 'required': True}
            for name in ('data_plantao_origem', 'data_plantao_destino')
        ] + [{'name': 'colaborador_substituto', 'type': 'select', 'label': 'Colega',
              'required': True, 'options_source': 'colaboradores_mesmo_cargo'}]
        self.tipo = TipoDocumento.objects.create(
            nome_documento='Troca de Plantão', definicao_formulario=self.schema,
        )

    def abrir(self, autor, colega, origem, destino):
        valores = {
            'data_plantao_origem': origem, 'data_plantao_destino': destino,
            'colaborador_substituto': str(colega.pk),
        }
        return criar_solicitacao(autor, self.tipo, {'schema': self.schema, 'values': valores}, self.schema)

    def test_bloqueia_reuso_do_destino_como_destino_ou_origem(self):
        primeira = self.abrir(self.sebastiao, self.ramom, '2026-11-09', '2026-11-12')
        with self.assertRaisesMessage(ValidationError, f'#{primeira.pk} para sebastiao_troca, ramom_troca'):
            self.abrir(self.sebastiao, self.ramom, '2026-11-11', '2026-11-12')
        with self.assertRaisesMessage(ValidationError, '12/11/2026'):
            self.abrir(self.sebastiao, self.ramom, '2026-11-12', '2026-11-14')

    def test_bloqueia_colega_e_edicao_mas_libera_terceiros_e_canceladas(self):
        primeira = self.abrir(self.sebastiao, self.ramom, '2026-11-09', '2026-11-12')
        with self.assertRaisesMessage(ValidationError, f'#{primeira.pk} para ramom_troca'):
            self.abrir(self.ramom, self.outro, '2026-11-12', '2026-11-14')
        outra = self.abrir(self.outro, self.sebastiao, '2026-11-15', '2026-11-16')
        with self.assertRaisesMessage(ValidationError, '12/11/2026'):
            editar_solicitacao(outra, self.outro, {'data_plantao_destino': '2026-11-12'})
        Solicitacao.objects.filter(pk=primeira.pk).update(status=Solicitacao.StatusChoices.CANCELADO)
        self.abrir(self.sebastiao, self.ramom, '2026-11-11', '2026-11-12')

    def test_troca_de_folga_tambem_ocupa_dia_de_plantao(self):
        tipo_folga = TipoDocumento.objects.create(nome_documento='Troca de Folga')
        Solicitacao.objects.create(
            colaborador=self.sebastiao, tipo_documento=tipo_folga,
            status=Solicitacao.StatusChoices.FINALIZADO,
            dados_preenchidos={'values': {
                'data_folga_origem': '2026-11-09', 'data_folga_destino': '2026-11-12',
            }},
        )
        with self.assertRaisesMessage(ValidationError, '12/11/2026'):
            self.abrir(self.sebastiao, self.ramom, '2026-11-12', '2026-11-14')


class ReferenciaMensalTipoDocumentoTests(SimpleTestCase):
    def setUp(self):
        self.tipo = TipoDocumento(
            nome_documento='Troca de Plantão',
            tipo_referencia=TipoDocumento.TipoReferenciaChoices.MENSAL,
            dia_abertura_mes_anterior=25,
            dia_limite_mes_referencia=10,
            limite_dias_antecedencia=2,
            restringir_datas_ao_mes_referencia=True,
            definicao_formulario=[
                {'name': 'origem', 'label': 'Origem', 'type': 'date', 'required': True,
                 'is_event_date': True, 'reference_month_date': True},
                {'name': 'destino', 'label': 'Destino', 'type': 'date', 'required': True,
                 'is_event_date': True, 'reference_month_date': True},
            ],
        )

    def test_calcula_referencia_nos_limites_da_janela(self):
        self.assertEqual(self.tipo.obter_mes_referencia(date(2026, 1, 25)), date(2026, 2, 1))
        self.assertEqual(self.tipo.obter_mes_referencia(date(2026, 2, 10)), date(2026, 2, 1))
        self.assertIsNone(self.tipo.obter_mes_referencia(date(2026, 2, 11)))
        self.assertIsNone(self.tipo.obter_mes_referencia(date(2026, 2, 24)))

    def test_calcula_referencia_na_virada_do_ano(self):
        self.assertEqual(self.tipo.obter_mes_referencia(date(2026, 12, 25)), date(2027, 1, 1))

    def test_aceita_duas_datas_no_mes_de_referencia(self):
        referencia = self.tipo.validar_regras(
            {'origem': '2026-02-05', 'destino': '2026-02-20'}, date(2026, 1, 25)
        )
        self.assertEqual(referencia, date(2026, 2, 1))

    def test_rejeita_data_do_mes_em_que_solicitacao_foi_aberta(self):
        with self.assertRaisesMessage(ValidationError, '02/2026'):
            self.tipo.validar_regras(
                {'origem': '2026-01-30', 'destino': '2026-02-20'}, date(2026, 1, 25)
            )

    def test_rejeita_qualquer_data_sem_dois_dias_de_antecedencia(self):
        with self.assertRaisesMessage(ValidationError, 'antecedência mínima de 2 dias'):
            self.tipo.validar_regras(
                {'origem': '2026-02-20', 'destino': '2026-02-10'}, date(2026, 2, 9)
            )

    def test_rejeita_solicitacao_fora_da_janela(self):
        with self.assertRaisesMessage(ValidationError, 'Dia 25 do mês anterior'):
            self.tipo.validar_regras(
                {'origem': '2026-02-20', 'destino': '2026-02-22'}, date(2026, 2, 11)
            )

    def test_prazo_existente_expira_apos_dia_limite_da_referencia(self):
        motivo = self.tipo.motivo_prazo_expirado(
            {'origem': '2026-02-20', 'destino': '2026-02-22'},
            date(2026, 1, 25),
            mes_referencia=date(2026, 2, 1),
            data_consulta=date(2026, 2, 11),
        )
        self.assertIn('02/2026', motivo)

    def test_prazo_existente_expira_quando_perde_antecedencia_minima(self):
        motivo = self.tipo.motivo_prazo_expirado(
            {'origem': '2026-02-11', 'destino': '2026-02-20'},
            date(2026, 1, 25),
            mes_referencia=date(2026, 2, 1),
            data_consulta=date(2026, 2, 10),
        )
        self.assertIn('antecedência mínima de 2 dias', motivo)

    def test_prazo_existente_permanece_valido(self):
        motivo = self.tipo.motivo_prazo_expirado(
            {'origem': '2026-02-12', 'destino': '2026-02-20'},
            date(2026, 1, 25),
            mes_referencia=date(2026, 2, 1),
            data_consulta=date(2026, 2, 9),
        )
        self.assertIsNone(motivo)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class AvisoLoginTests(TestCase):
    def test_exibe_apenas_solicitacoes_proprias_e_confirma_visualizacao(self):
        usuario = CustomUser.objects.create_user(
            username='usuario_teste', password='senha-segura', cpf='12345678909'
        )
        outro = CustomUser.objects.create_user(username='outro_aviso', cpf='11122233396')
        tipo_documento = TipoDocumento.objects.create(nome_documento='Documento aviso')
        solicitacoes = [Solicitacao.objects.create(colaborador=usuario, tipo_documento=tipo_documento)
                        for _ in range(3)]
        solicitacao_outro = Solicitacao.objects.create(
            colaborador=outro, colaborador_secundario=usuario, tipo_documento=tipo_documento,
        )
        solicitacao_aprovada_por_usuario = Solicitacao.objects.create(
            colaborador=outro, aprovador_atual=usuario, tipo_documento=tipo_documento,
        )
        notificacoes = []
        for solicitacao, tipo in zip(solicitacoes, [
            Notificacao.TipoChoices.COMENTARIO,
            Notificacao.TipoChoices.APROVADA_DP,
            Notificacao.TipoChoices.CANCELADA_SISTEMA,
        ]):
            notificacoes.append(Notificacao.objects.create(
                destinatario=usuario, solicitacao=solicitacao,
                tipo=tipo, titulo='Aviso', mensagem='Mensagem',
            ))
        Notificacao.objects.create(
            destinatario=usuario, solicitacao=solicitacao_outro,
            tipo=Notificacao.TipoChoices.COMENTARIO, titulo='Outro', mensagem='Mensagem',
        )
        Notificacao.objects.create(
            destinatario=usuario, solicitacao=solicitacao_aprovada_por_usuario,
            tipo=Notificacao.TipoChoices.COMENTARIO, titulo='Aprovador', mensagem='Mensagem',
        )
        Notificacao.objects.create(
            destinatario=usuario, solicitacao=solicitacoes[0],
            tipo=Notificacao.TipoChoices.SOLICITACAO_ABERTA,
            titulo='Abertura', mensagem='Mensagem',
        )

        requisicao = SimpleNamespace(session={})
        preparar_aviso_login(requisicao, usuario)
        ids = requisicao.session['aviso_solicitacoes_login']
        self.assertCountEqual(ids, [notificacao.pk for notificacao in notificacoes])
        self.assertEqual(Notificacao.objects.filter(pk__in=ids, visualizada_em__isnull=True).count(), 3)

        self.client.force_login(usuario)
        sessao = self.client.session
        sessao['aviso_solicitacoes_login'] = ids
        sessao.save()
        pagina = self.client.get(reverse('painel'), follow=True)
        self.assertEqual(len(pagina.context['aviso_solicitacoes_login']), 3)
        self.assertContains(pagina, 'max-w-2xl max-h-[90dvh]')
        for solicitacao in solicitacoes:
            self.assertContains(pagina, f'Solicitação #{solicitacao.pk}')
        resposta = self.client.post(reverse('confirmar_aviso_solicitacoes_login'))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn('aviso_solicitacoes_login', self.client.session)
        self.assertEqual(Notificacao.objects.filter(pk__in=ids, visualizada_em__isnull=False).count(), 3)
        self.assertEqual(Notificacao.objects.filter(pk__in=ids, aviso_login_exibido_em__isnull=False).count(), 3)

        nova_requisicao = SimpleNamespace(session={})
        preparar_aviso_login(nova_requisicao, usuario)
        self.assertNotIn('aviso_solicitacoes_login', nova_requisicao.session)


class RestricaoEmailDirecaoTests(TestCase):
    def setUp(self):
        cargo = Cargo.objects.create(
            nome_cargo='Diretor de teste', hierarquia=Cargo.HierarquiaChoices.DIRETOR
        )
        self.diretor = CustomUser.objects.create_user(
            username='diretor_teste', password='senha-segura', cpf='98765432100', cargo=cargo
        )

    def criar_notificacao(self, tipo):
        return Notificacao.objects.create(
            destinatario=self.diretor, tipo=tipo, titulo='Aviso', mensagem='Mensagem'
        )

    def test_direcao_nao_recebe_email_de_acoes_individuais(self):
        tipos_individuais = [
            Notificacao.TipoChoices.SOLICITACAO_ABERTA,
            Notificacao.TipoChoices.PENDENCIA_SECUNDARIO,
            Notificacao.TipoChoices.APROVADA_DP,
            Notificacao.TipoChoices.RECUSADA,
            Notificacao.TipoChoices.COMENTARIO,
            Notificacao.TipoChoices.CANCELADA_SISTEMA,
        ]
        for tipo in tipos_individuais:
            with self.subTest(tipo=tipo):
                self.assertFalse(deve_enviar_email_notificacao(self.criar_notificacao(tipo)))

    def test_direcao_recebe_email_do_resumo_semanal(self):
        notificacao = self.criar_notificacao(Notificacao.TipoChoices.RESUMO_SEMANAL)
        self.assertTrue(deve_enviar_email_notificacao(notificacao))

    @patch('core.services.obter_pendencias_do_usuario')
    def test_resumo_nao_e_criado_fora_da_segunda_feira(self, obter_pendencias):
        criado = criar_resumo_semanal_usuario(
            self.diretor, data_referencia=date(2026, 9, 3)
        )
        self.assertFalse(criado)
        obter_pendencias.assert_not_called()


class FiltroStatusRelatorioTests(SimpleTestCase):
    def test_padrao_exclui_canceladas_e_recusadas(self):
        status = obter_status_relatorio()
        self.assertNotIn('CANCELADO', status)
        self.assertNotIn('RECUSADO', status)
        self.assertIn('FINALIZADO', status)

    def test_usuario_pode_escolher_incluir_canceladas_e_recusadas(self):
        status = obter_status_relatorio(['CANCELADO', 'RECUSADO'], filtro_aplicado=True)
        self.assertEqual(status, ['CANCELADO', 'RECUSADO'])

    def test_status_invalido_e_ignorado(self):
        status = obter_status_relatorio(['FINALIZADO', 'INEXISTENTE'], filtro_aplicado=True)
        self.assertEqual(status, ['FINALIZADO'])


class RelatorioGeralStatusIntegrationTests(TestCase):
    def setUp(self):
        cargo_diretor = Cargo.objects.create(
            nome_cargo='Diretor relatório', hierarquia=Cargo.HierarquiaChoices.DIRETOR
        )
        self.diretor = CustomUser.objects.create_user(
            username='diretor_relatorio', password='senha-segura',
            cpf='11122233396', cargo=cargo_diretor,
        )
        self.lotacao = Lotacao.objects.create(nome_lotacao='Setor de teste')
        self.colaborador = CustomUser.objects.create_user(
            username='colaborador_relatorio', password='senha-segura',
            cpf='52998224725', lotacao=self.lotacao,
        )
        self.tipo = TipoDocumento.objects.create(
            nome_documento='Documento de teste', definicao_formulario=[]
        )
        for status in [
            Solicitacao.StatusChoices.FINALIZADO,
            Solicitacao.StatusChoices.RECUSADO,
            Solicitacao.StatusChoices.CANCELADO,
        ]:
            Solicitacao.objects.create(
                colaborador=self.colaborador,
                tipo_documento=self.tipo,
                status=status,
            )
        self.client = Client()
        self.client.force_login(self.diretor)

    def test_relatorio_aplica_padrao_e_selecao_explicita(self):
        resposta_padrao = self.client.get(reverse('relatorio_geral'))
        self.assertEqual(resposta_padrao.status_code, 200)
        self.assertEqual(resposta_padrao.context['ranking_data'][0]['total'], 1)
        self.assertContains(resposta_padrao, '<details class="relative">')
        self.assertContains(resposta_padrao, 'aria-label="Imprimir / Salvar PDF"')
        self.assertNotContains(resposta_padrao, '>\n            Imprimir\n')

        resposta_encerradas = self.client.get(reverse('relatorio_geral'), {
            'status_filter_applied': '1',
            'status': ['RECUSADO', 'CANCELADO'],
        })
        self.assertEqual(resposta_encerradas.status_code, 200)
        self.assertEqual(resposta_encerradas.context['ranking_data'][0]['total'], 2)

    def test_horas_extras_com_intervalo_e_formulario_antigo(self):
        tipo_horas = TipoDocumento.objects.create(
            nome_documento='Pagamento de Hora Extra em Folha', definicao_formulario=[]
        )
        Solicitacao.objects.create(
            colaborador=self.colaborador, tipo_documento=tipo_horas,
            status=Solicitacao.StatusChoices.FINALIZADO,
            dados_preenchidos={
                'schema': [{'name': 'cronograma_he', 'type': 'repeater', 'sub_fields': [
                    {'name': name} for name in (
                        'hora_inicio', 'inicio_intervalo', 'fim_intervalo', 'hora_fim'
                    )
                ]}],
                'values': {'cronograma_he': [
                    {'data_programada': '2025-12-31', 'hora_inicio': '08:00', 'inicio_intervalo': '12:00',
                     'fim_intervalo': '13:00', 'hora_fim': '17:00'},
                    {'data_programada': '2025-12-31', 'hora_inicio': '22:00', 'inicio_intervalo': '23:30',
                     'fim_intervalo': '00:00', 'hora_fim': '02:00'},
                ]},
            },
        )
        Solicitacao.objects.create(
            colaborador=self.colaborador, tipo_documento=tipo_horas,
            status=Solicitacao.StatusChoices.FINALIZADO,
            dados_preenchidos={
                'schema': [{'name': 'total_geral_horas', 'type': 'calculated',
                            'calc_format': 'time', 'label': 'Total de Horas Extras'}],
                'values': {'total_geral_horas': '02:00'},
            },
        )

        resposta = self.client.get(reverse('relatorio_geral'))
        self.assertEqual(resposta.context['horas_extras'], '13:30')


class SchedulerNaoCancelaPorPrazoTests(TestCase):
    def test_solicitacao_em_andamento_permanece_ativa_apos_fim_do_periodo(self):
        cargo_gestor = Cargo.objects.create(
            nome_cargo='Gestor scheduler', hierarquia=Cargo.HierarquiaChoices.COORDENADOR
        )
        cargo_colaborador = Cargo.objects.create(
            nome_cargo='Colaborador scheduler', hierarquia=Cargo.HierarquiaChoices.PADRAO
        )
        gestor = CustomUser.objects.create_user(
            username='gestor_scheduler', cpf='11144477735', cargo=cargo_gestor,
        )
        lotacao = Lotacao.objects.create(nome_lotacao='Setor scheduler', chefia=gestor)
        colaborador = CustomUser.objects.create_user(
            username='colaborador_scheduler', cpf='12345678909',
            cargo=cargo_colaborador, lotacao=lotacao,
        )
        tipo = TipoDocumento.objects.create(
            nome_documento='Documento mensal encerrado', dia_inicio=1, dia_fim=31,
            definicao_formulario=[],
        )
        solicitacao = Solicitacao.objects.create(
            colaborador=colaborador, tipo_documento=tipo,
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
            aprovador_atual=gestor,
        )
        Solicitacao.objects.filter(pk=solicitacao.pk).update(
            data=timezone.now() - timedelta(days=60)
        )
        TipoDocumento.objects.filter(pk=tipo.pk).update(dia_fim=1)

        with patch(
            'core.management.commands.request_scheduler.timezone.localdate',
            return_value=date(2026, 9, 1),
        ):
            call_command('request_scheduler')

        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.status, Solicitacao.StatusChoices.PENDENTE_GESTOR)
        self.assertEqual(solicitacao.aprovador_atual, gestor)
        self.assertFalse(solicitacao.logs.filter(acao='CANCELAMENTO_SISTEMA').exists())


class DecisoesValidasTests(TestCase):
    def setUp(self):
        from .models import LogAprovacao
        self.Log = LogAprovacao
        self.lotacao = Lotacao.objects.create(nome_lotacao='Setor reversões')
        self.autor = CustomUser.objects.create_user(
            username='autor_reversao', cpf='52998224725', lotacao=self.lotacao,
        )
        self.gestor = CustomUser.objects.create_user(
            username='gestor_reversao', cpf='11122233396',
        )
        cargo = Cargo.objects.create(nome_cargo='Diretor reversões', hierarquia=Cargo.HierarquiaChoices.DIRETOR)
        self.diretor = CustomUser.objects.create_user(
            username='diretor_reversao', cpf='12345678909', cargo=cargo,
        )
        tipo = TipoDocumento.objects.create(nome_documento='Teste reversões', definicao_formulario=[])
        self.solicitacao = Solicitacao.objects.create(
            colaborador=self.autor, tipo_documento=tipo,
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
            dados_preenchidos={'schema': [], 'values': {}},
        )
        self.log('CRIACAO', self.autor)

    def log(self, acao, ator):
        return self.Log.objects.create(solicitacao=self.solicitacao, ator=ator, acao=acao)

    def reverter(self, ator):
        from .services import reverter_status_solicitacao
        with patch.object(Lotacao, 'find_gestor_disponivel', return_value=self.gestor):
            reverter_status_solicitacao(self.solicitacao, ator)
        self.solicitacao.refresh_from_db()

    def test_gestor_aprova_reverte_e_autor_edita(self):
        from .services import editar_solicitacao
        self.assertTrue(self.solicitacao.can_edit(self.autor))
        decisao = self.log('APROVADO_GESTOR', self.gestor)
        self.solicitacao.status = Solicitacao.StatusChoices.PENDENTE_DP
        self.solicitacao.save()
        self.assertFalse(self.solicitacao.can_edit(self.autor))
        self.reverter(self.gestor)
        self.assertEqual(self.solicitacao.logs.get(acao='REVERSAO').decisao_anulada_id, decisao.pk)
        self.assertTrue(self.solicitacao.can_edit(self.autor))
        editar_solicitacao(self.solicitacao, self.autor, {'motivo': 'Corrigido'})
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.dados_preenchidos['values']['motivo'], 'Corrigido')
        self.assertTrue(self.solicitacao.can_edit(self.autor))
        self.assertFalse(self.solicitacao.can_edit(self.gestor))
        self.assertTrue(self.solicitacao.logs.filter(pk=decisao.pk).exists())
        self.assertFalse(self.solicitacao.can_reverse_status(self.gestor))

    def test_diretor_reverte_e_depois_gestor_reverte(self):
        gestor = self.log('APROVADO_GESTOR', self.gestor)
        diretor = self.log('APROVADO_DIRETOR', self.diretor)
        self.solicitacao.status = Solicitacao.StatusChoices.PENDENTE_DP
        self.solicitacao.save()
        self.assertFalse(self.solicitacao.can_reverse_status(self.gestor))
        self.reverter(self.diretor)
        self.assertEqual(self.solicitacao.decisoes_validas().get().pk, gestor.pk)
        self.assertTrue(self.solicitacao.can_reverse_status(self.gestor))
        self.assertFalse(self.solicitacao.can_edit(self.autor))
        self.reverter(self.gestor)
        self.assertFalse(self.solicitacao.decisoes_validas().exists())
        self.assertTrue(self.solicitacao.can_edit(self.autor))
        self.assertEqual(set(self.solicitacao.logs.filter(acao='REVERSAO').values_list('decisao_anulada_id', flat=True)), {gestor.pk, diretor.pk})

    def test_aceite_do_colega_continua_bloqueando_edicao(self):
        aceite = self.log('ACEITE_SECUNDARIO', self.diretor)
        self.log('APROVADO_GESTOR', self.gestor)
        self.reverter(self.gestor)
        self.assertEqual(self.solicitacao.decisoes_validas().get().pk, aceite.pk)
        self.assertFalse(self.solicitacao.can_edit(self.autor))

    def test_nova_aprovacao_volta_a_bloquear_edicao(self):
        self.log('APROVADO_GESTOR', self.gestor)
        self.reverter(self.gestor)
        nova = self.log('APROVADO_GESTOR', self.gestor)
        self.assertEqual(self.solicitacao.decisoes_validas().get().pk, nova.pk)
        self.assertFalse(self.solicitacao.can_edit(self.autor))
        self.assertFalse(self.solicitacao.can_reverse_status(self.gestor))

    def test_prazo_da_decisao_do_gestor_continua_valendo(self):
        gestor = self.log('APROVADO_GESTOR', self.gestor)
        self.Log.objects.filter(pk=gestor.pk).update(data_acao=timezone.now() - timedelta(hours=25))
        self.log('APROVADO_DIRETOR', self.diretor)
        self.reverter(self.diretor)
        self.assertFalse(self.solicitacao.can_reverse_status(self.gestor))

    def test_estados_encerrados_nao_permitem_edicao(self):
        for status in ['FINALIZADO', 'CANCELADO', 'RECUSADO']:
            with self.subTest(status=status):
                self.solicitacao.status = status
                self.assertFalse(self.solicitacao.can_edit(self.autor))

    def migrar_logs(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        migration = import_module('core.migrations.0008_vincular_reversoes_anteriores')
        migration.vincular_reversoes(apps, SimpleNamespace(connection=connection))

    def test_migracao_vincula_reversao_antiga(self):
        decisao = self.log('APROVADO_GESTOR', self.gestor)
        reversao = self.log('REVERSAO', self.gestor)
        reversao.detalhes = f"Status revertido. A decisão anterior ('{decisao.get_acao_display()}') foi desfeita. Justificativa: erro"
        reversao.save()
        self.migrar_logs()
        reversao.refresh_from_db()
        self.assertEqual(reversao.decisao_anulada_id, decisao.pk)
        self.assertTrue(self.solicitacao.can_edit(self.autor))

    def test_migracao_nao_inventa_vinculo_para_reversao_ambigua(self):
        self.log('APROVADO_GESTOR', self.gestor)
        reversao = self.log('REVERSAO', self.gestor)
        self.migrar_logs()
        reversao.refresh_from_db()
        self.assertIsNone(reversao.decisao_anulada_id)
        self.assertFalse(self.solicitacao.can_edit(self.autor))
        self.assertFalse(self.solicitacao.can_reverse_status(self.diretor))


    def test_encadeamento_completo_ate_aceite_do_colega(self):
        from django.contrib.auth.models import Group
        dp_group = Group.objects.create(name='DP')
        dp = CustomUser.objects.create_user(username='dp_reversao', cpf='00000000001')
        dp_final = CustomUser.objects.create_user(username='dp_final_reversao', cpf='00000000002')
        colega = CustomUser.objects.create_user(username='colega_reversao', cpf='00000000003')
        dp.groups.add(dp_group)
        dp_final.groups.add(dp_group)
        etapas = [
            ('ACEITE_SECUNDARIO', colega),
            ('APROVADO_GESTOR', self.gestor),
            ('APROVADO_DIRETOR', self.diretor),
            ('APROVADO_DP', dp),
            ('LANCADO', dp_final),
        ]
        decisoes = [self.log(acao, ator) for acao, ator in etapas]
        self.solicitacao.status = Solicitacao.StatusChoices.FINALIZADO
        self.solicitacao.save()
        for indice in range(len(etapas) - 1, -1, -1):
            with self.subTest(acao=etapas[indice][0]):
                self.assertEqual(self.solicitacao.decisoes_validas().first(), decisoes[indice])
                self.assertTrue(self.solicitacao.can_reverse_status(etapas[indice][1]))
                self.reverter(etapas[indice][1])
                self.assertEqual(self.solicitacao.can_edit(self.autor), indice == 0)
        self.assertEqual(self.solicitacao.status, Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO)

    def test_recusas_tambem_sao_decisoes_anulaveis(self):
        from django.contrib.auth.models import Group
        dp = CustomUser.objects.create_user(username='dp_recusa', cpf='00000000004')
        dp.groups.add(Group.objects.create(name='DP'))
        for acao, ator in [
            ('RECUSA_SECUNDARIO', self.autor),
            ('RECUSADO_GESTOR', self.gestor),
            ('RECUSADO_DIRETOR', self.diretor),
            ('RECUSADO_DP', dp),
        ]:
            with self.subTest(acao=acao):
                self.solicitacao = Solicitacao.objects.create(
                    colaborador=self.autor, tipo_documento=self.solicitacao.tipo_documento,
                    status=Solicitacao.StatusChoices.RECUSADO,
                )
                decisao = self.log(acao, ator)
                self.assertFalse(self.solicitacao.can_edit(self.autor))
                self.reverter(ator)
                self.assertEqual(self.solicitacao.logs.get(acao='REVERSAO').decisao_anulada_id, decisao.pk)
                self.assertTrue(self.solicitacao.can_edit(self.autor))

    def test_migracao_nao_interpreta_reversao_repetida_como_outra_decisao(self):
        self.log('APROVADO_GESTOR', self.gestor)
        diretor = self.log('APROVADO_DIRETOR', self.diretor)
        for _ in range(2):
            reversao = self.log('REVERSAO', self.diretor)
            reversao.detalhes = f"Status revertido. A decisão anterior ('{diretor.get_acao_display()}') foi desfeita."
            reversao.save()
        self.migrar_logs()
        self.assertEqual(self.solicitacao.logs.filter(decisao_anulada=diretor).count(), 1)
        self.assertTrue(self.solicitacao.tem_reversao_sem_vinculo())
        self.assertFalse(self.solicitacao.can_edit(self.autor))
