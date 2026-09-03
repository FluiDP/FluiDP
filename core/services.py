import os
import re
import logging
from datetime import timedelta
from email.mime.image import MIMEImage
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Config, LogAprovacao, Notificacao, Solicitacao, Cargo, CustomUser, TipoDocumento, Lotacao
import pandas as pd
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.urls import reverse
from django.db.models import Count, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def deve_enviar_email_notificacao(notificacao):
    """Diretores recebem por e-mail somente o resumo semanal."""
    destinatario = notificacao.destinatario
    is_direcao = bool(
        destinatario.cargo_id
        and destinatario.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR
    )
    return not is_direcao or notificacao.tipo == Notificacao.TipoChoices.RESUMO_SEMANAL


def enviar_email_notificacao(notificacao_id):
    """Envia o e-mail correspondente sem propagar falhas para o fluxo principal."""
    try:
        notificacao = Notificacao.todos_objetos.select_related(
            'destinatario', 'destinatario__cargo', 'solicitacao', 'solicitacao__tipo_documento'
        ).get(pk=notificacao_id)
        destinatario = notificacao.destinatario
        if not destinatario.email or not deve_enviar_email_notificacao(notificacao):
            return False

        url_fluidp = f"{settings.SITE_URL.rstrip('/')}{reverse('painel')}"
        contexto = {
            'notificacao': notificacao,
            'nome_usuario': destinatario.first_name or destinatario.username,
            'url_fluidp': url_fluidp,
            'tema': get_config(),
        }
        html_content = render_to_string('emails/_notificacao.html', contexto)
        email = EmailMultiAlternatives(
            subject=f'FluiDP | {notificacao.titulo}',
            body=strip_tags(html_content),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinatario.email],
        )
        email.attach_alternative(html_content, 'text/html')

        logo_path = os.path.join(settings.STATIC_ROOT, 'images', 'header-logo-slate-400.png')
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as img_file:
                logo = MIMEImage(img_file.read())
                logo.add_header('Content-ID', '<logo_fluidp>')
                logo.add_header('Content-Disposition', 'inline')
                email.attach(logo)
                email.mixed_subtype = 'related'

        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception('Falha ao enviar e-mail da notificação %s.', notificacao_id)
        return False


def _agendar_email_notificacao(notificacao):
    if not deve_enviar_email_notificacao(notificacao):
        return False

    def enfileirar():
        try:
            from django_q.tasks import async_task
            async_task('core.services.enviar_email_notificacao', notificacao.pk)
        except Exception:
            logger.exception('Falha ao colocar o e-mail da notificação %s na fila.', notificacao.pk)

    transaction.on_commit(enfileirar)
    return True


def criar_notificacao(destinatario, tipo, titulo, mensagem, solicitacao=None, chave=None):
    """Cria uma notificação interna; a chave torna eventos periódicos idempotentes."""
    if not destinatario:
        return None
    if chave:
        notificacao, criada = Notificacao.todos_objetos.get_or_create(
            chave=chave,
            defaults={
                'destinatario': destinatario,
                'solicitacao': solicitacao,
                'tipo': tipo,
                'titulo': titulo,
                'mensagem': mensagem,
            },
        )
    else:
        notificacao = Notificacao.objects.create(
            destinatario=destinatario,
            solicitacao=solicitacao,
            tipo=tipo,
            titulo=titulo,
            mensagem=mensagem,
        )
        criada = True
    if criada:
        _agendar_email_notificacao(notificacao)
    return notificacao


def notificar_cancelamento_automatico(solicitacao, motivo):
    """Ponto de integração para as futuras rotinas de cancelamento automático."""
    return criar_notificacao(
        solicitacao.colaborador,
        Notificacao.TipoChoices.CANCELADA_SISTEMA,
        'Solicitação cancelada pelo sistema',
        f'A solicitação #{solicitacao.pk} foi cancelada automaticamente: {motivo}.',
        solicitacao,
    )


def preparar_aviso_login(request, usuario):
    """Agrupa recusas/cancelamentos novos para exibição única após o login."""
    tipos = [Notificacao.TipoChoices.RECUSADA, Notificacao.TipoChoices.CANCELADA_SISTEMA]
    pendentes = Notificacao.todos_objetos.filter(
        destinatario=usuario,
        tipo__in=tipos,
        aviso_login_exibido_em__isnull=True,
        excluida_em__isnull=True,
    )
    contagens = dict(pendentes.values_list('tipo').annotate(total=Count('id')))
    if not contagens:
        return
    pendentes.update(aviso_login_exibido_em=timezone.now())
    request.session['aviso_solicitacoes_login'] = {
        'canceladas': contagens.get(Notificacao.TipoChoices.CANCELADA_SISTEMA, 0),
        'recusadas': contagens.get(Notificacao.TipoChoices.RECUSADA, 0),
    }


