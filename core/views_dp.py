from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.urls import reverse
from django.http import HttpResponse

from .models import Cargo, Solicitacao, TipoDocumento, CustomUser, Lotacao
from .decorators import dp_required
from .forms import LotacaoForm, CargoForm


@dp_required
def dp_painel_view(request):
    
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

    if request.user.cargo and request.user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        q_solicitacoes_pendentes = q_solicitacoes_pendentes | Q(status=Solicitacao.StatusChoices.PENDENTE_DIRETOR)
    else:
        q_solicitacoes_pendentes = q_solicitacoes_pendentes | Q(status=Solicitacao.StatusChoices.PENDENTE_DP)

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        
        'solicitacoes': Solicitacao.objects.filter(q_usuario_envolvido).distinct().order_by('-data'),
        'solicitacoes_ativas': Solicitacao.objects.filter(colaborador=request.user, status__in=status_pendentes_ativos).distinct().order_by('-data'),
        'solicitacoes_pendentes': Solicitacao.objects.filter(q_solicitacoes_pendentes).distinct().order_by('-data')
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_home.html', context)
    
    return render(request, 'painel/dp/home.html', context)

@dp_required
def dp_lotacoes_view(request):
    """View Principal: Carrega a página completa de lotações"""
    lotacoes = Lotacao.objects.all().order_by('nome_lotacao')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'lotacoes': lotacoes,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_lotacoes.html', context)
    
    return render(request, 'painel/dp/lotacoes.html', context)

@dp_required
def lotacoes_list_view(request):
    """View Parcial: Retorna apenas as linhas <tr> para a tabela (Busca/Update)"""
    lotacoes = Lotacao.objects.all().order_by('nome_lotacao')
    
    q = request.GET.get('q')
    if q:
        lotacoes = lotacoes.filter(nome_lotacao__icontains=q)

    return render(request, 'painel/dp/_partial_list_lotacoes.html', {'lotacoes': lotacoes})

@dp_required
def create_lotacao_model_view(request):
    """View Modal: Criação com Trigger de Atualização e Feedback visual"""
    form = LotacaoForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        
        response = render(request, 'partials/_message_sucess.html', {
            'message': f"Lotação <strong>{obj.nome_lotacao}</strong> criada com sucesso!"
        })
        response['HX-Trigger'] = 'updateLotacoesList'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Nova Lotação',
        'action_url': reverse('dp:create_lotacao'),
        'submit_text': 'Salvar Lotação',
    })

@dp_required
def dp_cargos_view(request):
    cargos = Cargo.objects.all().order_by('hierarquia', 'nome_cargo')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'cargos': cargos,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_cargos.html', context)
    
    return render(request, 'painel/dp/cargos.html', context)

@dp_required
def cargos_list_view(request):
    """View Parcial: Linhas da tabela de Cargos"""
    cargos = Cargo.objects.all().order_by('hierarquia', 'nome_cargo')
    
    q = request.GET.get('q')
    if q:
        cargos = cargos.filter(nome_cargo__icontains=q)

    return render(request, 'painel/dp/_partial_list_cargos.html', {'cargos': cargos})

@dp_required
def create_cargo_model_view(request):
    form = CargoForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        
        response = render(request, 'partials/_message_sucess.html', {
            'message': f"Cargo <strong>{obj.nome_cargo}</strong> criado com sucesso!"
        })
        response['HX-Trigger'] = 'updateCargosList'
        return response

    return render(request, 'partials/_generic_create_form.html', {
        'form': form,
        'modal_title': 'Novo Cargo',
        'action_url': reverse('dp:create_cargo'),
        'submit_text': 'Salvar Cargo',
    })

@dp_required
def dp_colaboradores_view(request):
    colaboradores = CustomUser.objects.all().order_by('first_name')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'colaboradores': colaboradores,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_colaboradores.html', context)
    
    return render(request, 'painel/dp/colaboradores.html', context)

@dp_required
def colaboradores_list_view(request):
    """View Parcial: Linhas da tabela de Colaboradores"""
    colaboradores = CustomUser.objects.all().order_by('first_name')
    
    q = request.GET.get('q')
    if q:
        colaboradores = colaboradores.filter(
            Q(first_name__icontains=q) | 
            Q(email__icontains=q) | 
            Q(matricula__icontains=q)
        )

    return render(request, 'painel/dp/_partial_list_colaboradores.html', {'colaboradores': colaboradores})

@dp_required
def dp_documentos_view(request):
    documentos = TipoDocumento.objects.all().order_by('nome_documento')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'documentos': documentos,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_documentos.html', context)
    
    return render(request, 'painel/dp/documentos.html', context)

@dp_required
def documentos_list_view(request):
    """View Parcial: Linhas da tabela de Documentos"""
    documentos = TipoDocumento.objects.all().order_by('nome_documento')
    
    q = request.GET.get('q')
    if q:
        documentos = documentos.filter(nome_documento__icontains=q)

    return render(request, 'painel/dp/_partial_list_documentos.html', {'documentos': documentos})

@dp_required
def dp_solicitacoes_view(request):
    solicitacoes = Solicitacao.objects.all().order_by('-data')
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name,
        'solicitacoes': solicitacoes,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_solicitacoes.html', context)
    
    return render(request, 'painel/dp/solicitacoes.html', context)

@dp_required
def solicitacoes_list_view(request):
    """View Parcial: Linhas da tabela de Solicitações (Atualização e Busca)"""
    solicitacoes = Solicitacao.objects.all().order_by('-data')
    
    q = request.GET.get('q')
    if q:
        solicitacoes = solicitacoes.filter(
            Q(colaborador__first_name__icontains=q) | 
            Q(tipo_documento__nome_documento__icontains=q)
        )

    return render(request, 'painel/dp/_partial_list_solicitacoes.html', {'solicitacoes': solicitacoes})
