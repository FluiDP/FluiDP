from django.db import transaction
from django.core.exceptions import ValidationError
from .models import LogAprovacao, Solicitacao, Cargo, CustomUser

def registrar_log_acao(solicitacao: Solicitacao, ator: CustomUser, acao: LogAprovacao.AcaoChoices, detalhes: str = ""):
    """
    Registra uma ação no histórico da solicitação.
    """
    return LogAprovacao.objects.create(
        solicitacao=solicitacao,
        ator=ator,
        acao=acao,
        detalhes=detalhes
    )

def _pode_ator_aprovar(solicitacao: Solicitacao, ator: CustomUser) -> bool:
    """
    Valida se o ator tem permissão para aprovar a solicitação no status atual.
    """
    status = solicitacao.status

    if status == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
        return solicitacao.colaborador_secundario == ator

    if status == Solicitacao.StatusChoices.PENDENTE_GESTOR:
        return solicitacao.aprovador_atual == ator

    if status == Solicitacao.StatusChoices.PENDENTE_DIRETOR:
        return ator.cargo and ator.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR

    if status == Solicitacao.StatusChoices.PENDENTE_DP:
        return ator.groups.filter(name='DP').exists()

    return False

@transaction.atomic
def aprovar_solicitacao(solicitacao: Solicitacao, ator: CustomUser, detalhes: str = ""):
    """
    Executa a lógica de aprovação, move para o próximo status e define o próximo aprovador.
    """
    
    if not _pode_ator_aprovar(solicitacao, ator):
        raise PermissionError(f"O usuário {ator} não tem permissão para aprovar esta solicitação no status {solicitacao.status}.")

    status_atual = solicitacao.status
    novo_status = None
    novo_aprovador = None
    acao_log = None

    if status_atual == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
        novo_status = Solicitacao.StatusChoices.PENDENTE_GESTOR
        acao_log = LogAprovacao.AcaoChoices.ACEITE_SECUNDARIO
        
        novo_aprovador = solicitacao.colaborador.lotacao.find_gestor_disponivel()
        
        if not novo_aprovador:
            raise ValidationError("Não foi possível encontrar um Gestor disponível (não ausente) na hierarquia da lotação.")

    elif status_atual == Solicitacao.StatusChoices.PENDENTE_GESTOR:
        acao_log = LogAprovacao.AcaoChoices.APROVADO_GESTOR
        
        gestor_e_diretor = (
            ator.cargo and ator.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR
        )

        if gestor_e_diretor:
            novo_status = Solicitacao.StatusChoices.PENDENTE_DP
            novo_aprovador = None
            
        elif solicitacao.tipo_documento.requer_aprovacao_diretor:
            novo_status = Solicitacao.StatusChoices.PENDENTE_DIRETOR
            novo_aprovador = None 
        
        else:
            novo_status = Solicitacao.StatusChoices.PENDENTE_DP
            novo_aprovador = None

    elif status_atual == Solicitacao.StatusChoices.PENDENTE_DIRETOR:
        novo_status = Solicitacao.StatusChoices.PENDENTE_DP
        acao_log = LogAprovacao.AcaoChoices.APROVADO_DIRETOR
        novo_aprovador = None

    elif status_atual == Solicitacao.StatusChoices.PENDENTE_DP:
        novo_status = Solicitacao.StatusChoices.APROVADO
        acao_log = LogAprovacao.AcaoChoices.PROCESSADO_DP
        novo_aprovador = None

    else:
        raise ValidationError(f"Solicitação com status '{status_atual}' não pode ser aprovada.")

    solicitacao.status = novo_status
    solicitacao.aprovador_atual = novo_aprovador
    solicitacao.save()

    registrar_log_acao(solicitacao, ator, acao_log, detalhes)

    return solicitacao

@transaction.atomic
def recusar_solicitacao(solicitacao: Solicitacao, ator: CustomUser, detalhes: str = ""):
    """
    Recusa a solicitação e encerra o fluxo.
    """

    mapa_log = {
        Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO: LogAprovacao.AcaoChoices.RECUSA_SECUNDARIO,
        Solicitacao.StatusChoices.PENDENTE_GESTOR: LogAprovacao.AcaoChoices.RECUSADO_GESTOR,
        Solicitacao.StatusChoices.PENDENTE_DIRETOR: LogAprovacao.AcaoChoices.RECUSADO_DIRETOR,
        Solicitacao.StatusChoices.PENDENTE_DP: LogAprovacao.AcaoChoices.RECUSADO_DP,
    }

    acao_log = mapa_log.get(solicitacao.status, LogAprovacao.AcaoChoices.COMENTARIO)

    solicitacao.status = Solicitacao.StatusChoices.RECUSADO
    solicitacao.aprovador_atual = None
    solicitacao.save()

    registrar_log_acao(solicitacao, ator, acao_log, detalhes)

    return solicitacao

@transaction.atomic
def criar_solicitacao(colaborador: CustomUser, tipo_documento, dados_preenchidos: dict, esquema_formulario: list):
    """
    Cria a solicitação, define o fluxo inicial (Substituto ou Gestor) e gera o log.
    """
    
    id_colaborador_secundario = None
    
    for campo in esquema_formulario:
        nome_campo = campo.get('name')
        if campo.get('options_source') == 'colaboradores_lotacao':
            valor_preenchido = dados_preenchidos.get('values', {}).get(nome_campo)
            if valor_preenchido:
                id_colaborador_secundario = valor_preenchido
                break

    nova_solicitacao = Solicitacao(
        colaborador=colaborador,
        tipo_documento=tipo_documento,
        dados_preenchidos=dados_preenchidos
    )

    if id_colaborador_secundario:
        nova_solicitacao.status = Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO
        nova_solicitacao.colaborador_secundario_id = id_colaborador_secundario
        nova_solicitacao.aprovador_atual = None 
    else:
        nova_solicitacao.status = Solicitacao.StatusChoices.PENDENTE_GESTOR
        
        gestor = colaborador.lotacao.find_gestor_disponivel()
        if not gestor:
            raise ValidationError("Não foi possível encontrar um gestor disponível na sua hierarquia.")
        
        nova_solicitacao.aprovador_atual = gestor

    nova_solicitacao.save()

    registrar_log_acao(
        solicitacao=nova_solicitacao, 
        ator=colaborador, 
        acao=LogAprovacao.AcaoChoices.CRIACAO, 
        detalhes="Solicitação criada."
    )

    return nova_solicitacao