def criar_resumos_semanais(data_referencia=None):
    """Gera uma notificação semanal por gestor/diretor com pendências atuais."""
    hoje = data_referencia or timezone.localdate()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    usuarios = CustomUser.objects.filter(
        is_active=True,
        cargo__hierarquia__in=[Cargo.HierarquiaChoices.DIRETOR, Cargo.HierarquiaChoices.GERENTE,
                              Cargo.HierarquiaChoices.COORDENADOR],
    ).select_related('cargo')
    criadas = 0
    for usuario in usuarios:
        criadas += int(criar_resumo_semanal_usuario(usuario, inicio_semana, data_referencia=hoje))
    return criadas


def criar_resumo_semanal_usuario(usuario, inicio_semana=None, data_referencia=None):
    """Cria, no máximo, um resumo por usuário em cada semana."""
    hoje = data_referencia or timezone.localdate()
    if hoje.weekday() != 0:
        return False
    if not usuario.cargo or usuario.cargo.hierarquia not in [
        Cargo.HierarquiaChoices.DIRETOR,
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR,
    ]:
        return False
    inicio_semana = inicio_semana or hoje
    quantidade = obter_pendencias_do_usuario(usuario).filter(
        status__in=[Solicitacao.StatusChoices.PENDENTE_GESTOR,
                    Solicitacao.StatusChoices.PENDENTE_DIRETOR]
    ).count()
    if not quantidade:
        return False
    notificacao, criada = Notificacao.todos_objetos.get_or_create(
        chave=f'resumo-semanal:{usuario.pk}:{inicio_semana.isoformat()}',
        defaults={
            'destinatario': usuario,
            'tipo': Notificacao.TipoChoices.RESUMO_SEMANAL,
            'titulo': 'Resumo semanal de aprovações',
            'mensagem': f'Você possui {quantidade} solicitação(ões) aguardando sua aprovação.',
        },
    )
    if criada:
        _agendar_email_notificacao(notificacao)
    return criada

def obter_pendencias_do_usuario(user):
    """
    Retorna um QuerySet consolidado com todas as solicitações que exigem 
    alguma ação do usuário, independentemente de onde a regra venha.
    As regras são cumulativas (Gestor + DP + Diretor + Aceite).
    """
    q_filtros = Q()

    if user.groups.filter(name='DP').exists():
        q_filtros |= Q(status__in=[Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO])

    q_filtros |= Q(status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO, colaborador_secundario=user)

    if user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        q_filtros |= Q(status=Solicitacao.StatusChoices.PENDENTE_DIRETOR)

    q_filtros |= Q(status=Solicitacao.StatusChoices.PENDENTE_GESTOR, aprovador_atual=user)

    q_minhas_lotacoes = Lotacao.objects.filter(
        Q(chefia=user) | (Q(chefia__isnull=True) & Q(chefia_secundaria=user))
    )
    
    if q_minhas_lotacoes.exists():
        minhas_lotacoes = set()
        for lotacao in q_minhas_lotacoes:
            minhas_lotacoes.add(lotacao.id)
            descendentes = lotacao.get_descendentes(include_self=True)
            minhas_lotacoes.update([d.id for d in descendentes])
            
        q_filtros |= Q(status=Solicitacao.StatusChoices.PENDENTE_GESTOR, colaborador__lotacao_id__in=minhas_lotacoes)

    if not q_filtros:
        return Solicitacao.objects.none()

    return Solicitacao.objects.filter(q_filtros).distinct().order_by('-data')


def obter_status_relatorio(status_informados=None, filtro_aplicado=False):
    """Normaliza o filtro do relatório; por padrão omite recusadas e canceladas."""
    valores_validos = {valor for valor, _ in Solicitacao.StatusChoices.choices}
    if filtro_aplicado:
        return list(dict.fromkeys(
            status for status in (status_informados or []) if status in valores_validos
        ))
    return [
        status for status, _ in Solicitacao.StatusChoices.choices
        if status not in {
            Solicitacao.StatusChoices.RECUSADO,
            Solicitacao.StatusChoices.CANCELADO,
        }
    ]

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

