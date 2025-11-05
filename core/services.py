from django.db import transaction
from django.utils import timezone
from .models import LogAprovacao, Solicitacao, CustomUser, Cargo


# Registro de logs de ações em solicitações

def registrar_log_acao(solicitacao: Solicitacao, ator: CustomUser, acao: LogAprovacao.AcaoChoices, detalhes: str = ""):
    log = LogAprovacao.objects.create(
        solicitacao=solicitacao,
        ator=ator,
        acao=acao,
        detalhes=detalhes
    )
    return log


# Lógica de aprovação de solicitações

def ferias_ativas(usuario: CustomUser) -> bool:
    if not usuario or not usuario.ausencia_inicio or not usuario.ausencia_fim:
        return False
        
    hoje = timezone.now().date()
    return usuario.ausencia_inicio <= hoje <= usuario.ausencia_fim

def encontrar_aprovador(solicitacao: Solicitacao) -> CustomUser | None:

    if solicitacao.status == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
        aprovador = solicitacao.colaborador_secundario
        if aprovador and not ferias_ativas(aprovador):
            return aprovador
        return None

    
    lotacao_atual = solicitacao.colaborador.lotacao
    if not lotacao_atual:
        return None

    if solicitacao.status == Solicitacao.StatusChoices.PENDENTE_GESTOR:

        while lotacao_atual:

            chefe = lotacao_atual.chefia
            if chefe and not ferias_ativas(chefe):
                return chefe

            chefe_sub = lotacao_atual.chefia_secundaria
            if chefe_sub and not ferias_ativas(chefe_sub):
                return chefe_sub
            
            lotacao_atual = lotacao_atual.lotacao_pai
        
        return None

    return None

def _pode_ator_aprovar(solicitacao: Solicitacao, ator: CustomUser) -> bool:
    status = solicitacao.status
    
    if status == Solicitacao.StatusChoices.PENDENTE_GESTOR:
        return ator == solicitacao.aprovador_atual
        
    if status == Solicitacao.StatusChoices.PENDENTE_DIRETOR:
        if ator.cargo and ator.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
            return True
    
    if status == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
        return ator == solicitacao.colaborador_secundario

    return False

@transaction.atomic
def aprovar_solicitacao(solicitacao: Solicitacao, ator: CustomUser, detalhes: str = ""):
    
    if not _pode_ator_aprovar(solicitacao, ator):
        raise PermissionError("Usuário não tem permissão para aprovar esta solicitação neste status.")

    status_atual = solicitacao.status
    acao_log = None
    proximo_status = None

    if status_atual == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
        acao_log = LogAprovacao.AcaoChoices.ACEITE_SECUNDARIO
        proximo_status = Solicitacao.StatusChoices.PENDENTE_GESTOR

    elif status_atual == Solicitacao.StatusChoices.PENDENTE_GESTOR:
        acao_log = LogAprovacao.AcaoChoices.APROVADO_GESTOR
        
        if solicitacao.tipo_documento.requer_aprovacao_diretor:
            proximo_status = Solicitacao.StatusChoices.PENDENTE_DIRETOR
        else:
            proximo_status = Solicitacao.StatusChoices.APROVADO

    elif status_atual == Solicitacao.StatusChoices.PENDENTE_DIRETOR:
        acao_log = LogAprovacao.AcaoChoices.APROVADO_DIRETOR
        proximo_status = Solicitacao.StatusChoices.APROVADO
    
    else:
        raise ValueError(f"Solicitação com status {status_atual} não pode ser aprovada.")

    solicitacao.status = proximo_status
    
    if proximo_status == Solicitacao.StatusChoices.PENDENTE_GESTOR:
         solicitacao.aprovador_atual = encontrar_aprovador(solicitacao)
    else:
         solicitacao.aprovador_atual = None

    solicitacao.save()

    LogAprovacao.objects.create(
        solicitacao=solicitacao,
        ator=ator,
        acao=acao_log,
        detalhes=detalhes
    )
