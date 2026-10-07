from .services import criar_resumo_semanal_usuario, get_config
from .models import Notificacao

def tema_global(request):
    return {'tema': get_config()}


def notificacoes_globais(request):
    if not request.user.is_authenticated:
        return {'tem_notificacoes_nao_visualizadas': False}
    criar_resumo_semanal_usuario(request.user)
    ids_aviso = request.session.get('aviso_solicitacoes_login', [])
    avisos_login = list(Notificacao.objects.filter(
        pk__in=ids_aviso,
        destinatario=request.user,
        solicitacao__colaborador=request.user,
        visualizada_em__isnull=True,
    ).select_related('solicitacao__tipo_documento').order_by('criada_em', 'pk'))
    return {
        'tem_notificacoes_nao_visualizadas': request.user.notificacoes.filter(
            visualizada_em__isnull=True
        ).exists(),
        'aviso_solicitacoes_login': avisos_login,
    }