def _pode_ator_aprovar(solicitacao: Solicitacao, ator: CustomUser, request_user: CustomUser) -> bool:
    """
    Valida se o ator tem permissão para aprovar a solicitação no status atual.
    """
    status = solicitacao.status

    if solicitacao.colaborador != request_user:
        if status == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
            return solicitacao.colaborador_secundario == ator

        if status == Solicitacao.StatusChoices.PENDENTE_GESTOR:
            return solicitacao.aprovador_atual == ator

        if status == Solicitacao.StatusChoices.PENDENTE_DIRETOR:
            return ator.cargo and ator.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR

        if status in [Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO]:
            return ator.groups.filter(name='DP').exists()
        
    if status in [Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO]:
        return ator.groups.filter(name='DP').exists()
    
    if solicitacao.aprovador_atual == ator:
        return ator.cargo and ator.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR

    return False

@transaction.atomic
def aprovar_solicitacao(solicitacao: Solicitacao, ator: CustomUser, request_user: CustomUser, detalhes: str = ""):
    """
    Executa a lógica de aprovação, move para o próximo status e define o próximo aprovador.
    """
    
    if not _pode_ator_aprovar(solicitacao, ator, request_user):
        raise PermissionError(f"O usuário {ator} não tem permissão para aprovar esta solicitação no status {solicitacao.status}.")

    status_atual = solicitacao.status
    novo_status = None
    novo_aprovador = None
    acao_log = None

    if status_atual == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
        novo_status = Solicitacao.StatusChoices.PENDENTE_GESTOR
        acao_log = LogAprovacao.AcaoChoices.ACEITE_SECUNDARIO
        
        novo_aprovador = solicitacao.colaborador.lotacao.find_gestor_disponivel(solicitante=solicitacao.colaborador)
        
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
            acao_log = LogAprovacao.AcaoChoices.APROVADO_DIRETOR
            
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
        novo_status = Solicitacao.StatusChoices.LANCAMENTO
        acao_log = LogAprovacao.AcaoChoices.APROVADO_DP
        novo_aprovador = None

    elif status_atual == Solicitacao.StatusChoices.LANCAMENTO:
        novo_status = Solicitacao.StatusChoices.FINALIZADO
        acao_log = LogAprovacao.AcaoChoices.LANCADO
        novo_aprovador = None

    else:
        raise ValidationError(f"Solicitação com status '{status_atual}' não pode ser aprovada.")

    solicitacao.status = novo_status
    solicitacao.aprovador_atual = novo_aprovador
    solicitacao.save()

    registrar_log_acao(solicitacao, ator, acao_log, detalhes)

    if novo_status == Solicitacao.StatusChoices.FINALIZADO:
        criar_notificacao(
            solicitacao.colaborador,
            Notificacao.TipoChoices.APROVADA_DP,
            'Solicitação aprovada pelo DP',
            f'Sua solicitação #{solicitacao.pk} foi aprovada pelo Departamento Pessoal.',
            solicitacao,
        )

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

    criar_notificacao(
        solicitacao.colaborador,
        Notificacao.TipoChoices.RECUSADA,
        'Solicitação recusada',
        f'Sua solicitação #{solicitacao.pk} foi recusada por {ator.get_full_name() or ator.username}.',
        solicitacao,
    )

    return solicitacao

