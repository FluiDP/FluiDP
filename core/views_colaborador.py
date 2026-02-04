import copy
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import LogAprovacao, Solicitacao, TipoDocumento, Cargo
from .decorators import colaborador_required
from . import services

User = get_user_model()

@colaborador_required
def colaborador_painel_view(request):
    
    status_pendentes_ativos = [
        Solicitacao.StatusChoices.PENDENTE_GESTOR,
        Solicitacao.StatusChoices.PENDENTE_DIRETOR,
        Solicitacao.StatusChoices.PENDENTE_DP,
        Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
    ]

    q_usuario_envolvido = Q(colaborador=request.user) | Q(colaborador_secundario=request.user)

    q_solicitacoes_pendentes = (
        (Q(status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO) & Q(colaborador_secundario=request.user)) |
        (Q(status=Solicitacao.StatusChoices.PENDENTE_GESTOR) & Q(aprovador_atual=request.user))
    )

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        
        'solicitacoes': Solicitacao.objects.filter(
            colaborador=q_usuario_envolvido
        ).distinct().order_by('-data'),
        
        'solicitacoes_ativas': Solicitacao.objects.filter(
            colaborador=request.user,
            status__in=status_pendentes_ativos
        ).distinct().order_by('-data'),
        
        'solicitacoes_pendentes': Solicitacao.objects.filter(
            q_solicitacoes_pendentes
        ).distinct().order_by('-data'),
        'active_link': 'dashboard'
    }

    if request.htmx:
        return render(request, 'painel/colaborador/_content_home.html', context)
    
    return render(request, 'painel/colaborador/home.html', context)

@colaborador_required
def colaborador_solicitacoes_view(request):

    q_usuario_envolvido = Q(colaborador=request.user) | Q(colaborador_secundario=request.user)

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'solicitacoes': Solicitacao.objects.filter(
            q_usuario_envolvido
        ).distinct().order_by('-data'),
        'active_link': 'solicitacoes'
    }

    if request.user.cargo.hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR,
        Cargo.HierarquiaChoices.DIRETOR
    ]:
        context['solicitacoes'] = Solicitacao.objects.filter(
            colaborador__lotacao__in=request.user.lotacao.get_descendentes(include_self=True)
        ).order_by('-data')
    
    elif request.user.groups.filter(name='DP').exists() or request.user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        context['solicitacoes'] = Solicitacao.objects.all().order_by('-data')

    if request.htmx:
        return render(request, 'painel/colaborador/_content_solicitacoes.html', context)
    
    return render(request, 'painel/colaborador/solicitacoes.html', context)

@colaborador_required
def get_create_solicitacao_select_view(request):
    
    context = {
        'tipos_documento': TipoDocumento.objects.all(),
        'active_link': 'solicitacoes',
    }
    
    return render(request, 'partials/_solicitacao_create_select_doc.html', context)

@colaborador_required
def get_create_solicitacao_form_view(request, tipo_doc_id):
    tipo_doc = get_object_or_404(TipoDocumento, id=tipo_doc_id)
    
    try:
        if not tipo_doc.ativo():
            raise Exception("Documento indisponível ou fora do prazo de solicitação.")

        campos_json = copy.deepcopy(tipo_doc.definicao_formulario)
    
        for campo in campos_json:
            source = campo.get("options_source")
            
            if source == "colaboradores_lotacao":

                users = User.objects.filter(
                    lotacao=request.user.lotacao,
                    is_active=True
                ).exclude(id=request.user.id).order_by('first_name')

                campo['options'] = [
                    {'value': str(u.id), 'label': f"{u.first_name}"}
                    for u in users
                ]
                
        context = {
            'tipo_documento': tipo_doc,
            'campos_formulario': campos_json,
            'active_link': 'solicitacoes',
        }
        
        return render(request, 'partials/_solicitacao_create_form.html', context)
    
    except Exception as e:
        url_retry = reverse('colaborador:get_create_solicitacao_form', args=[tipo_doc_id])
        
        return render(request, 'partials/_message_error.html', {
            'message': f'Erro ao carregar o formulário: {e}',
            'url_retry': url_retry
        })

@colaborador_required
@require_POST 
def salvar_solicitacao_view(request, tipo_doc_id):
    tipo_doc = get_object_or_404(TipoDocumento, id=tipo_doc_id)
    schema_no_momento = tipo_doc.definicao_formulario
    
    valores_preenchidos = {}
    for campo in schema_no_momento:
        campo_nome = campo.get('name')
        if campo_nome:
            valores_preenchidos[campo_nome] = request.POST.get(campo_nome)

    dados_completos = {
        'schema': schema_no_momento,
        'values': valores_preenchidos
    }

    try:
        services.criar_solicitacao(
            colaborador=request.user,
            tipo_documento=tipo_doc,
            dados_preenchidos=dados_completos,
            esquema_formulario=schema_no_momento
        )

        msg = mark_safe('Solicitação enviada com sucesso!')
        
        response = render(request, 'partials/_message_sucess.html', {
            'message': msg
        })
        
        response['HX-Trigger'] = 'updateContent'
        
        return response

    except ValidationError as ve:
        url_retry = reverse('colaborador:get_create_solicitacao_form', args=[tipo_doc_id]) 
        
        msg_erro = "Erro de validação."
        if hasattr(ve, 'messages'):
            msg_erro = "<br>".join(ve.messages)
        elif hasattr(ve, 'message'):
            msg_erro = ve.message
        else:
            msg_erro = str(ve)

        return render(request, 'partials/_message_error.html', {
            'message': mark_safe(msg_erro),
            'url_retry': url_retry
        })

    except Exception as e:
        url_retry = reverse('colaborador:get_create_solicitacao_form', args=[tipo_doc_id])
        
        return render(request, 'partials/_message_error.html', {
            'message': f'Erro ao salvar: {e}',
            'url_retry': url_retry
        })

@colaborador_required
def get_solicitacao_detalhes_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    user = request.user
    
    pode_aprovar = False
    pode_aprovar = services._pode_ator_aprovar(solicitacao, user, request.user)
    campos_schema = copy.deepcopy(solicitacao.dados_preenchidos.get('schema', []))
    dados_preenchidos = solicitacao.dados_preenchidos.get('values', {})
    
    campos_com_valores = []
    
    colaboradores_query = User.objects.filter(
        lotacao=solicitacao.colaborador.lotacao
    ).exclude(
        id=solicitacao.colaborador.id
    ).order_by('first_name')

    opcoes_colaboradores = [
        {'value': str(c.id), 'label': f"{c.first_name}".strip() or c.username}
        for c in colaboradores_query
    ]

    for campo in campos_schema:
        campo_nome = campo.get('name')
        campo['value'] = dados_preenchidos.get(campo_nome) 
        
        if campo.get('options_source') == 'colaboradores_lotacao':
            campo['options'] = opcoes_colaboradores

        campos_com_valores.append(campo)
        
    context = {
        'solicitacao': solicitacao,
        'tipo_documento': solicitacao.tipo_documento,
        'campos_formulario': campos_com_valores,
        'pode_aprovar': pode_aprovar,
        'active_link': 'solicitacoes',
    }
    
    return render(request, 'partials/_solicitacao_detalhes.html', context)

@colaborador_required
def get_solicitacao_logs_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    logs = LogAprovacao.objects.filter(solicitacao=solicitacao).order_by('-data_acao')

    context = {
        'solicitacao': solicitacao,
        'logs': logs,
        'active_link': 'solicitacoes',
    }

    return render(request, 'partials/_solicitacao_detalhes_logs.html', context)
