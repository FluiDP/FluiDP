from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from .models import Cargo, Solicitacao, TipoDocumento, CustomUser, Lotacao
from django.db.models import Q
from .decorators import dp_required
from .forms import LotacaoForm, CargoForm
from django.urls import reverse

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

    if request.user.cargo and request.user.cargo.hierarquia in [
        Cargo.HierarquiaChoices.DIRETOR
    ]:
        q_solicitacoes_pendentes = q_solicitacoes_pendentes | Q(status=Solicitacao.StatusChoices.PENDENTE_DIRETOR)
    else:
        q_solicitacoes_pendentes = q_solicitacoes_pendentes | Q(status=Solicitacao.StatusChoices.PENDENTE_DP)

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
            q_solicitacoes_pendentes
        )
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_home.html', context)
    
    return render(request, 'painel/dp/home.html', context)

@dp_required
def dp_lotacoes_view(request):
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        'lotacoes': Lotacao.objects.all().order_by('nome_lotacao'),
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_lotacoes.html', context)
    
    return render(request, 'painel/dp/lotacoes.html', context)

@dp_required
def dp_colaboradores_view(request):
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        'colaboradores': CustomUser.objects.all().order_by('first_name'),
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_colaboradores.html', context)
    
    return render(request, 'painel/dp/colaboradores.html', context)

@dp_required
def dp_documentos_view(request):
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        'documentos': TipoDocumento.objects.all().order_by('nome_documento'),
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_documentos.html', context)
    
    return render(request, 'painel/dp/documentos.html', context)

@dp_required
def dp_cargos_view(request):
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        'cargos': Cargo.objects.all().order_by('hierarquia', 'nome_cargo'),
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_cargos.html', context)
    
    return render(request, 'painel/dp/cargos.html', context)

@dp_required
def dp_solicitacoes_view(request):
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        
        'solicitacoes': Solicitacao.objects.all().order_by('-data'),
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_solicitacoes.html', context)
    
    return render(request, 'painel/dp/solicitacoes.html', context)

@dp_required
def updated_list_solicitacoes(request):
    
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
        
        'solicitacoes': Solicitacao.objects.all().order_by('-data'),
    }

    return render(request, 'partials/_solicitacoes_rows.html', context)

@dp_required
def create_lotacao_model_view(request):
    form = LotacaoForm(request.POST or None)
    success_message = None

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        success_message = f"Lotação <strong>{obj.nome_lotacao}</strong> criada!"
        form = None

    context = {
        'form': form,
        'modal_title': 'Nova Lotação',
        'action_url': reverse('dp:create_lotacao'),
        'submit_text': 'Salvar Lotação',
        'success_message': success_message
    }

    return render(request, 'partials/_generic_create_form.html', context)

@dp_required
def create_cargo_model_view(request):
    form = CargoForm(request.POST or None)
    success_message = None

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        success_message = f"Cargo <strong>{obj.nome_cargo}</strong> criado com sucesso!"
        form = None

    context = {
        'form': form,
        'modal_title': 'Novo Cargo',
        'action_url': reverse('dp:create_cargo'),
        'submit_text': 'Salvar Cargo',
        'success_message': success_message
    }

    return render(request, 'partials/_generic_create_form.html', context)