@transaction.atomic
def criar_solicitacao(colaborador, tipo_documento, dados_preenchidos: dict, esquema_formulario: list):
    """
    Cria a solicitação, define o fluxo inicial (Substituto ou Gestor) e gera o log.
    """
    
    valores = dados_preenchidos.get('values', {})
    mes_referencia = tipo_documento.validar_regras(valores)
    id_colaborador_secundario = None
    
    for campo in esquema_formulario:
        nome_campo = campo.get('name')
        if campo.get('options_source') in ['colaboradores_lotacao', 'colaboradores_mesmo_cargo']:
            valor_preenchido = dados_preenchidos.get('values', {}).get(nome_campo)
            if valor_preenchido:
                id_colaborador_secundario = valor_preenchido
                break

    nova_solicitacao = Solicitacao(
        colaborador=colaborador,
        tipo_documento=tipo_documento,
        dados_preenchidos=dados_preenchidos,
        mes_referencia=mes_referencia,
    )

    if id_colaborador_secundario:
        nova_solicitacao.status = Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO
        nova_solicitacao.colaborador_secundario_id = id_colaborador_secundario
        nova_solicitacao.aprovador_atual = None 
    else:
        if not colaborador.lotacao:
            raise ValidationError("O colaborador não possui uma lotação definida. Não é possível determinar o gestor responsável.")

        gestor = colaborador.lotacao.find_gestor_disponivel(solicitante=colaborador)
        if not gestor:

            if colaborador.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
                nova_solicitacao.status = Solicitacao.StatusChoices.PENDENTE_DP
                nova_solicitacao.aprovador_atual = None

            raise ValidationError("Não foi possível encontrar um gestor disponível na sua hierarquia.")
        
        if gestor.cargo and gestor.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
            nova_solicitacao.status = Solicitacao.StatusChoices.PENDENTE_DIRETOR
            nova_solicitacao.aprovador_atual = gestor
        else:
            nova_solicitacao.status = Solicitacao.StatusChoices.PENDENTE_GESTOR
            nova_solicitacao.aprovador_atual = gestor

    nova_solicitacao.save()

    registrar_log_acao(
        solicitacao=nova_solicitacao, 
        ator=colaborador, 
        acao=LogAprovacao.AcaoChoices.CRIACAO,
    )

    criar_notificacao(
        colaborador,
        Notificacao.TipoChoices.SOLICITACAO_ABERTA,
        'Solicitação aberta com sucesso',
        f'Sua solicitação #{nova_solicitacao.pk} de {tipo_documento.nome_documento} foi registrada.',
        nova_solicitacao,
    )
    if nova_solicitacao.status == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO:
        criar_notificacao(
            nova_solicitacao.colaborador_secundario,
            Notificacao.TipoChoices.PENDENCIA_SECUNDARIO,
            'Nova solicitação aguardando seu aceite',
            f'A solicitação #{nova_solicitacao.pk} de {colaborador.get_full_name() or colaborador.username} aguarda seu aceite.',
            nova_solicitacao,
        )

    return nova_solicitacao

@transaction.atomic
def comentar_solicitacao(solicitacao: Solicitacao, ator: CustomUser, comentario: str):
    """
    Adiciona um comentário à solicitação.
    """
    if not comentario.strip():
        raise ValidationError("O comentário não pode estar vazio.")

    registrar_log_acao(
        solicitacao=solicitacao,
        ator=ator,
        acao=LogAprovacao.AcaoChoices.COMENTARIO,
        detalhes=comentario
    )

    destinatarios_ids = {
        solicitacao.colaborador_id,
        solicitacao.colaborador_secundario_id,
        solicitacao.aprovador_atual_id,
        *solicitacao.logs.exclude(ator=ator).values_list('ator_id', flat=True),
    }
    destinatarios_ids.discard(None)
    destinatarios_ids.discard(ator.pk)
    for destinatario in CustomUser.objects.filter(pk__in=destinatarios_ids, is_active=True):
        criar_notificacao(
            destinatario,
            Notificacao.TipoChoices.COMENTARIO,
            'Novo comentário na solicitação',
            f'{ator.get_full_name() or ator.username} comentou na solicitação #{solicitacao.pk}.',
            solicitacao,
        )

    return solicitacao

