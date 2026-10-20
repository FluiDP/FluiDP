from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import CustomUser


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ColaboradoresSituacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dp = CustomUser.objects.create_user(username='dp_filtro')
        cls.dp.groups.add(Group.objects.create(name='DP'))
        cls.ativo = CustomUser.objects.create_user(
            username='ativo_filtro', first_name='Pessoa ativa', matricula='100',
        )
        cls.inativo = CustomUser.objects.create_user(
            username='inativo_filtro', first_name='Pessoa arquivada', matricula='200',
            is_active=False,
        )
        CustomUser.objects.create_user(username='admin', is_active=False)
        CustomUser.objects.create_user(username='reservado', matricula='000000')

    def setUp(self):
        self.client.force_login(self.dp)
        self.url = reverse('administracao:colaboradores')

    def usuarios(self, resposta):
        self.assertEqual(resposta.status_code, 200)
        return set(resposta.context['colaboradores'].object_list)

    def test_padrao_e_situacao_invalida_mostram_somente_ativos(self):
        for parametros in ({}, {'situacao': 'invalida'}):
            with self.subTest(parametros=parametros):
                self.assertEqual(self.usuarios(self.client.get(self.url, parametros)),
                                 {self.dp, self.ativo})

    def test_arquivados_permite_buscar_e_visualizar_sem_oferecer_arquivamento(self):
        resposta = self.client.get(
            self.url, {'situacao': 'arquivados', 'q': '200'}, HTTP_HX_REQUEST='true',
        )
        self.assertEqual(self.usuarios(resposta), {self.inativo})
        self.assertTemplateUsed(resposta, 'painel/dp/_content_colaboradores.html')
        self.assertContains(resposta, 'Arquivado/Inativo')
        self.assertNotContains(resposta, reverse('administracao:archive_colaborador', args=[self.inativo.pk]))
        detalhes = self.client.get(reverse('administracao:visualizar_colaborador', args=[self.inativo.pk]))
        self.assertContains(detalhes, 'Pessoa arquivada')

    def test_todos_preserva_exclusao_das_contas_reservadas(self):
        self.assertEqual(self.usuarios(self.client.get(self.url, {'situacao': 'todos'})),
                         {self.dp, self.ativo, self.inativo})

    def test_busca_paginacao_e_ordenacao_com_arquivados(self):
        for indice in range(16):
            CustomUser.objects.create_user(
                username=f'historico_{indice}', first_name=f'Historico {indice:02}',
                is_active=False,
            )
        parametros = {'situacao': 'arquivados', 'q': 'Historico', 'sort': '-first_name'}
        primeira = self.client.get(self.url, parametros, HTTP_HX_REQUEST='true')
        self.assertEqual(primeira.context['colaboradores'].paginator.count, 16)
        self.assertEqual(primeira.context['colaboradores'][0].first_name, 'Historico 15')
        segunda = self.client.get(self.url, {**parametros, 'page': 2}, HTTP_HX_REQUEST='true')
        self.assertEqual(len(self.usuarios(segunda)), 1)
        self.assertEqual(segunda.context['colaboradores'][0].first_name, 'Historico 00')
        self.assertFalse(self.usuarios(primeira) & self.usuarios(segunda))

    def test_arquivar_move_usuario_para_listagem_de_inativos(self):
        resposta = self.client.post(reverse('administracao:archive_colaborador', args=[self.ativo.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.ativo.refresh_from_db()
        self.assertFalse(self.ativo.is_active)
        self.assertNotIn(self.ativo, self.usuarios(self.client.get(self.url)))
        self.assertIn(self.ativo, self.usuarios(self.client.get(self.url, {'situacao': 'arquivados'})))

    def test_colaborador_comum_nao_pode_consultar_arquivados(self):
        self.client.force_login(self.ativo)
        self.assertEqual(self.client.get(self.url, {'situacao': 'arquivados'}).status_code, 403)

    def test_administrador_do_sistema_pode_consultar_arquivados(self):
        self.ativo.groups.add(Group.objects.create(name='SYSTEM_ADMIN'))
        self.client.force_login(self.ativo)
        self.assertEqual(self.usuarios(self.client.get(self.url, {'situacao': 'arquivados'})),
                         {self.inativo})
