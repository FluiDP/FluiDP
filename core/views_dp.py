from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q
from django.urls import reverse
from django.http import HttpResponse
from django.db.models import Count

from .models import Cargo, Solicitacao, TipoDocumento, CustomUser, Lotacao
from .decorators import dp_required
from .forms import CustomUserForm, EditCustomUserForm, LotacaoForm, CargoForm, TipoDocumentoForm

@dp_required
def dp_dashboard_view(request):
    user = request.user
    is_gestor_dp = user.groups.filter(name='DP').exists() and (user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.GERENTE or user.cargo.hierarquia == Cargo.HierarquiaChoices.COORDENADOR)

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

    q_pendencias_dp = Q(status=Solicitacao.StatusChoices.PENDENTE_DP)
    
    if is_gestor_dp:
        q_pendencias_dp = q_pendencias_dp | Q(colaborador__in=minha_equipe, status=Solicitacao.StatusChoices.PENDENTE_GESTOR)

    # KPI 1: Pendências na minha mesa
    pendencias_comigo = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_DP
    ).count()

    # KPI 2: Pendências da Direção
    pendencias_direcao = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_DIRETOR
    ).count()

    # KPI 3: Solicitações em fluxo
    fluxo_total = Solicitacao.objects.filter(
        status__in=[Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
                    Solicitacao.StatusChoices.PENDENTE_GESTOR,
                    Solicitacao.StatusChoices.PENDENTE_DIRETOR,
                    Solicitacao.StatusChoices.PENDENTE_DP],
    ).count()

    solicitacoes_pendentes = []

    if user.groups.filter(name='DP').exists():
        solicitacoes_pendentes = Solicitacao.objects.filter(
            status=Solicitacao.StatusChoices.PENDENTE_DP
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

    # KPI 4: Distribuição por Tipo (Gráfico)
    ranking_query_docs = Solicitacao.objects.values('tipo_documento__nome_documento') \
        .annotate(total=Count('id')) \
        .order_by('-total')

    # KPI 5: Distribuição por Setor (Gráfico)
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


# --- LOTAÇÕES ---

@dp_required
def dp_lotacoes_view(request):

    lotacoes = Lotacao.objects.filter(arquivado=False).order_by('nome_lotacao')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'lotacoes': lotacoes,
        'active_link': 'lotacoes',
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


# --- CARGOS ---

@dp_required
def dp_cargos_view(request):

    cargos = Cargo.objects.filter(arquivado=False).order_by('hierarquia', 'nome_cargo')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'cargos': cargos,
        'active_link': 'cargos',
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
            response = render(request, 'partials/_message_sucess.html', {'message': f"Cargo <strong>{nome}</strong> excluído!"})
            response['HX-Trigger'] = 'updateContent'
            return response
        except Exception:
            return render(request, 'partials/_message_error.html', {'message': "Não é possível excluir: Existem colaboradores vinculados."})
    
    return render(request, 'partials/_generic_confirm_modal.html', {
        'modal_title': 'Excluir Cargo',
        'message': f"Deseja excluir permanentemente o cargo <strong>{cargo.nome_cargo}</strong>?",
        'action_url': reverse('administracao:delete_cargo', args=[pk]),
        'submit_text': 'Excluir',
        'color': 'red',
        'icon_name': 'trash'
    })


# --- COLABORADORES ---

@dp_required
def dp_colaboradores_view(request):

    colaboradores = CustomUser.objects.filter(is_active=True).order_by('first_name')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'colaboradores': colaboradores,
        'active_link': 'colaboradores',
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


# --- DOCUMENTOS ---

@dp_required
def dp_documentos_view(request):

    documentos = TipoDocumento.objects.filter(arquivado=False).order_by('nome_documento')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'documentos': documentos,
        'active_link': 'documentos',
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_documentos.html', context)
    
    return render(request, 'painel/dp/documentos.html', context)

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


# --- SOLICITAÇÕES ---

@dp_required
def dp_solicitacoes_view(request):
    solicitacoes = Solicitacao.objects.all().order_by('-data')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'solicitacoes': solicitacoes,
        'active_link': 'solicitacoes',
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_solicitacoes.html', context)
    
    return render(request, 'painel/dp/solicitacoes.html', context)