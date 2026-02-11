import copy
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q
from django.urls import reverse
from django.http import HttpResponse
from django.db.models import Count
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model

from core.services import importar_dados

from .models import Cargo, Solicitacao, TipoDocumento, CustomUser, Lotacao
from .decorators import dp_required
from .forms import CustomUserForm, EditCustomUserForm, LotacaoForm, CargoForm, TipoDocumentoForm

User = get_user_model()

@dp_required
def dp_dashboard_view(request):
    user = request.user
    is_gestor_dp = (user.groups.filter(name='DP').exists() and (user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.GERENTE or user.cargo.hierarquia == Cargo.HierarquiaChoices.COORDENADOR)) if user.cargo else False

    q_minhas_lotacoes = Lotacao.objects.filter(
        Q(chefia=user) |
        (
            Q(chefia__isnull=True) &
            Q(chefia_secundaria=user)
        )
    )

    minhas_lotacoes = set(q_minhas_lotacoes)

    for lotacao in q_minhas_lotacoes:
        descendentes = lotacao.get_descendentes(include_self=True)
        minhas_lotacoes.update(descendentes)
        
    minha_equipe = CustomUser.objects.filter(
        lotacao__in=minhas_lotacoes,
        is_active=True
    ).exclude(id=user.id)

    q_pendencias_dp = Q(status__in=[Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO])
    
    if is_gestor_dp:
        q_pendencias_dp = q_pendencias_dp | Q(colaborador__in=minha_equipe, status=Solicitacao.StatusChoices.PENDENTE_GESTOR)

    pendencias_comigo = Solicitacao.objects.filter(
        status__in=[Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO]
    ).count()

    pendencias_direcao = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_DIRETOR
    ).count()

    fluxo_total = Solicitacao.objects.filter(
        status__in=[Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
                    Solicitacao.StatusChoices.PENDENTE_GESTOR,
                    Solicitacao.StatusChoices.PENDENTE_DIRETOR,
                    Solicitacao.StatusChoices.PENDENTE_DP,
                    Solicitacao.StatusChoices.LANCAMENTO],
    ).count()

    solicitacoes_pendentes = []

    if user.groups.filter(name='DP').exists():
        solicitacoes_pendentes = Solicitacao.objects.filter(
            status__in=[Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO]
        )
        
        if is_gestor_dp:
            solicitacoes_pendentes = solicitacoes_pendentes | Solicitacao.objects.filter(
                status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
                aprovador_atual=user
            )
    
    if user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        solicitacoes_pendentes = Solicitacao.objects.filter(
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
            aprovador_atual=user
        ) | Solicitacao.objects.filter(
            status=Solicitacao.StatusChoices.PENDENTE_DIRETOR
        )
    
    solicitacoes_pendentes = list(solicitacoes_pendentes.distinct().order_by('-data'))

    ranking_query_docs = Solicitacao.objects.values('tipo_documento__nome_documento') \
        .annotate(total=Count('id')) \
        .order_by('-total')

    ranking_query_setores = Solicitacao.objects.values('colaborador__lotacao__nome_lotacao') \
        .annotate(total=Count('id')) \
        .order_by('-total')

    ranking_labels_docs = [item['tipo_documento__nome_documento'] for item in ranking_query_docs]
    ranking_data_docs = [item['total'] for item in ranking_query_docs]

    ranking_labels_setores = [item['colaborador__lotacao__nome_lotacao'] for item in ranking_query_setores]
    ranking_data_setores = [item['total'] for item in ranking_query_setores]

    context = {
        'usuario': user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'is_dp': True,
        'is_aprovador': True,
        'kpi_pendencias': pendencias_comigo,
        'kpi_direcao': pendencias_direcao,
        'kpi_fluxo': fluxo_total,
        'distribuicao_tipos': ranking_query_docs,
        'distribuicao_setores': ranking_query_setores,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'ranking_labels_docs': ranking_labels_docs,
        'ranking_data_docs': ranking_data_docs,
        'ranking_labels_setores': ranking_labels_setores,
        'ranking_data_setores': ranking_data_setores,
        'active_link': 'dashboard',
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_dashboard.html', context)

    return render(request, 'painel/dp/dashboard.html', context)

@dp_required
def dp_lotacoes_view(request):
    search_query = request.GET.get('q')
    
    qs = Lotacao.objects.filter(arquivado=False)

    if search_query:
        qs = qs.filter(nome_lotacao__icontains=search_query).order_by('nome_lotacao')
        
        roots = list(qs)
        for lot in roots:
            lot.sub_lotacoes = []
            
    else:
        all_lotacoes = qs.select_related('chefia', 'lotacao_pai').order_by('nome_lotacao')
        lotacao_dict = {lot.id: lot for lot in all_lotacoes}
        
        for lot in all_lotacoes:
            lot.sub_lotacoes = []

        roots = []
        for lot in all_lotacoes:
            if lot.lotacao_pai_id:
                parent = lotacao_dict.get(lot.lotacao_pai_id)
                if parent:
                    parent.sub_lotacoes.append(lot)
                else:
                    roots.append(lot)
            else:
                roots.append(lot)

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'lotacoes': roots,
        'active_link': 'lotacoes',
        'search_query': search_query,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_lotacoes.html', context)
    
    return render(request, 'painel/dp/lotacoes.html', context)

@dp_required
def create_lotacao_modal_view(request):
    form = LotacaoForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Lotação criada com sucesso!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Nova Lotação',
        'action_url': reverse('administracao:create_lotacao'),
        'submit_text': 'Salvar Lotação',
    })

