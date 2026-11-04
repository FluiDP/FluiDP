from django.test import TestCase, override_settings
from django.urls import reverse, resolve
from .models import CustomUser, TipoDocumento, Solicitacao
from . import views_colaborador


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class MobileModalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = CustomUser.objects.create_user(username='mobile_modal')
        doc = TipoDocumento.objects.create(nome_documento='Documento de teste', definicao_formulario=[])
        cls.sol = Solicitacao.objects.create(colaborador=cls.user, tipo_documento=doc, status='FINALIZADO')

    def setUp(self):
        self.client.force_login(self.user)

    def test_rotas_reutilizam_views(self):
        for name, view in (('get_solicitacao_detalhes', views_colaborador.get_solicitacao_detalhes_view),
                            ('solicitacao_logs', views_colaborador.get_solicitacao_logs_view)):
            self.assertIs(resolve(reverse('mobile:'+name,args=[self.sol.pk])).func, view)

    def test_mobile_carrega_detalhes_historico_e_impressao_sem_redirecionar(self):
        for htmx in (True, False):
            headers = {'HTTP_USER_AGENT': 'iPhone Mobile'}
            if htmx:
                headers['HTTP_HX_REQUEST'] = 'true'
            response = self.client.get(reverse('mobile:get_solicitacao_detalhes',args=[self.sol.pk]), **headers)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, reverse('mobile:solicitacao_logs',args=[self.sol.pk]))
            self.assertContains(response, reverse('mobile:gerar_pdf_solicitacao',args=[self.sol.pk]))
            response = self.client.get(reverse('mobile:solicitacao_logs',args=[self.sol.pk]), **headers)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, reverse('mobile:get_solicitacao_detalhes',args=[self.sol.pk]))
            response = self.client.get(reverse('mobile:gerar_pdf_solicitacao',args=[self.sol.pk]), **headers)
            self.assertEqual(response.status_code, 200)

    def test_cards_e_avisos_de_horas(self):
        response = self.client.get(reverse('mobile:home'))
        self.assertContains(response, reverse('mobile:get_solicitacao_detalhes',args=[self.sol.pk]))
        self.assertContains(response, 'js/time-validation.js')
        self.assertContains(response, 'css/time-validation.css')
        self.assertContains(response, 'id="modal-spot"')

    def test_anonimo_nao_abre_modal(self):
        self.client.logout()
        response = self.client.get(reverse('mobile:get_solicitacao_detalhes',args=[self.sol.pk]))
        self.assertEqual(response.status_code, 302)
