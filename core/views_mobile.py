from django.db.models import Q
from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required

from .models import Solicitacao, Cargo

CustomUser = get_user_model()

@login_required
def mobile_index_view(request):
    user = request.user
    search_query = request.GET.get('q', '')

    q_search = Q()
    if search_query:
        q_search = Q(
            Q(id__icontains=search_query) |
            Q(colaborador__first_name__icontains=search_query) |
            Q(tipo_documento__nome_documento__icontains=search_query)
        )

    solicitacoes_totais = Solicitacao.objects.filter(
        Q(colaborador=user) | Q(colaborador_secundario=user)
    ).filter(q_search).distinct().order_by('-data')

    status_encerrados = [
        Solicitacao.StatusChoices.FINALIZADO,
        Solicitacao.StatusChoices.RECUSADO,
        Solicitacao.StatusChoices.CANCELADO
    ]
    
    solicitacoes_andamento = solicitacoes_totais.exclude(status__in=status_encerrados)
    solicitacoes_encerradas = solicitacoes_totais.filter(status__in=status_encerrados)

    q_pendencias = Q()

    q_pendencias |= Q(
        colaborador_secundario=user, 
        status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO
    )

    q_pendencias |= Q(
        aprovador_atual=user, 
        status=Solicitacao.StatusChoices.PENDENTE_GESTOR
    )

    if user.groups.filter(name='DP').exists():
        q_pendencias |= Q(
            status__in=[Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO]
        )

    if user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        q_pendencias |= Q(
            status=Solicitacao.StatusChoices.PENDENTE_DIRETOR
        )

    solicitacoes_pendentes = Solicitacao.objects.filter(
        q_pendencias
    ).filter(q_search).distinct().order_by('-data')

    context = {
        'usuario': user,
        'usuario_tagname': user.first_name.split()[0] if user.first_name else user.username,
        'solicitacoes_totais': solicitacoes_totais,
        'solicitacoes_andamento': solicitacoes_andamento,
        'solicitacoes_encerradas': solicitacoes_encerradas,
        'solicitacoes_pendentes': solicitacoes_pendentes,
        'search_query': search_query,
    }

    if request.htmx:
        return render(request, 'mobile/pages/_content_home.html', context)
    
    return render(request, 'mobile/pages/home.html', context)

@login_required
def mobile_perfil_view(request):
    user = request.user
    context = {
        'usuario': user,
        'usuario_tagname': user.first_name.split()[0] if user.first_name else user.username,
    }
    
    if request.htmx:
        return render(request, 'mobile/pages/_content_perfil.html', context)
    
    return render(request, 'mobile/pages/perfil.html', context)