@dp_required
def edit_lotacao_modal_view(request, lotacao_id):
    lotacao = get_object_or_404(Lotacao, id=lotacao_id)
    form = LotacaoForm(request.POST or None, instance=lotacao)

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Lotação atualizada com sucesso!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': f'Editar Lotação: {lotacao.nome_lotacao}',
        'action_url': reverse('administracao:edit_lotacao', args=[lotacao.id]),
        'submit_text': 'Salvar Alterações',
    })

@dp_required
def archive_lotacao_modal_view(request, pk):
    lotacao = get_object_or_404(Lotacao, pk=pk)
    
    if request.method == 'POST':
        lotacao.arquivado = True
        lotacao.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Lotação arquivada!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Arquivar Lotação',
        'message': f"Deseja arquivar a lotação <strong>{lotacao.nome_lotacao}</strong>?",
        'action_url': reverse('administracao:archive_lotacao', args=[pk]),
        'submit_text': 'Arquivar',
        'color': 'orange',
        'icon_name': 'archive'
    })

@dp_required
def delete_lotacao_view(request, pk):
    lotacao = get_object_or_404(Lotacao, pk=pk)
    
    if request.method == 'POST':
        try:
            lotacao.delete()
            response = render(request, 'partials/_message_sucess.html', {'message': "Lotação excluída!"})
            response['HX-Trigger'] = 'updateContent'
            return response
        except Exception:
            return render(request, 'partials/_message_error.html', {'message': "Erro: Existem registros vinculados."})

    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Excluir Lotação',
        'message': f"Excluir permanentemente <strong>{lotacao.nome_lotacao}</strong>?",
        'action_url': reverse('administracao:delete_lotacao', args=[pk]),
        'submit_text': 'Excluir',
        'color': 'red',
        'icon_name': 'trash'
    })

@dp_required
def dp_cargos_view(request):
    search_query = request.GET.get('q')
    
    cargos = Cargo.objects.filter(arquivado=False).order_by('hierarquia', 'nome_cargo')
    
    if search_query:
        cargos = cargos.filter(nome_cargo__icontains=search_query)
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'cargos': cargos,
        'active_link': 'cargos',
        'search_query': search_query,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_cargos.html', context)
    
    return render(request, 'painel/dp/cargos.html', context)

@dp_required
def create_cargo_modal_view(request):
    form = CargoForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Cargo criado com sucesso!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Novo Cargo',
        'action_url': reverse('administracao:create_cargo'),
        'submit_text': 'Salvar Cargo',
    })

