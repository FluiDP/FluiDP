from .models import LogAprovacao, Solicitacao, CustomUser

def registrar_log_acao(solicitacao: Solicitacao, ator: CustomUser, acao: LogAprovacao.AcaoChoices, detalhes: str = ""):
    """
    Função de serviço centralizada para criar um novo registo de log
    para uma solicitação.
    
    Isto garante que todos os logs são criados da mesma forma.
    """
    
    log = LogAprovacao.objects.create(
        id_solicitacao=solicitacao,
        id_ator=ator,
        acao=acao,
        detalhes=detalhes
    )
    
    return log