@transaction.atomic
def editar_solicitacao(solicitacao: Solicitacao, ator: CustomUser, novos_valores: dict):
    """
    Edita os dados de uma solicitação existente.
    - Se for o autor: Edita todos os campos livremente, desde que a solicitação permita (can_edit).
    - Se for o DP: Edita apenas campos 'calculated' (pelo form_schema) e apenas se estiver pendente para o DP (can_edit_dp).
    """
    
    is_autor = (solicitacao.colaborador == ator)
    is_dp = ator.groups.filter(name='DP').exists()

    pode_editar_como_autor = is_autor and solicitacao.can_edit(ator)
    pode_editar_como_dp = is_dp and solicitacao.can_edit_dp(ator)

    if not (pode_editar_como_autor or pode_editar_como_dp):
        raise PermissionError("Você não tem permissão para editar os dados desta solicitação no status atual.")

    esquema = solicitacao.dados_preenchidos.get('schema', [])
    valores_atuais = solicitacao.dados_preenchidos.get('values', {})
    
    if isinstance(valores_atuais, list):
        valores_atuais = {}

    valores_atualizados = dict(valores_atuais)
    acao_log = None

    if pode_editar_como_autor:
        valores_atualizados.update(novos_valores)
        log_detalhes = "O solicitante alterou os dados do formulário."
        acao_log = LogAprovacao.AcaoChoices.EDICAO
        
    elif pode_editar_como_dp:
        campos_calculados = {c['name']: c.get('label', c['name']) for c in esquema if c.get('type') == 'calculated'}
        
        campos_alterados = []
        detalhes_alteracoes = []

        for key, new_value in novos_valores.items():
            if key in campos_calculados:
                old_value = valores_atuais.get(key, '00:00')
                if str(old_value) != str(new_value):
                    valores_atualizados[key] = new_value
                    campos_alterados.append(key)
                    detalhes_alteracoes.append(f"[{campos_calculados[key]}] de '{old_value}' para '{new_value}'")
                    
        if not campos_alterados:
            raise ValidationError("Nenhuma alteração nos saldos/horas foi preenchida para envio.")
            
        log_detalhes = "O Departamento Pessoal corrigiu os seguintes saldos: " + "; ".join(detalhes_alteracoes) + "."
        acao_log = LogAprovacao.AcaoChoices.EDICAO

    solicitacao.dados_preenchidos['values'] = valores_atualizados
    solicitacao.save()

    registrar_log_acao(
        solicitacao=solicitacao,
        ator=ator,
        acao=acao_log,
        detalhes=log_detalhes
    )

    return solicitacao

@transaction.atomic
def cancelar_solicitacao(solicitacao: Solicitacao, ator: CustomUser, detalhes: str = ""):
    """
    Cancela a solicitação. Apenas o solicitante pode executar esta ação (conforme can_cancel do Model).
    """
    if not solicitacao.can_cancel(ator):
        raise PermissionError("Você não tem permissão para cancelar esta solicitação.")

    solicitacao.status = Solicitacao.StatusChoices.CANCELADO
    solicitacao.aprovador_atual = None
    solicitacao.save()

    registrar_log_acao(
        solicitacao=solicitacao,
        ator=ator,
        acao=LogAprovacao.AcaoChoices.CANCELAMENTO,
    )

    return solicitacao

@transaction.atomic
def reverter_status_solicitacao(solicitacao: Solicitacao, ator: CustomUser, detalhes: str = ""):
    """
    Reverte a última decisão tomada na solicitação, voltando um estágio no fluxo.
    Inteligente: Se for recuar para PENDENTE_GESTOR, ele procura o gestor disponível ATUAL
    da lotação, prevenindo que a solicitação caia na mesa de um ex-gestor ou gestor de férias.
    """

    if solicitacao.ja_revertido_por(ator):
        raise PermissionError("Você já reverteu uma decisão nesta solicitação. Uma reversão só pode ser realizada uma vez.")

    if not solicitacao.can_reverse_status(ator):
        raise PermissionError("Não tem permissão para reverter o status desta solicitação.")

    acoes_decisao = [
        LogAprovacao.AcaoChoices.ACEITE_SECUNDARIO,
        LogAprovacao.AcaoChoices.RECUSA_SECUNDARIO,
        LogAprovacao.AcaoChoices.APROVADO_GESTOR,
        LogAprovacao.AcaoChoices.RECUSADO_GESTOR,
        LogAprovacao.AcaoChoices.APROVADO_DIRETOR,
        LogAprovacao.AcaoChoices.RECUSADO_DIRETOR,
        LogAprovacao.AcaoChoices.APROVADO_DP,
        LogAprovacao.AcaoChoices.RECUSADO_DP,
        LogAprovacao.AcaoChoices.LANCADO,
    ]

    ultimo_log = solicitacao.logs.filter(acao__in=acoes_decisao).order_by('-data_acao').first()

    if not ultimo_log:
        raise ValidationError("Não há histórico de decisão válido para reverter.")

    novo_status = solicitacao.status
    novo_aprovador = solicitacao.aprovador_atual

    if ultimo_log.acao in [LogAprovacao.AcaoChoices.APROVADO_DP, LogAprovacao.AcaoChoices.RECUSADO_DP, LogAprovacao.AcaoChoices.LANCADO]:
        novo_status = Solicitacao.StatusChoices.PENDENTE_DP
        novo_aprovador = None

    elif ultimo_log.acao in [LogAprovacao.AcaoChoices.APROVADO_DIRETOR, LogAprovacao.AcaoChoices.RECUSADO_DIRETOR]:
        novo_status = Solicitacao.StatusChoices.PENDENTE_DIRETOR
        novo_aprovador = ultimo_log.ator

    elif ultimo_log.acao in [LogAprovacao.AcaoChoices.APROVADO_GESTOR, LogAprovacao.AcaoChoices.RECUSADO_GESTOR]:
        gestor_responsavel = solicitacao.colaborador.lotacao.find_gestor_disponivel(solicitante=solicitacao.colaborador)

        if not gestor_responsavel:
            novo_status = Solicitacao.StatusChoices.PENDENTE_DP
            novo_aprovador = None
        else:
            if gestor_responsavel.cargo and gestor_responsavel.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
                novo_status = Solicitacao.StatusChoices.PENDENTE_DIRETOR
            else:
                novo_status = Solicitacao.StatusChoices.PENDENTE_GESTOR
            novo_aprovador = gestor_responsavel

    elif ultimo_log.acao in [LogAprovacao.AcaoChoices.ACEITE_SECUNDARIO, LogAprovacao.AcaoChoices.RECUSA_SECUNDARIO]:
        novo_status = Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO
        novo_aprovador = None

    nome_acao_desfeita = ultimo_log.get_acao_display()

    texto_detalhes = f"Status revertido. A decisão anterior ('{nome_acao_desfeita}') foi desfeita."
    if detalhes:
        texto_detalhes += f" Justificativa: {detalhes}"

    registrar_log_acao(
        solicitacao=solicitacao,
        ator=ator,
        acao=LogAprovacao.AcaoChoices.REVERSAO,
        detalhes=texto_detalhes
    )

    solicitacao.status = novo_status
    solicitacao.aprovador_atual = novo_aprovador
    solicitacao.save()

    return solicitacao

