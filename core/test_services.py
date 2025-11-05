import datetime
from django.test import TestCase
from django.utils import timezone
from .models import Cargo, Lotacao, CustomUser, TipoDocumento, Solicitacao, LogAprovacao
from .services import (
    ferias_ativas,
    encontrar_aprovador,
    _pode_ator_aprovar,
    aprovar_solicitacao
)

class ServicosDeSolicitacaoTest(TestCase):

    def setUp(self):
        """
        Configura um mini-organograma e dados base para todos os testes.
        
        Estrutura:
        - Diretoria (Chefe: Diretor A)
          - Gerência (Chefe: Gestor A, Sub: Gestor B)
            - Equipe (Sem chefe, Pai: Gerência)
        """
        
        self.cargo_padrao = Cargo.objects.create(nome_cargo="Analista", hierarquia=Cargo.HierarquiaChoices.PADRAO)
        self.cargo_gerente = Cargo.objects.create(nome_cargo="Gerente", hierarquia=Cargo.HierarquiaChoices.GERENTE)
        self.cargo_diretor = Cargo.objects.create(nome_cargo="Diretor", hierarquia=Cargo.HierarquiaChoices.DIRETOR)

        self.diretor_a = CustomUser.objects.create_user(username="diretor_a", cargo=self.cargo_diretor)
        self.diretor_b = CustomUser.objects.create_user(username="diretor_b", cargo=self.cargo_diretor)
        self.gestor_a = CustomUser.objects.create_user(username="gestor_a", cargo=self.cargo_gerente)
        self.gestor_b_sub = CustomUser.objects.create_user(username="gestor_b_sub", cargo=self.cargo_gerente)
        self.colaborador = CustomUser.objects.create_user(username="colaborador", cargo=self.cargo_padrao)
        
        self.gestor_ferias = CustomUser.objects.create_user(username="gestor_ferias", cargo=self.cargo_gerente)
        hoje = timezone.now().date()
        self.gestor_ferias.ausencia_inicio = hoje - datetime.timedelta(days=5)
        self.gestor_ferias.ausencia_fim = hoje + datetime.timedelta(days=5)
        self.gestor_ferias.save()

        self.lot_diretoria = Lotacao.objects.create(nome_lotacao="Diretoria", chefia=self.diretor_a)
        self.lot_gerencia = Lotacao.objects.create(
            nome_lotacao="Gerência",
            chefia=self.gestor_a,
            chefia_secundaria=self.gestor_b_sub,
            lotacao_pai=self.lot_diretoria
        )
        self.lot_equipe = Lotacao.objects.create(nome_lotacao="Equipe", lotacao_pai=self.lot_gerencia)
        
        self.colaborador.lotacao = self.lot_equipe
        self.colaborador.save()
        self.gestor_a.lotacao = self.lot_gerencia
        self.gestor_a.save()
        self.diretor_a.lotacao = self.lot_diretoria
        self.diretor_a.save()

        self.doc_simples = TipoDocumento.objects.create(
            nome_documento="Abono Simples",
            requer_aprovacao_gestor=True,
            requer_aprovacao_diretor=False
        )
        self.doc_complexo = TipoDocumento.objects.create(
            nome_documento="Férias",
            requer_aprovacao_gestor=True,
            requer_aprovacao_diretor=True
        )

        self.solicitacao_gestor = Solicitacao.objects.create(
            colaborador=self.colaborador,
            tipo_documento=self.doc_complexo,
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
            aprovador_atual=self.gestor_a
        )
        
        self.solicitacao_diretor = Solicitacao.objects.create(
            colaborador=self.colaborador,
            tipo_documento=self.doc_complexo,
            status=Solicitacao.StatusChoices.PENDENTE_DIRETOR,
            aprovador_atual=None
        )

    def test_ferias_ativas(self):
        """Testa se o usuário está de férias (True) ou não (False)."""
        self.assertTrue(ferias_ativas(self.gestor_ferias))
        self.assertFalse(ferias_ativas(self.colaborador))
        self.assertFalse(ferias_ativas(self.gestor_a))

    def test_encontrar_aprovador_gestor(self):
        """Testa se encontra o gestor correto subindo na hierarquia."""

        aprovador = encontrar_aprovador(self.solicitacao_gestor)
        
        self.assertEqual(aprovador, self.gestor_a)

    def test_encontrar_aprovador_gestor_em_ferias(self):
        """Testa se ignora o gestor de férias e pega o substituto."""
        
        self.gestor_a.ausencia_inicio = timezone.now().date()
        self.gestor_a.ausencia_fim = timezone.now().date() + datetime.timedelta(days=10)
        self.gestor_a.save()
        
        aprovador = encontrar_aprovador(self.solicitacao_gestor)
        self.assertEqual(aprovador, self.gestor_b_sub)

    def test_pode_ator_aprovar_gestor_correto(self):
        """Testa se o GESTOR correto pode aprovar."""

        pode = _pode_ator_aprovar(self.solicitacao_gestor, self.gestor_a)
        self.assertTrue(pode)

    def test_pode_ator_aprovar_gestor_incorreto(self):
        """Testa se um GESTOR aleatório NÃO pode aprovar uma pendência de outro."""

        pode = _pode_ator_aprovar(self.solicitacao_gestor, self.gestor_b_sub)
        self.assertFalse(pode)

    def test_pode_ator_aprovar_diretor_na_fila(self):
        """Testa se QUALQUER diretor pode aprovar uma solicitação PENDENTE_DIRETOR."""
        
        pode_dir_a = _pode_ator_aprovar(self.solicitacao_diretor, self.diretor_a)
        pode_dir_b = _pode_ator_aprovar(self.solicitacao_diretor, self.diretor_b)
        
        self.assertTrue(pode_dir_a, "Diretor A deveria poder aprovar")
        self.assertTrue(pode_dir_b, "Diretor B deveria poder aprovar")

    def test_pode_ator_aprovar_gestor_nao_pode_ser_diretor(self):
        """Testa se um Gestor NÃO pode aprovar uma pendência de Diretor."""
        pode = _pode_ator_aprovar(self.solicitacao_diretor, self.gestor_a)
        self.assertFalse(pode)

    def test_aprovar_solicitacao_fluxo_simples(self):
        """Testa Gestor -> Aprovado (documento não requer diretor)."""
        
        sol_simples = Solicitacao.objects.create(
            colaborador=self.colaborador,
            tipo_documento=self.doc_simples,
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
            aprovador_atual=self.gestor_a
        )
        
        aprovar_solicitacao(sol_simples, self.gestor_a)
        
        sol_simples.refresh_from_db()
        
        self.assertEqual(sol_simples.status, Solicitacao.StatusChoices.APROVADO)
        self.assertIsNone(sol_simples.aprovador_atual)
        self.assertEqual(LogAprovacao.objects.count(), 1)
        self.assertEqual(LogAprovacao.objects.first().acao, LogAprovacao.AcaoChoices.APROVADO_GESTOR)

    def test_aprovar_solicitacao_fluxo_complexo(self):
        """Testa Gestor -> Diretor -> Aprovado."""

        self.assertEqual(self.solicitacao_gestor.status, Solicitacao.StatusChoices.PENDENTE_GESTOR)
        
        aprovar_solicitacao(self.solicitacao_gestor, self.gestor_a)
        
        self.solicitacao_gestor.refresh_from_db()
        self.assertEqual(self.solicitacao_gestor.status, Solicitacao.StatusChoices.PENDENTE_DIRETOR)
        self.assertIsNone(self.solicitacao_gestor.aprovador_atual, "Deveria ser None (fila)")

        aprovar_solicitacao(self.solicitacao_gestor, self.diretor_b)
        
        self.solicitacao_gestor.refresh_from_db()
        self.assertEqual(self.solicitacao_gestor.status, Solicitacao.StatusChoices.APROVADO)
        self.assertIsNone(self.solicitacao_gestor.aprovador_atual)
        
        self.assertEqual(LogAprovacao.objects.count(), 2)
        logs = LogAprovacao.objects.all().order_by('data_acao')
        self.assertEqual(logs[0].acao, LogAprovacao.AcaoChoices.APROVADO_GESTOR)
        self.assertEqual(logs[0].ator, self.gestor_a)
        self.assertEqual(logs[1].acao, LogAprovacao.AcaoChoices.APROVADO_DIRETOR)
        self.assertEqual(logs[1].ator, self.diretor_b)

    def test_aprovar_solicitacao_permissao_negada(self):
        """Testa se um ator não autorizado falha ao tentar aprovar."""
        
        
        with self.assertRaises(PermissionError):
            aprovar_solicitacao(self.solicitacao_gestor, self.diretor_a)
            
        self.solicitacao_gestor.refresh_from_db()
        self.assertEqual(self.solicitacao_gestor.status, Solicitacao.StatusChoices.PENDENTE_GESTOR)
        self.assertEqual(LogAprovacao.objects.count(), 0)
