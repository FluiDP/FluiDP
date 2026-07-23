import copy
import uuid
from django.core.cache import cache, caches
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q, Count
from django.urls import reverse
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from django.utils.safestring import mark_safe

from django.core.files.storage import default_storage
from django_q.tasks import async_task

from .services import obter_pendencias_do_usuario, registrar_log_acao
from .models import Cargo, Solicitacao, TipoDocumento, CustomUser, Lotacao
from .decorators import dp_required
from .forms import CustomUserForm, EditCustomUserForm, LotacaoForm, CargoForm, TipoDocumentoForm
from core import services

User = get_user_model()

# ==========================================
# DASHBOARD
# ==========================================

@dp_required
def dp_dashboard_view(request):
    user = request.user

    solicitacoes = services.obter_pendencias_do_usuario(user)

    dp_pendencias = Solicitacao.objects.filter(
        status__in=[
            Solicitacao.StatusChoices.PENDENTE_DP,
            Solicitacao.StatusChoices.LANCAMENTO
            ]
        )
    
    # --- 2. KPIs ---
    kpi_pendencias_dp = dp_pendencias.count()

    kpi_direcao = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_DIRETOR
    ).count()

    kpi_fluxo = Solicitacao.objects.filter(
        status__in=[
            Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
            Solicitacao.StatusChoices.PENDENTE_GESTOR,
            Solicitacao.StatusChoices.PENDENTE_DIRETOR,
            Solicitacao.StatusChoices.PENDENTE_DP,
            Solicitacao.StatusChoices.LANCAMENTO
        ]
    ).count()

    # --- 3. GRÁFICOS E RANKINGS ---
    # Documentos (Geral)
    ranking_query_docs = Solicitacao.objects.values('tipo_documento__nome_documento') \
        .annotate(total=Count('id')) \
        .order_by('-total')

    ranking_labels_docs = [item['tipo_documento__nome_documento'] for item in ranking_query_docs]
    ranking_data_docs = [item['total'] for item in ranking_query_docs]

    # Setores (Top 5 conforme pedido no template)
    ranking_query_setores = Solicitacao.objects.values('colaborador__lotacao__nome_lotacao') \
        .annotate(total=Count('id')) \
        .order_by('-total')[:5]

    ranking_labels_setores = [item['colaborador__lotacao__nome_lotacao'] for item in ranking_query_setores]
    ranking_data_setores = [item['total'] for item in ranking_query_setores]

    # --- 4. CONTEXTO ---
    context = {
        'usuario': user,
        'usuario_tagname': user.first_name.split()[0] if user.first_name else user.username,
        'is_dp': user.groups.filter(name='DP').exists(),
        'is_tic': user.groups.filter(name='SYSTEM_ADMIN').exists(),
        
        # KPIs
        'kpi_pendencias': kpi_pendencias_dp,
        'kpi_direcao': kpi_direcao,
        'kpi_fluxo': kpi_fluxo,
        
        # Tabela
        'solicitacoes': solicitacoes,
        
        # Gráficos
        'distribuicao_tipos': bool(ranking_query_docs),
        'ranking_labels_docs': ranking_labels_docs,
        'ranking_data_docs': ranking_data_docs,
        
        'distribuicao_setores': bool(ranking_query_setores),
        'ranking_labels_setores': ranking_labels_setores,
        'ranking_data_setores': ranking_data_setores,
        
        'active_link': 'dashboard',
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_dashboard.html', context)

    return render(request, 'painel/dp/dashboard.html', context)


# ==========================================
# LOTAÇÕES
# ==========================================

@dp_required
def dp_lotacoes_view(request):
    search_query = request.GET.get('q')
    
    # Adicionado suporte a ordenação efetiva no front-end para Lotações
    sort_param = request.GET.get('sort', 'nome_lotacao')
    campos_permitidos = ['nome_lotacao', '-nome_lotacao']
    if sort_param not in campos_permitidos:
        sort_param = 'nome_lotacao'
    
    qs = Lotacao.objects.filter(arquivado=False)

    if search_query:
        qs = qs.filter(nome_lotacao__icontains=search_query).order_by(sort_param)
        
        roots = list(qs)
        for lot in roots:
            lot.sub_lotacoes = []
            
    else:
        all_lotacoes = qs.select_related('chefia', 'lotacao_pai').order_by(sort_param)
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
        'current_sort': sort_param,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_lotacoes.html', context)
    
    return render(request, 'painel/dp/lotacoes.html', context)

@dp_required
def create_lotacao_modal_view(request):
    form = LotacaoForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': "Lotação criada com sucesso!"})
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
        form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': "Lotação atualizada com sucesso!"})
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
        response = render(request, 'partials/_message_sucess.html', {'message': "Lotação arquivada!"})
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


# ==========================================
# CARGOS
# ==========================================

@dp_required
def dp_cargos_view(request):
    search_query = request.GET.get('q')
    cargos = Cargo.objects.filter(arquivado=False)
    
    if search_query:
        cargos = cargos.filter(nome_cargo__icontains=search_query)

    sort_param = request.GET.get('sort', 'hierarquia')
    campos_permitidos = ['nome_cargo', '-nome_cargo', 'hierarquia', '-hierarquia']
    
    if sort_param not in campos_permitidos:
        sort_param = 'hierarquia'

    # Ordenação executada corretamente antes da montagem do contexto
    cargos = cargos.order_by(sort_param, 'nome_cargo')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'cargos': cargos,
        'active_link': 'cargos',
        'search_query': search_query,
        'current_sort': sort_param,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_cargos.html', context)
    
    return render(request, 'painel/dp/cargos.html', context)

@dp_required
def create_cargo_modal_view(request):
    form = CargoForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': "Cargo criado com sucesso!"})
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
        response = render(request, 'partials/_message_sucess.html', {'message': "Cargo atualizado com sucesso!"})
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


# ==========================================
# COLABORADORES
# ==========================================

@dp_required
def dp_colaboradores_view(request):
    exclude_colaboradores = (Q(is_active=False) | Q(username='admin') | Q(matricula='000000'))

    search_query = request.GET.get('q', '')
    page_number = request.GET.get('page')

    colaboradores = CustomUser.objects.filter(is_active=True).exclude(exclude_colaboradores)

    if search_query:
        colaboradores = colaboradores.filter(
            Q(first_name__icontains=search_query) | 
            Q(matricula__icontains=search_query) |
            Q(email__icontains=search_query)
        )
        
    sort_param = request.GET.get('sort', 'first_name')
    campos_permitidos = ['first_name', '-first_name', 'matricula', '-matricula', 'lotacao__nome_lotacao', '-lotacao__nome_lotacao']
    
    if sort_param not in campos_permitidos:
        sort_param = 'first_name'

    # CORREÇÃO: A ordenação deve vir ANTES da paginação!
    colaboradores = colaboradores.order_by(sort_param)

    paginator = Paginator(colaboradores, 15)
    page_obj = paginator.get_page(page_number)

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'colaboradores': page_obj,
        'active_link': 'colaboradores',
        'search_query': search_query,
        'current_sort': sort_param,
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
        colaborador.precisa_trocar_senha = True
        colaborador.save()
        form.save_m2m()
        
        form.save_groups(colaborador)
        
        response = render(request, 'partials/_message_sucess.html', {'message': "Colaborador cadastrado!"})
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
        response = render(request, 'partials/_message_sucess.html', {'message': "Colaborador atualizado!"})
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
        response = render(request, 'partials/_message_sucess.html', {'message': "Colaborador arquivado!"})
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


# ==========================================
# TIPOS DE DOCUMENTO
# ==========================================

@dp_required
def dp_documentos_view(request):
    search_query = request.GET.get('q')
    documentos = TipoDocumento.objects.filter(arquivado=False)
    
    if search_query:
        documentos = documentos.filter(nome_documento__icontains=search_query)

    sort_param = request.GET.get('sort', 'nome_documento')
    campos_permitidos = ['nome_documento', '-nome_documento']
    
    if sort_param not in campos_permitidos:
        sort_param = 'nome_documento'

    documentos = documentos.order_by(sort_param)

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'documentos': documentos,
        'active_link': 'documentos',
        'search_query': search_query,
        'current_sort': sort_param,
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
        form.save()
        response = render(request, 'partials/_message_sucess.html', {'message': "Documento criado com sucesso!"})
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
        response = render(request, 'partials/_message_sucess.html', {'message': "Documento atualizado com sucesso!"})
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
        response = render(request, 'partials/_message_sucess.html', {'message': "Documento arquivado!"})
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


# ==========================================
# SOLICITAÇÕES
# ==========================================

@dp_required
def dp_solicitacoes_view(request):
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    documento_filter = request.GET.get('documento', '')
    lotacao_filter = request.GET.get('lotacao', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    page_number = request.GET.get('page')

    solicitacoes_list = Solicitacao.objects.all()

    if search_query:
        solicitacoes_list = solicitacoes_list.filter(
            Q(id__icontains=search_query) |
            Q(colaborador__first_name__icontains=search_query) |
            Q(tipo_documento__nome_documento__icontains=search_query)
        )
    
    if status_filter:
        solicitacoes_list = solicitacoes_list.filter(status=status_filter)
        
    if documento_filter:
        solicitacoes_list = solicitacoes_list.filter(tipo_documento_id=documento_filter)

    if lotacao_filter:
        solicitacoes_list = solicitacoes_list.filter(colaborador__lotacao_id=lotacao_filter)

    if data_inicio:
        solicitacoes_list = solicitacoes_list.filter(data__date__gte=data_inicio)
        
    if data_fim:
        solicitacoes_list = solicitacoes_list.filter(data__date__lte=data_fim)

    sort_param = request.GET.get('sort', '-data')
    campos_permitidos = [
        'data', '-data', 
        'colaborador__first_name', '-colaborador__first_name',
        'tipo_documento__nome_documento', '-tipo_documento__nome_documento',
        'status', '-status',
        'colaborador__lotacao__nome_lotacao', '-colaborador__lotacao__nome_lotacao'
    ]
    
    if sort_param not in campos_permitidos:
        sort_param = '-data'

    solicitacoes_list = solicitacoes_list.order_by(sort_param)

    paginator = Paginator(solicitacoes_list, 15)
    page_obj = paginator.get_page(page_number)
    
    tipos_documento = TipoDocumento.objects.filter(arquivado=False).order_by('nome_documento')
    lotacoes = Lotacao.objects.filter(arquivado=False).order_by('nome_lotacao')
    status_choices = Solicitacao.StatusChoices.choices

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    
    url_params = f"&{query_params.urlencode()}" if query_params else ""

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'is_dp': True,
        'solicitacoes': page_obj,
        'num_pages': paginator.num_pages,
        'active_link': 'solicitacoes',
        'search_query': search_query,
        'status_filter': status_filter,
        'documento_filter': documento_filter,
        'lotacao_filter': lotacao_filter,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'tipos_documento': tipos_documento,
        'lotacoes': lotacoes,
        'status_choices': status_choices,
        'url_params': url_params,
        'current_sort': sort_param,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_solicitacoes.html', context)
    
    return render(request, 'painel/dp/solicitacoes.html', context)

@dp_required
def dp_edit_solicitacao_modal_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    
    if not solicitacao.can_edit_dp(request.user):
        return render(request, 'partials/_message_error.html', {
            'message': 'Você não tem permissão para editar esta solicitação.'
        })

    tipo_doc = solicitacao.tipo_documento
    schema = solicitacao.dados_preenchidos.get('schema', tipo_doc.definicao_formulario)

    if request.method == 'POST':
        novos_valores = solicitacao.dados_preenchidos.get('values', {})
        for campo in schema:
            if campo.get('type') == 'calculated':
                nome_campo = campo.get('name')
                if nome_campo in request.POST:
                    novos_valores[nome_campo] = request.POST.get(nome_campo)

        try:
            services.editar_solicitacao(
                solicitacao=solicitacao,
                ator=request.user,
                novos_valores=novos_valores
            )
            msg = mark_safe('Campos calculados <span class="font-bold">atualizados</span> pelo DP.')
            response = render(request, 'partials/_message_sucess.html', {'message': msg})
            response['HX-Trigger'] = 'updateContent'
            return response
        except ValidationError as ve:
            return render(request, 'partials/_message_error.html', {'message': str(ve)})
        except Exception as e:
            return render(request, 'partials/_message_error.html', {'message': f'Erro ao editar: {e}'})

    dados_valores = solicitacao.dados_preenchidos.get('values', {})
    campos_exclusivos_dp = []
    for campo in schema:
        if campo.get('type') == 'calculated':
            campo_name = campo.get('name')
            campo['value'] = dados_valores.get(campo_name)
            campos_exclusivos_dp.append(campo)

    context = {
        'solicitacao': solicitacao,
        'tipo_documento': tipo_doc,
        'campos_exclusivos_dp': campos_exclusivos_dp,
        'action_url': reverse('administracao:edit_solicitacao_modal', args=[solicitacao.id])
    }
    return render(request, 'partials/_dp_solicitacao_edit_form.html', context)

@dp_required
@require_POST
def dp_reverter_status_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    detalhes = request.POST.get('detalhes', '').strip()

    try:
        services.reverter_status_solicitacao(solicitacao, request.user, detalhes)
        msg = mark_safe('Status revertido pelo DP com sucesso.')
        response = render(request, 'partials/_message_sucess.html', {'message': msg})
        response['HX-Trigger'] = 'updateContent'
        return response
    except (ValidationError, PermissionDenied) as e:
        return render(request, 'partials/_message_error.html', {'message': str(e)})
    except Exception as e:
        return render(request, 'partials/_message_error.html', {'message': f"Erro ao reverter: {e}"})


# ==========================================
# IMPORTAÇÃO (TASKS HTMX)
# ==========================================

@dp_required
def import_data_modal_view(request, tipo_dado):
    """View para o modal de importação genérica (Lotações, Cargos, Colaboradores, etc.)"""
    config = {
        'colaboradores': {'titulo': 'Importar Colaboradores', 'url': reverse('administracao:import_data', args=['colaboradores'])},
        'lotacoes': {'titulo': 'Importar Lotações', 'url': reverse('administracao:import_data', args=['lotacoes'])},
        'cargos': {'titulo': 'Importar Cargos', 'url': reverse('administracao:import_data', args=['cargos'])},
    }

    if request.method == 'POST':
        arquivo = request.FILES.get('arquivo')
        
        if not arquivo:
            return render(request, 'partials/_message_error.html', {'message': "Nenhum arquivo selecionado."})

        try:
            file_ext = arquivo.name.split('.')[-1]
            temp_filename = f"tmp_import/{uuid.uuid4()}.{file_ext}"
            saved_path = default_storage.save(temp_filename, arquivo)

            task_id = str(uuid.uuid4())
            cache.set(task_id, {'status': 'processing', 'message': 'Iniciando importação...'}, timeout=3600)

            async_task('core.tasks.processar_importacao_task', task_id, saved_path, tipo_dado)

            return render(request, 'partials/_import_progress.html', {'task_id': task_id})

        except Exception as e:
            return render(request, 'partials/_message_error.html', {'message': f"Erro ao iniciar processo: {str(e)}"})

    ctx = config.get(tipo_dado)
    return render(request, 'partials/_import_form.html', {
        'modal_title': ctx['titulo'],
        'action_url': ctx['url']
    })

def check_import_status_view(request, task_id):
    """View chamada via HTMX Polling para verificar o status da importação."""
    status_data = caches['default'].get(task_id, {'status': 'error', 'message': 'Status da tarefa não encontrado ou expirou.'})

    if status_data['status'] == 'success':
        caches['default'].delete(task_id)
        response = render(request, 'partials/_message_sucess.html', {'message': status_data['message']})
        response['HX-Trigger'] = 'updateContent'
        return response

    elif status_data['status'] == 'error':
        caches['default'].delete(task_id)
        return render(request, 'partials/_message_error.html', {'message': status_data['message']})

    contexto = {
        'task_id': task_id,
        'message': status_data.get('message', 'Por favor, aguarde...')
    }
    return render(request, 'partials/_message_loading.html', contexto)