def importar_dados(arquivo_io, nome_arquivo, model_class, mapa_de_campos, campo_busca_fk=None):
    """
    Importa dados com tratamento para CPF numérico, Username=Matrícula e auto-criação de FKs.
    """
    User = get_user_model()

    if nome_arquivo.lower().endswith('.csv'):
        df = pd.read_csv(arquivo_io, sep=',', encoding='utf-8')
    elif nome_arquivo.lower().endswith(('.xls', '.xlsx')):
        df = pd.read_excel(arquivo_io)
    else:
        raise ValidationError("Formato inválido. Use .csv ou .xlsx")

    df.columns = df.columns.str.strip()
    
    sucesso = 0
    erros = []
    
    SENHA_PADRAO = 'Ti!@0101'

    try:
        with transaction.atomic():
            for index, row in df.iterrows():
                linha = index + 2
                dados_para_salvar = {}

                try:
                    for coluna_excel, config_modelo in mapa_de_campos.items():
                        
                        if coluna_excel not in df.columns:
                            continue

                        valor_celula = row.get(coluna_excel)
                        
                        if pd.isna(valor_celula):
                            valor_celula = None
                        
                        campo_destino = config_modelo if isinstance(config_modelo, str) else config_modelo[0]
                        
                        if campo_destino == 'cpf' and valor_celula:
                            if isinstance(valor_celula, float):
                                valor_celula = int(valor_celula)
                            
                            valor_celula = re.sub(r'[^0-9]', '', str(valor_celula)).zfill(11)

                        if isinstance(config_modelo, str):
                            dados_para_salvar[config_modelo] = valor_celula

                        elif isinstance(config_modelo, tuple):
                            campo_no_modelo, model_fk, campo_busca = config_modelo
                            
                            if valor_celula:
                                obj_fk, created_fk = model_fk.objects.get_or_create(
                                    **{campo_busca: valor_celula}
                                )
                                dados_para_salvar[campo_no_modelo] = obj_fk
                            else:
                                dados_para_salvar[campo_no_modelo] = None
                    
                    is_usuario = (model_class == User) or (model_class.__name__ == 'CustomUser')
                    senha_foi_injetada = False

                    if is_usuario:
                        if 'matricula' in dados_para_salvar and dados_para_salvar['matricula']:
                            dados_para_salvar['username'] = str(dados_para_salvar['matricula'])
                        elif 'email' in dados_para_salvar:
                            dados_para_salvar['username'] = dados_para_salvar['email']
                        
                        if 'is_active' not in dados_para_salvar:
                            dados_para_salvar['is_active'] = True

                        if 'password' not in dados_para_salvar or not dados_para_salvar['password']:
                            dados_para_salvar['password'] = SENHA_PADRAO
                            senha_foi_injetada = True

                    if campo_busca_fk:
                        filtro_busca = {k: dados_para_salvar[k] for k in campo_busca_fk if k in dados_para_salvar}
                        
                        if not filtro_busca:
                             raise ValueError(f"Campos chaves ({campo_busca_fk}) não encontrados na linha.")

                        obj, created = model_class.objects.update_or_create(
                            defaults=dados_para_salvar,
                            **filtro_busca
                        )
                    else:
                        obj = model_class.objects.create(**dados_para_salvar)
                        created = True

                    if is_usuario:
                        precisa_salvar_senha = False
                        
                        if senha_foi_injetada or created:
                            precisa_salvar_senha = True
                        elif obj.check_password(SENHA_PADRAO):
                            precisa_salvar_senha = True

                        if precisa_salvar_senha:
                            obj.set_password(SENHA_PADRAO)
                            obj.precisa_trocar_senha = True
                            obj.save()

                    sucesso += 1

                except Exception as e:
                    erros.append(f"Linha {linha}: {e}")

    except Exception as e:
        return {'sucesso': 0, 'erros': [f"Erro Crítico na Importação: {e}"]}

    return {'sucesso': sucesso, 'erros': erros}

