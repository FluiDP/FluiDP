from datetime import date, datetime
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Cargo, CustomUser, LogAprovacao, Notificacao, Solicitacao, TipoDocumento
from .services import aprovar_solicitacao, cancelar_solicitacao_por_prazo


class PrazoTrocasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.autor = CustomUser.objects.create_user(username='autor_prazo')
        cargo = Cargo.objects.create(nome_cargo='Diretor prazo', hierarquia=Cargo.HierarquiaChoices.DIRETOR)
        cls.aprovador = CustomUser.objects.create_user(username='aprovador_prazo', cargo=cargo)
        cls.aprovador.groups.add(Group.objects.create(name='DP'))
        cls.plantao = TipoDocumento.objects.create(
            nome_documento='Troca de Plantão', tipo_referencia='MENSAL',
            dia_abertura_mes_anterior=25, dia_limite_mes_referencia=10,
        )
        cls.folga = TipoDocumento.objects.create(nome_documento='Troca de Folga', dia_inicio=25, dia_fim=10)

    def nova(self, tipo=None, status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
             abertura=datetime(2026, 9, 25, 12), referencia=date(2026, 10, 1)):
        with patch('django.utils.timezone.localdate', return_value=abertura.date()):
            sol = Solicitacao.objects.create(
                colaborador=self.autor, colaborador_secundario=self.aprovador,
                aprovador_atual=self.aprovador, tipo_documento=tipo or self.plantao,
                status=status, mes_referencia=referencia,
            )
        Solicitacao.objects.filter(pk=sol.pk).update(
            data=timezone.make_aware(abertura), mes_referencia=referencia)
        sol.refresh_from_db()
        return sol

    def test_janela_inclui_dia_limite_e_expira_no_dia_seguinte(self):
        for tipo in (self.plantao, self.folga):
            sol = self.nova(tipo)
            self.assertIsNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 10, 10)))
            self.assertIsNotNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 10, 11)))

    def test_reabertura_nao_revalida_solicitacao_do_ciclo_anterior(self):
        for tipo in (self.plantao, self.folga):
            sol = self.nova(tipo)
            self.assertIsNotNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 10, 25)))
            self.assertIsNotNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 11, 1)))

    def test_plantao_legado_sem_referencia_usa_data_original(self):
        sol = self.nova(referencia=None)
        self.assertIsNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 10, 10)))
        self.assertIsNotNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 10, 11)))

    def test_virada_de_ano_e_fevereiro(self):
        for tipo in (self.plantao, self.folga):
            sol = self.nova(tipo, abertura=datetime(2025, 12, 25, 12), referencia=date(2026, 1, 1))
            self.assertIsNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 1, 10)))
            self.assertIsNotNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 1, 11)))
        tipo = TipoDocumento.objects.create(nome_documento='Troca de Folga fevereiro', dia_inicio=1, dia_fim=31)
        sol = self.nova(tipo, abertura=datetime(2026, 2, 1, 12), referencia=None)
        self.assertIsNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 2, 28)))
        self.assertIsNotNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 3, 1)))

    def test_antecedencia_da_criacao_nao_encurta_janela_de_aprovacao(self):
        self.plantao.limite_dias_antecedencia = 2
        self.plantao.definicao_formulario = [
            {'name': 'data_plantao_origem', 'label': 'Origem', 'type': 'date', 'is_event_date': True},
        ]
        self.plantao.save()
        sol = self.nova()
        sol.dados_preenchidos = {'values': {'data_plantao_origem': '2026-10-10'}}
        self.assertIsNone(sol.motivo_prazo_aprovacao_expirado(date(2026, 10, 10)))

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 11))
    def test_scheduler_cancela_todas_as_etapas_e_nao_duplica_historico(self, _):
        solicitacoes = [self.nova(status=status) for status in (
            Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
            Solicitacao.StatusChoices.PENDENTE_GESTOR,
            Solicitacao.StatusChoices.PENDENTE_DIRETOR,
            Solicitacao.StatusChoices.PENDENTE_DP,
            Solicitacao.StatusChoices.LANCAMENTO,
        )]
        call_command('request_scheduler', stdout=StringIO())
        call_command('request_scheduler', stdout=StringIO())
        for sol in solicitacoes:
            sol.refresh_from_db()
            self.assertEqual(sol.status, Solicitacao.StatusChoices.CANCELADO)
            self.assertIsNone(sol.aprovador_atual)
            self.assertEqual(sol.logs.filter(acao=LogAprovacao.AcaoChoices.CANCELAMENTO_SISTEMA).count(), 1)
            self.assertEqual(Notificacao.todos_objetos.filter(
                solicitacao=sol, tipo=Notificacao.TipoChoices.CANCELADA_SISTEMA).count(), 1)
            self.assertIsNotNone(sol.data_finalizacao)

    def test_estados_terminais_e_outros_documentos_sao_preservados(self):
        outro = TipoDocumento.objects.create(nome_documento='Outro documento', dia_inicio=25, dia_fim=10)
        solicitacoes = [self.nova(status=status) for status in (
            Solicitacao.StatusChoices.FINALIZADO, Solicitacao.StatusChoices.RECUSADO,
            Solicitacao.StatusChoices.CANCELADO,
        )] + [self.nova(outro)]
        for sol in solicitacoes:
            status = sol.status
            self.assertIsNone(cancelar_solicitacao_por_prazo(sol, date(2026, 10, 11)))
            sol.refresh_from_db()
            self.assertEqual(sol.status, status)
            self.assertFalse(sol.logs.exists())

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 11))
    def test_aprovacao_cancela_imediatamente_e_persiste_apesar_do_erro(self, _):
        for status in (
            Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
            Solicitacao.StatusChoices.PENDENTE_GESTOR,
            Solicitacao.StatusChoices.PENDENTE_DIRETOR,
            Solicitacao.StatusChoices.PENDENTE_DP,
            Solicitacao.StatusChoices.LANCAMENTO,
        ):
            with self.subTest(status=status):
                sol = self.nova(status=status)
                with self.assertRaisesMessage(ValidationError, 'Não é possível aprovar após o prazo'):
                    aprovar_solicitacao(sol, self.aprovador, self.aprovador)
                sol.refresh_from_db()
                self.assertEqual(sol.status, Solicitacao.StatusChoices.CANCELADO)
                self.assertEqual(sol.logs.count(), 1)

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 10))
    def test_aprovacao_no_ultimo_dia_permitida(self, _):
        sol = self.nova(status=Solicitacao.StatusChoices.PENDENTE_DIRETOR)
        aprovar_solicitacao(sol, self.aprovador, self.aprovador)
        sol.refresh_from_db()
        self.assertEqual(sol.status, Solicitacao.StatusChoices.PENDENTE_DP)

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 11))
    def test_usuario_sem_permissao_nao_modifica_solicitacao(self, _):
        sol = self.nova()
        with self.assertRaises(PermissionError):
            aprovar_solicitacao(sol, self.autor, self.autor)
        sol.refresh_from_db()
        self.assertEqual(sol.status, Solicitacao.StatusChoices.PENDENTE_GESTOR)
        self.assertFalse(sol.logs.exists())

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 11))
    def test_instancia_antiga_nao_reaprova_pedido_cancelado(self, _):
        sol = self.nova()
        antiga = Solicitacao.objects.get(pk=sol.pk)
        cancelar_solicitacao_por_prazo(sol)
        with self.assertRaises(PermissionError):
            aprovar_solicitacao(antiga, self.aprovador, self.aprovador)
        sol.refresh_from_db()
        self.assertEqual(sol.status, Solicitacao.StatusChoices.CANCELADO)

    @patch('django.utils.timezone.localdate', return_value=date(2026, 10, 11))
    def test_aprovacao_em_lote_cancela_vencida_e_aprova_valida(self, _):
        vencida = self.nova(status=Solicitacao.StatusChoices.PENDENTE_DP)
        outro = TipoDocumento.objects.create(nome_documento='Documento sem prazo')
        valida = self.nova(outro, status=Solicitacao.StatusChoices.PENDENTE_DP)
        self.client.force_login(self.aprovador)
        resposta = self.client.post(reverse('processar_lote_solicitacoes'), {
            'solicitacoes_ids': [vencida.pk, valida.pk], 'action_lote': 'aprovar',
        })
        self.assertEqual(resposta.status_code, 200)
        vencida.refresh_from_db()
        valida.refresh_from_db()
        self.assertEqual(vencida.status, Solicitacao.StatusChoices.CANCELADO)
        self.assertEqual(valida.status, Solicitacao.StatusChoices.LANCAMENTO)
