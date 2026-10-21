import html
import json
import re

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .models import CustomUser, TipoDocumento


class DocumentoJSONEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dp = CustomUser.objects.create_user(username='dp_json_editor')
        cls.dp.groups.add(Group.objects.create(name='DP'))
        cls.schema = [{'name': 'observacao', 'label': 'Observação', 'type': 'text', 'required': True}]
        cls.documento = TipoDocumento.objects.create(
            nome_documento='Documento JSON', definicao_formulario=cls.schema,
        )

    def setUp(self):
        self.client.force_login(self.dp)
        self.url = reverse('administracao:edit_documento', args=[self.documento.pk])

    def valor_json(self, resposta):
        markup = resposta.content.decode()
        campo = re.search(r'<textarea[^>]*name="definicao_formulario"[^>]*>(.*?)</textarea>', markup, re.S)
        self.assertIsNotNone(campo)
        return html.unescape(campo.group(1)).lstrip('\n')

    def dados(self, valor):
        return {
            'nome_documento': 'Documento JSON', 'dia_inicio': 1, 'dia_fim': 31,
            'tipo_referencia': 'NENHUMA', 'limite_dias_antecedencia': 0,
            'definicao_formulario': valor, 'disponivel': 'on',
        }

    def test_modal_exibe_json_indentado_sem_alterar_cadastro(self):
        resposta = self.client.get(self.url, HTTP_HX_REQUEST='true')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.valor_json(resposta), json.dumps(self.schema, ensure_ascii=False, indent=2))
        self.assertContains(resposta, 'data-json-editor="true"')
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.definicao_formulario, self.schema)

    def test_salvar_json_formatado_preserva_tipos_e_acentos(self):
        schema = [{'name': 'campo', 'label': 'Informação', 'type': 'text', 'required': False}]
        resposta = self.client.post(self.url, self.dados(json.dumps(schema, ensure_ascii=False, indent=2)))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.headers['HX-Trigger'], 'updateContent')
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.definicao_formulario, schema)

    def test_json_invalido_permanece_no_modal_sem_sobrescrever_cadastro(self):
        invalido = '[{"name": "incompleto"'
        resposta = self.client.post(self.url, self.dados(invalido), HTTP_HX_REQUEST='true')
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.valor_json(resposta), invalido)
        self.assertTrue(resposta.context['form'].errors.get('definicao_formulario'))
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.definicao_formulario, self.schema)
