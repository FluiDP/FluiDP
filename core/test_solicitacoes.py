from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Cargo, CustomUser, Lotacao, Solicitacao, TipoDocumento


class ListingHTMLParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class SolicitacoesListagemTests(TestCase):
    fields = (
        'colaborador__first_name', 'colaborador__lotacao__nome_lotacao',
        'tipo_documento__nome_documento', 'data', 'status',
    )
    namespaces = ('colaborador', 'gestor', 'administracao')

    @classmethod
    def setUpTestData(cls):
        cargo = Cargo.objects.create(
            nome_cargo='Diretor', hierarquia=Cargo.HierarquiaChoices.DIRETOR,
        )
        cls.lotacoes = [Lotacao.objects.create(nome_lotacao=name) for name in ('Zulu', 'Alfa')]
        cls.usuario = CustomUser.objects.create_user(
            username='diretor_listagem', cpf='11122233396', cargo=cargo,
            lotacao=cls.lotacoes[0],
        )
        cls.usuario.groups.add(Group.objects.create(name='DP'))
        cls.colaboradores = [
            CustomUser.objects.create_user(
                username=f'colaborador_listagem_{i}', first_name=name,
                cpf=cpf, lotacao=cls.lotacoes[i],
            ) for i, (name, cpf) in enumerate((('Zulu', '52998224725'), ('Alfa', '12345678909')))
        ]
        cls.documentos = [
            TipoDocumento.objects.create(nome_documento=name, definicao_formulario=[])
            for name in ('Documento Zulu', 'Documento Alfa')
        ]
        cls.agora = timezone.now()
        for i in range(18):
            solicitacao = Solicitacao.objects.create(
                colaborador=cls.colaboradores[i % 2], colaborador_secundario=cls.usuario,
                tipo_documento=cls.documentos[(i // 2) % 2],
                status=Solicitacao.StatusChoices.FINALIZADO if i % 3 else Solicitacao.StatusChoices.CANCELADO,
            )
            Solicitacao.objects.filter(pk=solicitacao.pk).update(data=cls.agora - timedelta(days=i))

    def setUp(self):
        self.client.force_login(self.usuario)

    def get_listing(self, namespace, params=None, htmx=True):
        response = self.client.get(
            reverse(f'{namespace}:solicitacoes'), params or {},
            headers={'HX-Request': 'true'} if htmx else {},
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_todas_colunas_nos_dois_sentidos_antes_da_paginacao(self):
        for namespace in self.namespaces:
            for field in self.fields:
                for prefix in ('', '-'):
                    sort = prefix + field
                    with self.subTest(namespace=namespace, sort=sort):
                        response = self.get_listing(namespace, {'sort': sort})
                        expected = Solicitacao.objects.order_by(sort, 'pk')
                        if namespace != 'colaborador':
                            expected = expected[:15]
                        self.assertEqual(
                            [sol.pk for sol in response.context['solicitacoes']],
                            list(expected.values_list('pk', flat=True)),
                        )

    def test_busca_filtros_e_ordenacao_combinados(self):
        params = {
            'q': 'Documento', 'status': Solicitacao.StatusChoices.FINALIZADO,
            'documento': str(self.documentos[1].pk), 'lotacao': str(self.lotacoes[0].pk),
            'data_inicio': (self.agora - timedelta(days=12)).date().isoformat(),
            'data_fim': self.agora.date().isoformat(), 'sort': 'data',
        }
        for namespace in self.namespaces:
            with self.subTest(namespace=namespace):
                response = self.get_listing(namespace, params)
                expected = Solicitacao.objects.filter(
                    status=params['status'], tipo_documento=self.documentos[1],
                    data__date__gte=params['data_inicio'], data__date__lte=params['data_fim'],
                )
                if namespace != 'colaborador':
                    expected = expected.filter(colaborador__lotacao=self.lotacoes[0])
                self.assertTrue(expected.exists())
                self.assertEqual(
                    [sol.pk for sol in response.context['solicitacoes']],
                    list(expected.order_by('data', 'pk').values_list('pk', flat=True)),
                )

    def test_segunda_pagina_respeita_ordenacao_e_busca(self):
        for namespace in ('gestor', 'administracao'):
            response = self.get_listing(namespace, {'sort': 'data', 'page': '2', 'q': 'Documento'})
            self.assertEqual(response.context['solicitacoes'].number, 2)
            self.assertEqual(
                [sol.pk for sol in response.context['solicitacoes']],
                list(Solicitacao.objects.order_by('data', 'pk').values_list('pk', flat=True)[15:]),
            )

    def test_cabecalhos_alternam_sem_sobrescrever_sort_com_valor_do_formulario(self):
        for namespace in self.namespaces:
            for sort, expected_next in [('data', '-data'), ('-data', 'data')]:
                response = self.get_listing(namespace, {'sort': sort, 'q': 'Documento', 'page': '2'})
                elements = ListingHTMLParser(response.content.decode()).elements
                links = [attrs for tag, attrs in elements if tag == 'a' and attrs.get('title', '').startswith('Ordenar por ')]
                self.assertEqual(len(links), len(self.fields))
                next_sorts = []
                for attrs in links:
                    url = urlsplit(attrs['hx-get'])
                    self.assertEqual(url.path, reverse(f'{namespace}:solicitacoes'))
                    fallback_params = parse_qs(urlsplit(attrs['href']).query)
                    self.assertEqual(fallback_params['q'], ['Documento'])
                    self.assertEqual(attrs['hx-params'], 'not sort,page')
                    self.assertEqual(attrs['hx-include'], '#filter-form')
                    self.assertEqual(attrs['hx-target'], '#solicitacoes')
                    self.assertEqual(attrs['hx-swap'], 'outerHTML')
                    self.assertEqual(attrs['hx-push-url'], 'true')
                    params = parse_qs(url.query)
                    self.assertEqual(params['page'], ['2'])
                    self.assertEqual(set(params), {'sort', 'page'})
                    next_sorts.append(params['sort'][0])
                self.assertIn(expected_next, next_sorts)
                hidden_sort = [attrs for tag, attrs in elements if tag == 'input' and attrs.get('name') == 'sort']
                self.assertEqual(hidden_sort[0]['value'], sort)
                form = next(attrs for tag, attrs in elements if tag == 'form' and attrs.get('id') == 'filter-form')
                self.assertIn("input from:input[type='search'] delay:500ms", form['hx-trigger'])
                self.assertIn('updateContent from:body', form['hx-trigger'])

    def test_atualizacao_reflete_alteracoes_preservando_busca_e_sort(self):
        for namespace in self.namespaces:
            params = {'sort': 'data', 'q': 'Documento', 'status': Solicitacao.StatusChoices.FINALIZADO}
            before = self.get_listing(namespace, params)
            first = list(before.context['solicitacoes'])[0]
            Solicitacao.objects.filter(pk=first.pk).update(status=Solicitacao.StatusChoices.CANCELADO)
            after = self.get_listing(namespace, params)
            self.assertNotIn(first.pk, [sol.pk for sol in after.context['solicitacoes']])
            self.assertEqual(after.context['current_sort'], 'data')
            self.assertEqual(after.context['search_query'], 'Documento')

    def test_urls_dos_cabecalhos_reordenam_na_pagina_atual(self):
        for namespace in ('gestor', 'administracao'):
            initial = self.get_listing(namespace, {'page': '2', 'sort': '-data', 'q': 'Documento'})
            elements = ListingHTMLParser(initial.content.decode()).elements
            links = [attrs for tag, attrs in elements if tag == 'a' and attrs.get('title', '').startswith('Ordenar por ')]
            for attrs in links:
                with self.subTest(namespace=namespace, column=attrs['title']):
                    # Follow the rendered URL, including the same page and filters.
                    response = self.client.get(attrs['hx-get'], headers={'HX-Request': 'true'})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['solicitacoes'].number, 2)
                    sort = parse_qs(urlsplit(attrs['hx-get']).query)['sort'][0]
                    self.assertEqual(response.context['current_sort'], sort)
                    actual = [sol.pk for sol in response.context['solicitacoes']]
                    expected = list(Solicitacao.objects.order_by(sort, 'pk').values_list('pk', flat=True)[15:])
                    self.assertEqual(actual, expected)
                    if sort == 'data':
                        self.assertNotEqual(actual, [sol.pk for sol in initial.context['solicitacoes']])
                    # The normal link also works when HTMX is unavailable.
                    fallback = self.client.get(attrs['href'])
                    self.assertEqual(fallback.status_code, 200)
                    self.assertEqual(fallback.context['solicitacoes'].number, 2)
                    self.assertEqual(fallback.context['current_sort'], sort)

    def test_clique_usa_busca_e_filtros_atuais_do_formulario(self):
        for namespace in ('gestor', 'administracao'):
            initial = self.get_listing(namespace, {'page': '2', 'sort': '-data', 'q': 'Documento Zulu'})
            elements = ListingHTMLParser(initial.content.decode()).elements
            attrs = next(attrs for tag, attrs in elements if tag == 'a' and attrs.get('title') == 'Ordenar por Data')
            # HTMX appends the included inputs except sort/page, which belong to the clicked URL.
            live_params = {'q': 'Documento Alfa', 'documento': str(self.documentos[1].pk), 'status': ''}
            response = self.client.get(attrs['hx-get'] + '&' + urlencode(live_params), headers={'HX-Request': 'true'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['current_sort'], 'data')
            self.assertEqual(response.context['search_query'], 'Documento Alfa')
            self.assertTrue(response.context['solicitacoes'])
            for sol in response.context['solicitacoes']:
                self.assertEqual(sol.tipo_documento_id, self.documentos[1].pk)

    def test_sort_invalido_volta_ao_padrao(self):
        for namespace in self.namespaces:
            response = self.get_listing(namespace, {'sort': 'campo_inexistente'})
            self.assertEqual(response.context['current_sort'], '-data')

    def test_colaborador_preserva_escopo_das_solicitacoes(self):
        fora_do_escopo = Solicitacao.objects.create(
            colaborador=self.colaboradores[0], tipo_documento=self.documentos[0],
        )
        response = self.get_listing('colaborador', {'sort': 'data'})
        self.assertNotIn(fora_do_escopo, response.context['solicitacoes'])

    def test_gestor_preserva_escopo_da_lotacao(self):
        cargo = Cargo.objects.create(nome_cargo='Gerente', hierarquia=Cargo.HierarquiaChoices.GERENTE)
        self.usuario.cargo = cargo
        self.usuario.save(update_fields=['cargo'])
        response = self.get_listing('gestor', {'sort': 'data'})
        self.assertTrue(response.context['solicitacoes'])
        for sol in response.context['solicitacoes']:
            self.assertEqual(sol.colaborador.lotacao_id, self.lotacoes[0].pk)

    def test_renderizacao_completa_e_parcial(self):
        for namespace in self.namespaces:
            self.get_listing(namespace, {'sort': 'status'}, htmx=False)
            self.get_listing(namespace, {'sort': 'status'}, htmx=True)
