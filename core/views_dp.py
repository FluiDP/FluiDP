from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Q
from django.urls import reverse
from django.http import HttpResponse
from django.db.models import Count

from .models import Cargo, Solicitacao, TipoDocumento, CustomUser, Lotacao
from .decorators import dp_required
from .forms import LotacaoForm, CargoForm

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

    solicitacoes_pendentes = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_DP
    ).order_by('data')

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
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
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
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_dashboard.html', context)

    return render(request, 'painel/dp/dashboard.html', context)

@dp_required
def dp_lotacoes_view(request):
    """View Principal: Carrega a página completa de lotações"""
    lotacoes = Lotacao.objects.all().order_by('nome_lotacao')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'lotacoes': lotacoes,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_lotacoes.html', context)
    
    return render(request, 'painel/dp/lotacoes.html', context)

@dp_required
def create_lotacao_model_view(request):
    """View Modal: Criação com Trigger de Atualização e Feedback visual"""
    form = LotacaoForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        
        response = render(request, 'partials/_message_sucess.html', {
            'message': f"Lotação <strong>{obj.nome_lotacao}</strong> criada com sucesso!"
        })
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Nova Lotação',
        'action_url': reverse('administracao:create_lotacao'),
        'submit_text': 'Salvar Lotação',
    })

@dp_required
def dp_cargos_view(request):
    cargos = Cargo.objects.all().order_by('hierarquia', 'nome_cargo')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'cargos': cargos,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_cargos.html', context)
    
    return render(request, 'painel/dp/cargos.html', context)

@dp_required
def create_cargo_model_view(request):
    form = CargoForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        
        response = render(request, 'partials/_message_sucess.html', {
            'message': f"Cargo <strong>{obj.nome_cargo}</strong> criado com sucesso!"
        })
        response['HX-Trigger'] = 'updateContent'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Novo Cargo',
        'action_url': reverse('administracao:create_cargo'),
        'submit_text': 'Salvar Cargo',
    })

@dp_required
def dp_colaboradores_view(request):
    return redirect('indisponibilidade') # temporariamente indisponível

    colaboradores = CustomUser.objects.all().order_by('first_name')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'colaboradores': colaboradores,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_colaboradores.html', context)
    
    return render(request, 'painel/dp/colaboradores.html', context)

@dp_required
def dp_documentos_view(request):
    return redirect('indisponibilidade') # temporariamente indisponível

    documentos = TipoDocumento.objects.all().order_by('nome_documento')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'documentos': documentos,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_documentos.html', context)
    
    return render(request, 'painel/dp/documentos.html', context)

@dp_required
def dp_solicitacoes_view(request):
    solicitacoes = Solicitacao.objects.all().order_by('-data')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'solicitacoes': solicitacoes,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_solicitacoes.html', context)
    
    return render(request, 'painel/dp/solicitacoes.html', context)
