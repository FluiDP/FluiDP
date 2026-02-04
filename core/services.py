import re
from django.db import transaction
from django.core.exceptions import ValidationError
from .models import LogAprovacao, Solicitacao, Cargo, CustomUser, Lotacao
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

        if status == Solicitacao.StatusChoices.PENDENTE_DP:
            return ator.groups.filter(name='DP').exists()
        
    if status == Solicitacao.StatusChoices.PENDENTE_DP:
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
        
        gestor = colaborador.lotacao.find_gestor_disponivel(solicitante=colaborador)
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
    
    SENHA_PADRAO = 'Mudar@123'

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
                            valor_celula = re.sub(r'[^0-9]', '', str(valor_celula))

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
    Gera um token de definição de senha e envia um e-mail de boas-vindas.
    """
    user = instance
    
    try:
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        link_relativo = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
        
        full_site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        
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
        
        html_content = render_to_string('emails/_new_collaborators.html', contexto)
        text_content = strip_tags(html_content)
        
        email = EmailMultiAlternatives(
            subject="Boas vindas ao FluiDP | São Camilo Crato",
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.attach_alternative(html_content, "text/html")
        
        email.send()
        return True

    except Exception as e:
        print(f"Erro ao enviar e-mail de boas-vindas para {user.email}: {e}")
        return False
