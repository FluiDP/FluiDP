"""Política de arquivamento e visibilidade das solicitações."""
from .models import Cargo


DIAS_ARQUIVAMENTO_SOLICITACOES = 30


def pode_ver_arquivadas(user):
    return user.groups.filter(name__in=['DP', 'SYSTEM_ADMIN']).exists() or bool(
        user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR
    )


def filtrar_arquivadas(queryset, request):
    permitido = pode_ver_arquivadas(request.user)
    condicao = request.GET.get('arquivadas', 'ocultar') if permitido else 'ocultar'
    if condicao not in ('ocultar', 'incluir', 'somente'):
        condicao = 'ocultar'
    if condicao != 'incluir':
        queryset = queryset.filter(arquivado=condicao == 'somente')
    return queryset, {
        'pode_ver_arquivadas': permitido,
        'arquivadas_filter': condicao,
        'dias_arquivamento': DIAS_ARQUIVAMENTO_SOLICITACOES,
    }
