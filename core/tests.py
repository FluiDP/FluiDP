from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from .models import Cargo, CustomUser, Notificacao, TipoDocumento
from .services import (
    criar_resumo_semanal_usuario,
    deve_enviar_email_notificacao,
    preparar_aviso_login,
)


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


class AvisoLoginTests(TestCase):
    def test_agrupa_eventos_e_nao_exibe_novamente(self):
        usuario = CustomUser.objects.create_user(
            username='usuario_teste', password='senha-segura', cpf='12345678909'
        )
        for tipo in [
            Notificacao.TipoChoices.CANCELADA_SISTEMA,
            Notificacao.TipoChoices.CANCELADA_SISTEMA,
            Notificacao.TipoChoices.RECUSADA,
        ]:
            Notificacao.objects.create(
                destinatario=usuario, tipo=tipo, titulo='Aviso', mensagem='Mensagem'
            )

        primeira_requisicao = SimpleNamespace(session={})
        preparar_aviso_login(primeira_requisicao, usuario)
        self.assertEqual(
            primeira_requisicao.session['aviso_solicitacoes_login'],
            {'canceladas': 2, 'recusadas': 1},
        )

        segunda_requisicao = SimpleNamespace(session={})
        preparar_aviso_login(segunda_requisicao, usuario)
        self.assertNotIn('aviso_solicitacoes_login', segunda_requisicao.session)


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