@dp_required
def edit_cargo_modal_view(request, pk):
    cargo = get_object_or_404(Cargo, pk=pk)
    form = CargoForm(request.POST or None, instance=cargo)
    
    if request.method == 'POST' and form.is_valid():
        form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Cargo atualizado com sucesso!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': f'Editar {cargo.nome_cargo}',
        'action_url': reverse('administracao:edit_cargo', args=[pk]),
        'submit_text': 'Salvar Alterações',
    })

@dp_required
def archive_cargo_modal_view(request, pk):
    cargo = get_object_or_404(Cargo, pk=pk)
    
    if request.method == 'POST':
        cargo.arquivado = True
        cargo.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Cargo <strong>{cargo.nome_cargo}</strong> arquivado!"})
        response['HX-Trigger'] = 'updateContent'
        return response
    
    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Arquivar Cargo',
        'message': f"Deseja arquivar o cargo <strong>{cargo.nome_cargo}</strong>?",
        'action_url': reverse('administracao:archive_cargo', args=[pk]),
        'submit_text': 'Arquivar',
        'color': 'orange',
        'icon_name': 'archive'
    })

@dp_required
def delete_cargo_view(request, pk):
    cargo = get_object_or_404(Cargo, pk=pk)
    
    if request.method == 'POST':
        try:
            nome = cargo.nome_cargo
            cargo.delete()
            response = render(request, 'partials/_message_sucess.html', {'message': f"Cargo <strong>{nome}</strong> excluído permanentemente!"})
            response['HX-Trigger'] = 'updateContent'
            return response
        except Exception:
            return render(request, 'partials/_message_error.html', {'message': "Não é possível excluir este cargo pois existem colaboradores vinculados."})
    
    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Excluir Cargo',
        'message': f"Deseja excluir permanentemente o cargo <strong>{cargo.nome_cargo}</strong>?",
        'action_url': reverse('administracao:delete_cargo', args=[pk]),
        'submit_text': 'Excluir',
        'color': 'red',
        'icon_name': 'trash'
    })

@dp_required
def dp_colaboradores_view(request):

    exclude_colaboradores = (Q(is_active=False) | Q(username='admin') | Q(matricula='000000'))

    search_query = request.GET.get('q', '')
    page_number = request.GET.get('page')

    colaboradores = CustomUser.objects.filter(is_active=True).exclude(exclude_colaboradores).order_by('first_name')

    if search_query:
        colaboradores = colaboradores.filter(
            Q(first_name__icontains=search_query) | 
            Q(matricula__icontains=search_query) |
            Q(email__icontains=search_query)
        )
    
    paginator = Paginator(colaboradores, 15)
    page_obj = paginator.get_page(page_number)

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'colaboradores': page_obj,
        'active_link': 'colaboradores',
        'search_query': search_query,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_colaboradores.html', context)
    
    return render(request, 'painel/dp/colaboradores.html', context)

@dp_required
def create_colaborador_modal_view(request):
    form = CustomUserForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        colaborador = form.save(commit=False)
        colaborador.username = colaborador.matricula
        colaborador.set_password('Mudar@123') 
        colaborador.save()
        form.save_m2m()
        
        response = render(request, 'partials/_message_sucess.html', {'message': f"Colaborador cadastrado!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Novo Colaborador',
        'action_url': reverse('administracao:create_colaborador'),
        'submit_text': 'Cadastrar Colaborador',
    })

@dp_required
def edit_colaborador_modal_view(request, pk):
    colaborador = get_object_or_404(CustomUser, pk=pk)
    form = EditCustomUserForm(request.POST or None, instance=colaborador)
    
    if request.method == 'POST' and form.is_valid():
        form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Colaborador atualizado!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': f'Editar {colaborador.first_name}',
        'action_url': reverse('administracao:edit_colaborador', args=[pk]),
        'submit_text': 'Salvar Alterações',
    })

@dp_required
def archive_colaborador_modal_view(request, pk):
    colaborador = get_object_or_404(CustomUser, pk=pk)
    
    if request.method == 'POST':
        colaborador.arquivado = True
        colaborador.is_active = False
        colaborador.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Colaborador arquivado!"})
        response['HX-Trigger'] = 'updateContent'
        return response
        
    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Arquivar Colaborador',
        'message': f"Deseja arquivar <strong>{colaborador.get_full_name()}</strong>?",
        'action_url': reverse('administracao:archive_colaborador', args=[pk]),
        'submit_text': 'Arquivar',
        'color': 'orange',
        'icon_name': 'archive'
    })

