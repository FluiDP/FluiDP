from urllib import response
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse
from .models import Solicitacao, Lotacao
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
        
        response['HX-Trigger'] = 'updateSolicitacoesList'
        
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
        
        response['HX-Trigger'] = 'updateSolicitacoesList'
        
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

    minhas_lotacoes = Lotacao.objects.filter(
        Q(chefia=user) | Q(chefia_secundaria=user)
    )
    
    minha_equipe = CustomUser.objects.filter(
        lotacao__in=minhas_lotacoes,
        is_active=True
    ).exclude(id=user.id)

    # KPI 1: Pendências na minha mesa
    pendencias_comigo = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
        aprovador_atual=user
    ).count()

    # KPI 2: Pendências da Direção
    pendencias_direcao = Solicitacao.objects.filter(
        colaborador__in=minha_equipe,
        status=Solicitacao.StatusChoices.PENDENTE_DIRETOR
    ).count()

    # KPI 3: Travados no Substituto
    travados_substituto = Solicitacao.objects.filter(
        colaborador__in=minha_equipe,
        status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO
    ).count()

    solicitacoes_pendentes = Solicitacao.objects.filter(
        status=Solicitacao.StatusChoices.PENDENTE_GESTOR,
        aprovador_atual=user
    ).order_by('data')

    # KPI 5: Distribuição por Tipo (Gráfico)
    ranking_query = Solicitacao.objects.values('tipo_documento__nome_documento') \
        .annotate(total=Count('id')) \
        .order_by('-total')

    ranking_labels = [item['tipo_documento__nome_documento'] for item in ranking_query]
    ranking_data = [item['total'] for item in ranking_query]

    context = {
        'usuario': user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        'is_aprovador': True,
        'kpi_pendencias': pendencias_comigo,
        'kpi_direcao': pendencias_direcao,
        'kpi_travados': travados_substituto,
        'distribuicao_tipos': ranking_query,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'ranking_labels': ranking_labels,
        'ranking_data': ranking_data,
    }

    if request.htmx:
        return render(request, 'painel/gestor/_content_dashboard.html', context)

    return render(request, 'painel/gestor/dashboard.html', context)
