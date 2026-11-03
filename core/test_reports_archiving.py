from datetime import datetime, timedelta
from types import SimpleNamespace

from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Cargo, CustomUser, Lotacao, Solicitacao, TipoDocumento
from .reports import horas_solicitacao, minutos_duracao


class HorasRelatorioTests(SimpleTestCase):
    def sol(self, schema, values):
        return SimpleNamespace(dados_preenchidos={'schema': schema, 'values': values},
                               tipo_documento=SimpleNamespace(nome_documento='Pagamento de Hora Extra em Folha'))

    def test_duracao_assinada_e_minutos_invalidos(self):
        self.assertEqual(minutos_duracao('-25:30'), -1530)
        for value in ('01:75', '1-0:00', 'texto', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                minutos_duracao(value)

    def test_compensacao_usa_as_duas_pontas_sem_perder_duracao_negativa(self):
        schema = [{'name': name, 'type': 'calculated', 'calc_format': 'time'}
                  for name in ('total_ocorrencia', 'total_compensacao')]
        for origem, plano in (('10:00', '-08:00'), ('-10:00', '08:00')):
            self.assertEqual(horas_solicitacao(self.sol(schema, {
                'total_ocorrencia': origem, 'total_compensacao': plano,
            })), (0, 480))

    def test_total_salvo_pelo_dp_prevalece_sobre_linhas(self):
        schema = [{'name': 'total_geral_horas', 'type': 'calculated', 'calc_format': 'time'},
                  {'name': 'cronograma_he', 'type': 'repeater'}]
        self.assertEqual(horas_solicitacao(self.sol(schema, {
            'total_geral_horas': '02:00', 'cronograma_he': [{'hora_inicio': '08:00', 'hora_fim': '20:00'}],
        })), (120, 0))

    def test_intervalo_fora_da_jornada_nao_produz_total_incorreto(self):
        with self.assertRaises(ValueError):
            horas_solicitacao(self.sol([{'name': 'cronograma_he', 'type': 'repeater'}], {
                'cronograma_he': [{'hora_inicio': '08:00', 'hora_fim': '17:00',
                                   'inicio_intervalo': '20:00', 'fim_intervalo': '21:00'}],
            }))


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class RelatorioArquivamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lotacao = Lotacao.objects.create(nome_lotacao='Histórico', arquivado=True)
        cls.colab = CustomUser.objects.create_user(username='murilo_teste', cpf='52998224725',
                                                   matricula='1915', lotacao=cls.lotacao)
        cls.doc = TipoDocumento.objects.create(nome_documento='Documento', definicao_formulario=[])
        cls.cargo = Cargo.objects.create(nome_cargo='Direção', hierarquia=Cargo.HierarquiaChoices.DIRETOR)
        cls.diretor = CustomUser.objects.create_user(username='diretor', cpf='11122233396', cargo=cls.cargo)
        cls.dp = CustomUser.objects.create_user(username='dp', cpf='12345678909', lotacao=cls.lotacao)
        cls.dp.groups.add(Group.objects.create(name='DP'))
        cls.tic = CustomUser.objects.create_user(username='tic', cpf='11144477735', lotacao=cls.lotacao)
        cls.tic.groups.add(Group.objects.create(name='SYSTEM_ADMIN'))
        cls.gestor = CustomUser.objects.create_user(username='gestor', cpf='00000000191', lotacao=cls.lotacao,
            cargo=Cargo.objects.create(nome_cargo='Gerência', hierarquia=Cargo.HierarquiaChoices.GERENTE))
        cls.lotacao.chefia = cls.gestor
        cls.lotacao.save()
        cls.data = timezone.make_aware(datetime(2026, 10, 31, 23, 59, 59, 999999))
        for i in range(25):
            sol = Solicitacao.objects.create(colaborador=cls.colab, tipo_documento=cls.doc,
                arquivado=i < 24, status='RECUSADO' if i < 2 else 'FINALIZADO')
            Solicitacao.objects.filter(pk=sol.pk).update(data=cls.data)

    def report(self, **params):
        return self.client.get(reverse('relatorio_geral'), {
            'data_inicio': '2026-10-01', 'data_fim': '2026-10-31', **params,
        })

    def test_25_solicitacoes_com_arquivadas_status_e_ultimo_instante_do_dia(self):
        self.client.force_login(self.diretor)
        resposta = self.report()
        self.assertEqual(resposta.context['total_solicitacoes'], 23)
        self.assertEqual(resposta.context['total_arquivadas'], 22)
        self.assertEqual(resposta.context['ranking_data'][0]['total'], 23)
        self.assertEqual(self.report(status=['FINALIZADO', 'RECUSADO']).context['total_solicitacoes'], 25)
        self.assertEqual(self.report(status_filter_applied='1').context['total_solicitacoes'], 0)
        self.assertEqual(self.report(data_inicio='2026-11-01', data_fim='2026-11-30').context['total_solicitacoes'], 0)
        self.assertContains(resposta, '31/10/2026')

    def test_datas_invalidas_nao_usam_outro_periodo_silenciosamente(self):
        self.client.force_login(self.diretor)
        for params in ({'data_inicio': 'invalida'}, {'data_inicio': '2026-11-01'}):
            resposta = self.report(**params)
            self.assertEqual(resposta.context['total_solicitacoes'], 0)
            self.assertContains(resposta, 'Informe um período válido')

    def test_graficos_ranking_e_total_fecham_com_mais_de_cinco_grupos(self):
        self.client.force_login(self.diretor)
        for i in range(7):
            lot = Lotacao.objects.create(nome_lotacao=f'Lotação {i}')
            autor = CustomUser.objects.create_user(username=f'autor{i}', cpf=f'{10000000000+i}', lotacao=lot)
            doc = TipoDocumento.objects.create(nome_documento=f'Doc {i}', definicao_formulario=[])
            sol = Solicitacao.objects.create(colaborador=autor, tipo_documento=doc, status='FINALIZADO')
            Solicitacao.objects.filter(pk=sol.pk).update(data=self.data)
        context = self.report().context
        self.assertEqual(context['total_solicitacoes'], 30)
        self.assertEqual(sum(context['chart_docs_data']), 30)
        self.assertEqual(sum(context['chart_lot_data']), 30)
        self.assertEqual(sum(item['total'] for item in context['ranking_data']), 30)
        self.assertIn('Outros', context['chart_docs_labels'])

    def test_gestor_nao_obtem_dados_fora_da_hierarquia_no_relatorio(self):
        externo = CustomUser.objects.create_user(username='externo', cpf='00000000272',
            lotacao=Lotacao.objects.create(nome_lotacao='Externa'))
        sol = Solicitacao.objects.create(colaborador=externo, tipo_documento=self.doc, status='FINALIZADO')
        Solicitacao.objects.filter(pk=sol.pk).update(data=self.data)
        self.client.force_login(self.gestor)
        self.assertEqual(self.report().context['total_solicitacoes'], 23)

    def test_controle_apenas_dp_tic_direcao_e_filtros_aplicados_no_servidor(self):
        for user, namespace in ((self.dp, 'administracao'), (self.tic, 'administracao'),
                                (self.diretor, 'gestor'), (self.colab, 'colaborador'), (self.gestor, 'gestor')):
            self.client.force_login(user)
            permitido = user in (self.dp, self.tic, self.diretor)
            for condicao, expected in (('ocultar', 1), ('incluir', 25), ('somente', 24), ('invalida', 1)):
                response = self.client.get(reverse(f'{namespace}:solicitacoes'), {
                    'arquivadas': condicao, 'sort': 'data', 'q': 'Documento',
                }, headers={'HX-Request': 'true'})
                self.assertEqual(response.status_code, 200)
                lista = response.context['solicitacoes']
                total = lista.paginator.count if hasattr(lista, 'paginator') else lista.count()
                self.assertEqual(total, expected if permitido else 1, (user.username, condicao))
                if permitido:
                    self.assertContains(response, 'name="arquivadas"')
                    self.assertContains(response, 'há mais de 30 dias')
                else:
                    self.assertNotContains(response, 'name="arquivadas"')
            response = self.client.get(reverse(f'{namespace}:solicitacoes'), headers={'HX-Request': 'true'})
            self.assertFalse(any(s.arquivado for s in response.context['solicitacoes']))

    def test_paginacao_preserva_condicao_e_busca(self):
        self.client.force_login(self.dp)
        response = self.client.get(reverse('administracao:solicitacoes'), {
            'arquivadas': 'somente', 'q': 'Documento', 'sort': 'data', 'page': '2',
        }, headers={'HX-Request': 'true'})
        self.assertEqual(len(response.context['solicitacoes']), 9)
        self.assertIn('arquivadas=somente', response.context['url_params'])
        self.assertContains(response, 'Arquivada')

    def test_horas_so_de_finalizadas_e_avisos_sem_perder_volume(self):
        self.client.force_login(self.diretor)
        doc = TipoDocumento.objects.create(nome_documento='Hora Extra', definicao_formulario=[])
        for status, valor, arquivado in (('FINALIZADO', '25:30', True), ('RECUSADO', '10:00', False),
                                         ('FINALIZADO', '01:99', False)):
            sol = Solicitacao.objects.create(colaborador=self.colab, tipo_documento=doc,
                status=status, arquivado=arquivado, dados_preenchidos={
                    'schema': [{'name': 'total_geral_horas', 'type': 'calculated', 'calc_format': 'time'}],
                    'values': {'total_geral_horas': valor},
                })
            Solicitacao.objects.filter(pk=sol.pk).update(data=self.data)
        response = self.report(status=['FINALIZADO', 'RECUSADO'])
        self.assertEqual(response.context['total_solicitacoes'], 28)
        self.assertEqual(response.context['horas_extras'], '25:30')
        self.assertEqual(response.context['avisos_horas'], [sol.pk])
        self.assertContains(response, f'Revisar códigos: {sol.pk}')

    def test_mobile_controle_restrito_e_escopo_pessoal_preservado(self):
        for user in (self.colab, self.dp, self.tic, self.diretor):
            sol = Solicitacao.objects.create(colaborador=user, tipo_documento=self.doc,
                status='FINALIZADO', arquivado=True)
            self.client.force_login(user)
            response = self.client.get(reverse('mobile:home'), {'arquivadas': 'somente', 'q': 'Documento'},
                                       headers={'HX-Request': 'true'})
            self.assertEqual(response.status_code, 200)
            if user == self.colab:
                self.assertNotContains(response, 'name="arquivadas"')
                self.assertFalse(any(s.arquivado for s in response.context['solicitacoes_totais']))
            else:
                self.assertContains(response, 'name="arquivadas"')
                self.assertEqual(list(response.context['solicitacoes_totais']), [sol])
