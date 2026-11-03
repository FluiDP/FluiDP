import copy
import json
from pathlib import Path
import shutil
import subprocess
from html.parser import HTMLParser
from unittest import skipUnless

from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import Cargo, CustomUser, Lotacao, Solicitacao, TipoDocumento
from .time_validation import analisar_periodos, INTERVALO_FORA


def field(name, **kwargs):
    return {'name': name, 'label': name.replace('_', ' ').title(), 'type': 'text', 'required': False, **kwargs}


SHIFT = [field(name) for name in ('hora_inicio', 'hora_fim', 'inicio_intervalo', 'fim_intervalo')]
SHIFT.append(field('sem_intervalo', type='checkbox'))
REPEATER = [field('cronograma_he', type='repeater', sub_fields=SHIFT)]
BAD_ROW = {'hora_inicio': '07:00', 'hora_fim': '07:30', 'inicio_intervalo': '01:14', 'fim_intervalo': '02:17'}
AUTO = [field('entrada'), field('saida'), field('qtd_horas', extra_props={'auto_calc_time_diff': {'start': 'entrada', 'end': 'saida'}})]


CASES = [
    ('caso_2647', REPEATER, {'cronograma_he': [BAD_ROW]}, {('cronograma_he', 0, 'inicio_intervalo'), ('cronograma_he', 0, 'fim_intervalo')}),
    ('intervalo_valido', SHIFT, {'hora_inicio': '08:00', 'hora_fim': '17:00', 'inicio_intervalo': '12:00', 'fim_intervalo': '13:00'}, set()),
    ('meia_noite', SHIFT, {'hora_inicio': '22:00', 'hora_fim': '06:00', 'inicio_intervalo': '23:30', 'fim_intervalo': '00:30'}, set()),
    ('plantao_19_as_07_intervalo_01_as_02', SHIFT, {'hora_inicio': '19:00', 'hora_fim': '07:00', 'inicio_intervalo': '01:00', 'fim_intervalo': '02:00'}, set()),
    ('intervalo_no_final', SHIFT, {'hora_inicio': '22:00', 'hora_fim': '06:00', 'inicio_intervalo': '05:30', 'fim_intervalo': '06:00'}, set()),
    ('intervalo_parcialmente_fora', SHIFT, {'hora_inicio': '22:00', 'hora_fim': '06:00', 'inicio_intervalo': '05:30', 'fim_intervalo': '06:30'}, {('inicio_intervalo',), ('fim_intervalo',)}),
    ('sem_intervalo_ignora_dados_antigos', SHIFT, {**BAD_ROW, 'sem_intervalo': 'true'}, set()),
    ('sem_intervalo_booleano', SHIFT, {**BAD_ROW, 'sem_intervalo': True}, set()),
    ('horario_invalido', SHIFT, {'hora_inicio': '24:00', 'hora_fim': '25:65'}, {('hora_inicio',), ('hora_fim',)}),
    ('periodo_incompleto', SHIFT, {'hora_inicio': '08:00'}, {('hora_fim',)}),
    ('intervalo_ausente', SHIFT, {'hora_inicio': '08:00', 'hora_fim': '17:00'}, {('inicio_intervalo',), ('fim_intervalo',)}),
    ('formulario_vazio', SHIFT, {}, set()),
    ('periodo_zero', SHIFT, {'hora_inicio': '08:00', 'hora_fim': '08:00', 'sem_intervalo': True}, {('hora_inicio',), ('hora_fim',)}),
    ('duracao_invalida', [field('qtd_horas', extra_props={'count_time_field': True})], {'qtd_horas': '01:75'}, {('qtd_horas',)}),
    ('duracao_superior_24h', [field('qtd_horas', extra_props={'count_time_field': True})], {'qtd_horas': '125:30'}, set()),
    ('saldo_dp_assinado', [field('total_compensacao', type='calculated', calc_format='time')], {'total_compensacao': '-25:30'}, set()),
    ('auto_noite_valida', AUTO, {'entrada': '22:00', 'saida': '02:00', 'qtd_horas': '04:00'}, set()),
    ('auto_divergente', AUTO, {'entrada': '22:00', 'saida': '02:00', 'qtd_horas': '28:00'}, {('qtd_horas',)}),
    ('qualquer_nome_vinculado', [field('de'), field('ate'), field('total', extra_props={'auto_calc_time_diff': {'start': 'de', 'end': 'ate'}})], {'de': '18:00', 'ate': '18:00', 'total': '00:00'}, {('de',), ('ate',), ('total',)}),
    ('datas_invertidas', [field('data_inicio', type='date'), field('data_fim', type='date')], {'data_inicio': '2026-11-03', 'data_fim': '2026-11-02'}, {('data_fim',)}),
    ('data_inexistente', [field('data_inicio', type='date'), field('data_fim', type='date')], {'data_inicio': '2026-02-30', 'data_fim': '2026-03-01'}, {('data_inicio',)}),
    ('nao_marcar_numeros_comuns', [field('numero_inicio', type='number'), field('numero_fim', type='number')], {'numero_inicio': '1', 'numero_fim': '20'}, set()),
    ('duas_linhas_independentes', REPEATER, {'cronograma_he': [{'hora_inicio': '08:00', 'hora_fim': '09:00', 'sem_intervalo': True}, BAD_ROW]}, {('cronograma_he', 1, 'inicio_intervalo'), ('cronograma_he', 1, 'fim_intervalo')}),
]