@dp_required
def delete_colaborador_view(request, pk):
    colaborador = get_object_or_404(CustomUser, pk=pk)
    
    if request.method == 'POST':
        nome = colaborador.get_full_name()
        colaborador.delete()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Colaborador <strong>{nome}</strong> excluído!"})
        response['HX-Trigger'] = 'updateContent'
        return response
        
    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Excluir Colaborador',
        'message': f"Excluir permanentemente <strong>{colaborador.get_full_name()}</strong>?",
        'action_url': reverse('administracao:delete_colaborador', args=[pk]),
        'submit_text': 'Excluir',
        'color': 'red',
        'icon_name': 'trash'
    })

@dp_required
def dp_documentos_view(request):
    search_query = request.GET.get('q')
    
    documentos = TipoDocumento.objects.filter(arquivado=False).order_by('nome_documento')
    
    if search_query:
        documentos = documentos.filter(nome_documento__icontains=search_query)
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'documentos': documentos,
        'active_link': 'documentos',
        'search_query': search_query,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_documentos.html', context)
    
    return render(request, 'painel/dp/documentos.html', context)

@dp_required
def visualize_documento_view(request, pk):
    tipo_doc = get_object_or_404(TipoDocumento, id=pk)
    
    try:
        campos_json = copy.deepcopy(tipo_doc.definicao_formulario)
    
        for campo in campos_json:
            source = campo.get("options_source")
            
            if source == "colaboradores_lotacao":

                users = User.objects.filter(
                    lotacao=request.user.lotacao,
                    is_active=True
                ).exclude(id=request.user.id).order_by('first_name')

                campo['options'] = [
                    {'value': str(u.id), 'label': f"{u.first_name}"}
                    for u in users
                ]
                
        context = {
            'tipo_documento': tipo_doc,
            'campos_formulario': campos_json,
            'active_link': 'documentos',
        }
        
        return render(request, 'partials/_visualize_documento.html', context)
    
    except Exception as e:
        url_retry = reverse('colaborador:get_create_solicitacao_form', args=[pk])
        
        return render(request, 'partials/_message_error.html', {
            'message': f'Erro ao carregar o formulário: {e}',
            'url_retry': url_retry
        })

@dp_required
def create_documento_modal_view(request):
    form = TipoDocumentoForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Documento criado com sucesso!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Novo Documento',
        'action_url': reverse('administracao:create_documento'),
        'submit_text': 'Salvar Documento',
    })

@dp_required
def edit_documento_modal_view(request, pk):
    documento = get_object_or_404(TipoDocumento, pk=pk)
    form = TipoDocumentoForm(request.POST or None, instance=documento)
    
    if request.method == 'POST' and form.is_valid():
        form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Documento atualizado com sucesso!"})
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': f'Editar {documento.nome_documento}',
        'action_url': reverse('administracao:edit_documento', args=[pk]),
        'submit_text': 'Salvar Alterações',
    })

@dp_required
def archive_documento_modal_view(request, pk):
    documento = get_object_or_404(TipoDocumento, pk=pk)
    
    if request.method == 'POST':
        documento.arquivado = True
        documento.save()
        response = render(request, 'partials/_message_sucess.html', {'message': f"Documento arquivado!"})
        response['HX-Trigger'] = 'updateContent'
        return response
    
    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Arquivar Documento',
        'message': f"Deseja arquivar o documento <strong>{documento.nome_documento}</strong>?",
        'action_url': reverse('administracao:archive_documento', args=[pk]),
        'submit_text': 'Arquivar',
        'color': 'orange',
        'icon_name': 'archive'
    })

