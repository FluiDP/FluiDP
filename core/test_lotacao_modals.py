from datetime import timedelta

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import CustomUser, Lotacao, Solicitacao, TipoDocumento


class LotacaoModalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dp = CustomUser.objects.create_user(username='dp_modal', cpf='11122233396')
        cls.dp.groups.add(Group.objects.create(name='DP'))
        cls.gestor = CustomUser.objects.create_user(
            username='gestor_modal', first_name='Gestor Principal', cpf='52998224725',
            ausencia_inicio=timezone.localdate() - timedelta(days=1),
            ausencia_fim=timezone.localdate() + timedelta(days=1),
        )
        cls.secundario = CustomUser.objects.create_user(
            username='segundo_modal', first_name='Gestor Secundário', cpf='12345678909',
        )
        cls.lotacao = Lotacao.objects.create(
            nome_lotacao='Unidade Modal', chefia=cls.gestor, chefia_secundaria=cls.secundario,
        )
        cls.colaborador = CustomUser.objects.create_user(
            username='colaborador_modal', first_name='Pessoa da Unidade',
            cpf='39053344705', matricula='12345', lotacao=cls.lotacao,
        )
        cls.documento = TipoDocumento.objects.create(nome_documento='Documento Modal')

    def setUp(self):
        self.client.force_login(self.dp)

    def test_modal_lotacao_exibe_colaboradores_e_chefia_ativa(self):
        resposta = self.client.get(reverse('administracao:visualizar_lotacao', args=[self.lotacao.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'Gestor Principal')
        self.assertContains(resposta, 'Gestor Secundário')
        self.assertContains(resposta, 'Ausente')
        self.assertContains(resposta, 'Ativo')
        self.assertContains(resposta, 'Pessoa da Unidade')
        self.assertContains(resposta, '12345')

    def test_modal_colaborador_conta_autoria_e_participacao_no_periodo(self):
        propria = Solicitacao.objects.create(colaborador=self.colaborador, tipo_documento=self.documento)
        secundaria = Solicitacao.objects.create(
            colaborador=self.gestor, colaborador_secundario=self.colaborador,
            tipo_documento=self.documento,
        )
        antiga = Solicitacao.objects.create(colaborador=self.colaborador, tipo_documento=self.documento)
        Solicitacao.objects.filter(pk=antiga.pk).update(data=timezone.now() - timedelta(days=60))

        hoje = timezone.localdate().isoformat()
        resposta = self.client.get(
            reverse('administracao:visualizar_colaborador', args=[self.colaborador.pk]),
            {'data_inicio': hoje, 'data_fim': hoje},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.context['total_solicitacoes'], 2)
        self.assertContains(resposta, f'#{propria.pk}')
        self.assertContains(resposta, f'#{secundaria.pk}')
        self.assertNotContains(resposta, f'#{antiga.pk}')