class AvisosHorasTests(SimpleTestCase):
    def test_plantao_noturno_do_exemplo_tem_onze_horas_e_nenhum_alerta(self):
        from types import SimpleNamespace
        from .reports import horas_solicitacao
        values = {'cronograma_he': [{'hora_inicio': '19:00', 'hora_fim': '07:00',
            'inicio_intervalo': '01:00', 'fim_intervalo': '02:00'}]}
        self.assertEqual(analisar_periodos(REPEATER, values), {})
        sol = SimpleNamespace(dados_preenchidos={'schema': REPEATER, 'values': values},
            tipo_documento=SimpleNamespace(nome_documento='Pagamento de Hora Extra em Folha'))
        self.assertEqual(horas_solicitacao(sol), (660, 0))

    def test_cenarios_de_periodos_e_duracoes_sem_alterar_valores(self):
        for name, schema, values, expected in CASES:
            with self.subTest(name=name):
                before = copy.deepcopy(values)
                warnings = analisar_periodos(schema, values)
                self.assertEqual(set(warnings), expected)
                self.assertEqual(values, before)
        self.assertIn(INTERVALO_FORA, analisar_periodos(REPEATER, {'cronograma_he': [BAD_ROW]}).values())

    def test_ajustes_dp_nao_sao_tratados_como_divergencia_do_original(self):
        schema = [field('plano', type='repeater', sub_fields=[field('qtd_horas', extra_props={'count_time_field': True})]),
                  field('total_compensacao', type='calculated', calc_format='time', target_repeater='plano', target_subfield='qtd_horas')]
        self.assertEqual(analisar_periodos(schema, {'plano': [{'qtd_horas': '00:10'}], 'total_compensacao': '-00:38'}), {})

    @skipUnless(shutil.which('node'), 'Node necessário para conferir a validação do navegador')
    def test_navegador_e_servidor_dao_os_mesmos_avisos(self):
        script = Path(__file__).resolve().parent.parent / 'theme/static/js/time-validation.js'
        code = "const api = require(process.argv[1]); let input=''; process.stdin.on('data',x=>input+=x); process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(input).map(c=>api.analyze(c.schema,c.values)))));"
        result = subprocess.run([shutil.which('node'), '-e', code, str(script)],
            input=json.dumps([{'schema': s, 'values': v} for _, s, v, _ in CASES]),
            text=True, encoding='utf-8', capture_output=True, check=True)
        expected = [{json.dumps(list(k), separators=(',', ':')): v for k, v in analisar_periodos(s, values).items()}
                    for _, s, values, _ in CASES]
        self.assertEqual(json.loads(result.stdout), expected)


class WarningParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.warnings = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'data-time-warning' in attrs:
            self.warnings.append(attrs)


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class AvisosHorasInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lotacao = Lotacao.objects.create(nome_lotacao='Teste de horários')
        cls.autor = CustomUser.objects.create_user(username='autor_horarios', lotacao=cls.lotacao)
        cls.gestor = CustomUser.objects.create_user(username='gestor_horarios', lotacao=cls.lotacao,
            cargo=Cargo.objects.create(nome_cargo='Gestor', hierarquia=Cargo.HierarquiaChoices.GERENTE))
        cls.diretor = CustomUser.objects.create_user(username='diretor_horarios', lotacao=cls.lotacao,
            cargo=Cargo.objects.create(nome_cargo='Diretor', hierarquia=Cargo.HierarquiaChoices.DIRETOR))
        cls.dp = CustomUser.objects.create_user(username='dp_horarios', lotacao=cls.lotacao)
        cls.dp.groups.add(Group.objects.create(name='DP'))
        cls.tic = CustomUser.objects.create_user(username='tic_horarios', lotacao=cls.lotacao)
        cls.tic.groups.add(Group.objects.create(name='SYSTEM_ADMIN'))
        cls.lotacao.chefia = cls.gestor
        cls.lotacao.save()
        cls.tipo = TipoDocumento.objects.create(nome_documento='Pagamento de Hora Extra em Folha', definicao_formulario=REPEATER)
        cls.sol = Solicitacao.objects.create(colaborador=cls.autor, tipo_documento=cls.tipo,
            status='FINALIZADO', dados_preenchidos={'schema': REPEATER, 'values': {'cronograma_he': [BAD_ROW]}})

    def test_todos_os_perfis_veem_o_alerta_nas_celulas_de_horas(self):
        for usuario in (self.autor, self.gestor, self.diretor, self.dp, self.tic):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                response = self.client.get(reverse('colaborador:get_solicitacao_detalhes', args=[self.sol.pk]))
                self.assertEqual(response.status_code, 200)
                warnings = WarningParser(response.content.decode()).warnings
                self.assertEqual(len(warnings), 2)
                self.assertTrue(all(w['title'] == INTERVALO_FORA for w in warnings))
                self.assertTrue(all(w['tabindex'] == '0' and w['aria-label'] for w in warnings))
                self.assertContains(response, 'name="warning-outline"')
        self.sol.refresh_from_db()
        self.assertEqual(self.sol.dados_preenchidos['values']['cronograma_he'][0], BAD_ROW)

    def test_visualizacao_e_impressao_usam_schema_historico(self):
        self.tipo.definicao_formulario = []
        self.tipo.save()
        self.sol.arquivado = True
        self.sol.save()
        self.client.force_login(self.autor)
        response = self.client.get(reverse('gerar_pdf_solicitacao', args=[self.sol.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(WarningParser(response.content.decode()).warnings), 2)
        self.assertContains(response, 'css/time-validation.css')

    def test_formularios_criacao_e_edicao_carregam_verificacao_dinamica(self):
        self.client.force_login(self.autor)
        response = self.client.get(reverse('colaborador:get_create_solicitacao_form', args=[self.tipo.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-time-validation')
        self.sol.status = 'PENDENTE_GESTOR'
        self.sol.save()
        response = self.client.get(reverse('edit_solicitacao_modal', args=[self.sol.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-time-validation')
        self.assertContains(response, 'id="edit-time-schema"')

    def test_periodo_valido_nao_tem_etiqueta(self):
        self.sol.dados_preenchidos['values']['cronograma_he'] = [{'hora_inicio': '22:00', 'hora_fim': '06:00', 'sem_intervalo': 'true'}]
        self.sol.save()
        self.client.force_login(self.autor)
        response = self.client.get(reverse('colaborador:get_solicitacao_detalhes', args=[self.sol.pk]))
        self.assertEqual(WarningParser(response.content.decode()).warnings, [])

    def test_aviso_nao_bloqueia_envio_nem_modifica_horarios(self):
        self.client.force_login(self.autor)
        response = self.client.post(reverse('colaborador:salvar_solicitacao', args=[self.tipo.pk]), {
            **{'cronograma_he_' + name + '[]': value for name, value in BAD_ROW.items()},
            'cronograma_he_sem_intervalo[]': 'false',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enviada com sucesso')
        sol = Solicitacao.objects.exclude(pk=self.sol.pk).get()
        for name, value in BAD_ROW.items():
            self.assertEqual(sol.dados_preenchidos['values']['cronograma_he'][0][name], value)