def new_collaborator_email(instance):
    """
    Gera um token de definição de senha e envia um e-mail de boas-vindas com imagem embutida.
    """
    user = instance
    
    try:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        link_relativo = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        
        full_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8080')
        
        if "://" in full_site_url:
            protocol, domain = full_site_url.split("://", 1)
        else:
            protocol = "http"
            domain = full_site_url
            
        domain = domain.rstrip('/')

        link_completo = f"{protocol}://{domain}{link_relativo}"
        
        contexto = {
            'nome_usuario': user.first_name or user.username,
            'link_definicao_senha': link_completo,
            'email_usuario': user.email,
            'protocol': protocol,
            'domain': domain,
        }

        contexto['tema'] = get_config()
        
        html_content = render_to_string('emails/_new_collaborators.html', contexto)
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject="Boas vindas ao FluiDP | São Camilo Crato",
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_content, "text/html")
        
        email.mixed_subtype = 'related'
        
        logo_path = os.path.join(settings.STATIC_ROOT, 'images', 'header-logo-slate-400.png')
        
        try:
            with open(logo_path, 'rb') as img_file:
                imagem_anexo = MIMEImage(img_file.read())
                imagem_anexo.add_header('Content-ID', '<logo_fluidp>')
                imagem_anexo.add_header('Content-Disposition', 'inline')
                email.attach(imagem_anexo)
        except FileNotFoundError:
            raise Exception(f"ERRO FATAL: A imagem não foi encontrada no caminho: {logo_path}")
        
        email.send()
        return True

    except Exception as e:
        print(f"Erro ao enviar e-mail de boas-vindas para {user.email}: {e}")
        return False
    
def enviar_email_boas_vindas_task(user_id):
    """
    Tarefa de background que recebe o ID, procura o utilizador no banco e envia o e-mail.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    try:
        user = User.objects.get(id=user_id)
        new_collaborator_email(user)
    except User.DoesNotExist:
        print(f"Erro: Utilizador com ID {user_id} não encontrado.")

def get_config():
    """
    Retorna a instância de Config, criando uma se não existir.
    """

    config, created = Config.objects.get_or_create(pk=1)
    return config.load()

def set_config(nome_instituicao, primary_color, secondary_color, emphasis_color, logo):
    """
    Salva as configurações de tema, garantindo que haja apenas uma instância.
    """
    config = get_config()

    if nome_instituicao:
        config.nome_instituicao = nome_instituicao
    if primary_color:
        config.primary_color = primary_color
    if secondary_color:
        config.secondary_color = secondary_color
    if emphasis_color:
        config.emphasis_color = emphasis_color
    if logo:
        config.logo = logo
    else:
        config.logo = None
        
    config.save()
    return config

def new_password(user, new_password: str):
    """
    Define uma nova senha para o usuário.
    """

    try:
        user.set_password(new_password)
        user.precisa_trocar_senha = False
        user.save()
        return True
    except Exception as e:
        print(f"Erro ao definir nova senha para o usuário {user.username}: {e}")
        return False
