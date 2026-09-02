from datetime import date

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from .models import TipoDocumento


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
