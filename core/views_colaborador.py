from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from .models import Cargo, Solicitacao, TipoDocumento, Lotacao
from .decorators import colaborador_required
from . import services
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.contrib.auth import get_user_model

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

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        
        'solicitacoes': Solicitacao.objects.filter(
            colaborador=q_usuario_envolvido
        ).distinct(),
        
        'solicitacoes_ativas': Solicitacao.objects.filter(
            colaborador=request.user,
            status__in=status_pendentes_ativos
        ).distinct(),
        
        'solicitacoes_pendentes': Solicitacao.objects.filter(
            status=Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO,
            colaborador_secundario=request.user
        )
    }

    if request.htmx:
        return render(request, 'painel/colaborador/_content_home.html', context)
    
    return render(request, 'painel/colaborador/home.html', context)

@colaborador_required
def colaborador_solicitacoes_view(request):

    q_usuario_envolvido = Q(colaborador=request.user) | Q(colaborador_secundario=request.user)

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        
        'solicitacoes': Solicitacao.objects.filter(
            q_usuario_envolvido
        ).distinct(),
    }

    if request.htmx:
        return render(request, 'painel/colaborador/_content_solicitacoes.html', context)
    
    return render(request, 'painel/colaborador/solicitacoes.html', context)

@colaborador_required
def get_create_solicitacao_select_view(request):
    
    context = {
        'tipos_documento': TipoDocumento.objects.all(),
    }
    
    return render(request, 'partials/_create_select_doc.html', context)

@colaborador_required
def get_create_solicitacao_form_view(request, tipo_doc_id):
    tipo_doc = get_object_or_404(TipoDocumento, id=tipo_doc_id)
    campos_json = tipo_doc.definicao_formulario
    
    colaboradores = None

    for campo in campos_json:
        source = campo.get("options_source")
        
        if source == "colaboradores_lotacao":
            q_filtro = Q(lotacao=request.user.lotacao) | Q(cargo=request.user.cargo)
            
            colaboradores = User.objects.filter(
                q_filtro
            ).exclude(
                id=request.user.id
            ).filter(
                is_active=True
            ).distinct().order_by('first_name')

    context = {
        'tipo_documento': tipo_doc,
        'campos_formulario': campos_json,
        'colaboradores_lotacao': colaboradores 
    }
    
    return render(request, 'partials/_create_form.html', context)


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

        return HttpResponse('<div class="p-4 bg-green-100 text-green-800 rounded-lg border border-green-200">Solicitação enviada com sucesso!</div>')

    except ValidationError as ve:
        return HttpResponse(f'<div class="p-4 bg-yellow-50 text-yellow-800 rounded-lg border border-yellow-200">Atenção: {ve.message}</div>')

    except Exception as e:
        return HttpResponse(f'<div class="p-4 bg-red-100 text-red-800 rounded-lg border border-red-200">Erro ao salvar: {e}</div>')

@colaborador_required
def get_solicitacao_detalhes_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    user = request.user
    
    pode_aprovar = False
    pode_aprovar = services._pode_ator_aprovar(solicitacao, user)
    campos_schema = solicitacao.dados_preenchidos.get('schema', [])
    dados_preenchidos = solicitacao.dados_preenchidos.get('values', {})
    
    campos_com_valores = []
    
    colaboradores_query = User.objects.filter(
        lotacao=solicitacao.colaborador.lotacao
    ).exclude(
        id=solicitacao.colaborador.id
    ).order_by('first_name')

    opcoes_colaboradores = [
        {'value': str(c.id), 'label': f"{c.first_name} {c.last_name or ''}".strip() or c.username} 
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
        'pode_aprovar': pode_aprovar
    }
    
    return render(request, 'partials/_solicitacao_detalhes.html', context)

@colaborador_required
def colaborador_perfil_view(request):
    context = {
        'colaborador': request.user
    }

    return render(request, 'painel/colaborador/perfil.html')
