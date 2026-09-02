from .services import criar_resumo_semanal_usuario, get_config

def tema_global(request):
    return {'tema': get_config()}


def notificacoes_globais(request):
    if not request.user.is_authenticated:
        return {'tem_notificacoes_nao_visualizadas': False}
    criar_resumo_semanal_usuario(request.user)
    return {
        'tem_notificacoes_nao_visualizadas': request.user.notificacoes.filter(
            visualizada_em__isnull=True
        ).exists()
    }
