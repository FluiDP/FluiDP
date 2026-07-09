from urllib import response
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse
from .models import Cargo, Solicitacao, Lotacao, TipoDocumento
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from .decorators import aprovador_required, is_aprovador_solicitacao
from . import services 
from django.utils.safestring import mark_safe
from django.db.models import Q, Count
from django.utils import timezone

CustomUser = get_user_model()

@aprovador_required
def aprovador_painel_view(request):
    return redirect('gestor:dashboard')

@require_POST
@is_aprovador_solicitacao
def aprovar_solicitacao_view(request, solicitacao_id):
    """
    Chama o service.aprovar_solicitacao e retorna feedback visual
    """
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    
    try:
        services.aprovar_solicitacao(
            solicitacao, 
            ator=request.user, 
            request_user=request.user
        )
        
        msg = mark_safe('Solicitação <span class="text-slate-600 font-bold">aprovada</span> com sucesso!')
        
        response = render(request, 'partials/_message_sucess.html', {
            'message': msg
        })
        
        response['HX-Trigger'] = 'updateContent'
        
        return response
        
    except (ValidationError, PermissionDenied) as e:
        url_retry = reverse('colaborador:get_solicitacao_detalhes', args=[solicitacao.id])
        
        return render(request, 'partials/_message_error.html', {
            'message': e,
            'url_retry': url_retry
        })
        
    except Exception as e:
        url_retry = reverse('colaborador:get_solicitacao_detalhes', args=[solicitacao.id])
        
        return render(request, 'partials/_message_error.html', {
            'message': f"Erro inesperado: {e}",
            'url_retry': url_retry
        })


@require_POST
@is_aprovador_solicitacao
def recusar_solicitacao_view(request, solicitacao_id):
    """
    Chama o service.recusar_solicitacao e retorna feedback visual
    """
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    
    try:
        services.recusar_solicitacao(
            solicitacao, 
            ator=request.user, 
            detalhes="Recusado via Painel"
        )

        msg = mark_safe('Solicitação <span class="text-slate-600 font-bold">recusada</span> com sucesso.')

        response = render(request, 'partials/_message_sucess.html', {
            'message': msg
        })
        
        response['HX-Trigger'] = 'updateContent'
        
        return response
        
    except Exception as e:
        url_retry = reverse('colaborador:get_solicitacao_detalhes', args=[solicitacao.id])
        
        return render(request, 'partials/_message_error.html', {
            'message': f"Erro ao recusar: {e}",
            'url_retry': url_retry
        })

@aprovador_required
def gestor_dashboard_view(request):
    user = request.user

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
    )
    
    # KPI 1: Pendências na minha mesa
    pendencias_comigo = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
        aprovador_atual=user
    ).count()

    # KPI 2: Aguardando Lançamento do DP
    em_lancamento = Solicitacao.objects.filter(
        colaborador__in=minha_equipe,
        status=Solicitacao.StatusChoices.LANCAMENTO
    ).count()

    # KPI 3: Travados no Substituto
    travados_substituto = Solicitacao.objects.filter(
        colaborador__in=minha_equipe,
        status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO
    ).count()

    q_sol_pend = (
        Q(
            status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
            aprovador_atual=user
        ) |
        Q(
            status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
            colaborador_secundario=user
        )
    )

    if request.user.cargo and request.user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        q_sol_pend |= Q(
            status=Solicitacao.StatusChoices.PENDENTE_DIRETOR
        )

    solicitacoes_pendentes = Solicitacao.objects.filter(
        q_sol_pend
    ).order_by('data')

    # KPI 5: Distribuição por Tipo (Gráfico)
    ranking_query = Solicitacao.objects.filter(colaborador__in=minha_equipe) \
        .values('tipo_documento__nome_documento') \
        .annotate(total=Count('id')) \
        .order_by('-total')

    ranking_labels = [item['tipo_documento__nome_documento'] for item in ranking_query]
    ranking_data = [item['total'] for item in ranking_query]

    context = {
        'usuario': user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'is_aprovador': True,
        'kpi_pendencias': pendencias_comigo,
        'kpi_lancamento_dp': em_lancamento,
        'kpi_travados': travados_substituto,
        'distribuicao_tipos': ranking_query,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'ranking_labels': ranking_labels,
        'ranking_data': ranking_data,
        'active_link': 'dashboard',
    }

    if request.htmx:
        return render(request, 'painel/gestor/_content_dashboard.html', context)

    return render(request, 'painel/gestor/dashboard.html', context)

@aprovador_required
def gestor_solicitacoes_view(request):
    search_query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    documento_filter = request.GET.get('documento', '')
    lotacao_filter = request.GET.get('lotacao', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    page_number = request.GET.get('page')

    solicitacoes_list = Solicitacao.objects.filter(
        Q(colaborador=request.user) | Q(colaborador_secundario=request.user)
    ).distinct()

    if request.user.cargo and request.user.cargo.hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR
    ]:
        solicitacoes_list = Solicitacao.objects.filter(
            colaborador__lotacao__in=request.user.lotacao.get_descendentes(include_self=True)
        )

    elif request.user.groups.filter(name='DP').exists() or (request.user.cargo and request.user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR):
        solicitacoes_list = Solicitacao.objects.all()

    if search_query:
        solicitacoes_list = solicitacoes_list.filter(
            Q(id__icontains=search_query) |
            Q(colaborador__first_name__icontains=search_query) |
            Q(tipo_documento__nome_documento__icontains=search_query)
        )

    solicitacoes_list = solicitacoes_list.order_by('-data')
    
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

    paginator = Paginator(solicitacoes_list, 15)
    page_obj = paginator.get_page(page_number)
    
    tipos_documento = TipoDocumento.objects.filter(arquivado=False).order_by('nome_documento')
    lotacoes = Lotacao.objects.all() if (request.user.cargo and request.user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR) else request.user.lotacao.get_descendentes(include_self=True)
    status_choices = Solicitacao.StatusChoices.choices

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']
    
    url_params = f"&{query_params.urlencode()}" if query_params else ""

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

    context['current_sort'] = sort_param

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'is_aprovador': True,
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
        return render(request, 'painel/gestor/_content_solicitacoes.html', context)
    
    return render(request, 'painel/gestor/solicitacoes.html', context)