@dp_required
def delete_documento_view(request, pk):
    documento = get_object_or_404(TipoDocumento, pk=pk)
    
    if request.method == 'POST':
        try:
            nome = documento.nome_documento
            documento.delete()
            response = render(request, 'partials/_message_sucess.html', {'message': f"Documento <strong>{nome}</strong> excluído!"})
            response['HX-Trigger'] = 'updateContent'
            return response
        except Exception:
            return render(request, 'partials/_message_error.html', {'message': "Existem solicitações vinculadas."})
    
    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Excluir Documento',
        'message': f"ATENÇÃO: Deseja excluir permanentemente <strong>{documento.nome_documento}</strong>?",
        'action_url': reverse('administracao:delete_documento', args=[pk]),
        'submit_text': 'Excluir',
        'color': 'red',
        'icon_name': 'trash'
    })

@dp_required
def dp_solicitacoes_view(request):
    search_query = request.GET.get('q', '')
    page_number = request.GET.get('page')

    solicitacoes_list = Solicitacao.objects.all().order_by('-data')

    if search_query:
        solicitacoes_list = solicitacoes_list.filter(
            Q(id__icontains=search_query) |
            Q(colaborador__first_name__icontains=search_query) |
            Q(tipo_documento__nome_documento__icontains=search_query)
        )
    
    paginator = Paginator(solicitacoes_list, 15)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'is_dp': True,
        'solicitacoes': page_obj,
        'num_pages': paginator.num_pages,
        'active_link': 'solicitacoes',
        'search_query': search_query,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_solicitacoes.html', context)
    
    return render(request, 'painel/dp/solicitacoes.html', context)

@dp_required
def import_data_modal_view(request, tipo_dado):
    config = {
        'colaboradores': {'titulo': 'Importar Colaboradores', 'url': reverse('administracao:import_data', args=['colaboradores'])},
        'lotacoes': {'titulo': 'Importar Lotações', 'url': reverse('administracao:import_data', args=['lotacoes'])},
        'cargos': {'titulo': 'Importar Cargos', 'url': reverse('administracao:import_data', args=['cargos'])},
    }

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo')
        
        if not arquivo:
            return render(request, 'partials/_message_error.html', {'message': "Nenhum arquivo selecionado."})

        mapa = {}
        campo_chave = []
        model = None
        
        try:
            if tipo_dado == 'colaboradores':
                model = get_user_model()
                mapa = {
                    'Nome': 'first_name',
                    'Email': 'email',
                    'Matricula': 'matricula',
                    'CPF': 'cpf',
                    'Cargo': ('cargo', Cargo, 'nome_cargo'), 
                    'Lotacao': ('lotacao', Lotacao, 'nome_lotacao'),
                }
                campo_chave = ['cpf'] 

            elif tipo_dado == 'lotacoes':
                model = Lotacao
                mapa = {
                    'Nome': 'nome_lotacao',
                    'Pai': ('lotacao_pai', Lotacao, 'nome_lotacao') 
                }
                campo_chave = ['nome_lotacao']

            elif tipo_dado == 'cargos':
                model = Cargo
                mapa = {
                    'Nome': 'nome_cargo',
                    'Nivel': 'hierarquia' 
                }
                campo_chave = ['nome_cargo']
            
            resultado = importar_dados(
                arquivo_io=arquivo,
                nome_arquivo=arquivo.name,
                model_class=model,
                mapa_de_campos=mapa,
                campo_busca_fk=campo_chave
            )

            if resultado['sucesso'] > 0:
                msg = f"Sucesso! {resultado['sucesso']} registros processados."
                if resultado['erros']:
                    msg += f" (Com {len(resultado['erros'])} alertas)"
                
                response = render(request, 'partials/_message_sucess.html', {'message': msg})
                response['HX-Trigger'] = 'updateContent'
                return response
            else:
                erro_txt = resultado['erros'][0] if resultado['erros'] else "Erro desconhecido"
                return render(request, 'partials/_message_error.html', {'message': f"Falha: {erro_txt}"})

        except Exception as e:
            return render(request, 'partials/_message_error.html', {'message': f"Erro interno: {str(e)}"})

    ctx = config.get(tipo_dado)
    return render(request, 'partials/_import_form.html', {
        'modal_title': ctx['titulo'],
        'action_url': ctx['url']
    })