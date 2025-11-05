from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from .models import Cargo
from .decorators import colaborador_required

@colaborador_required
def colaborador_painel_view(request):
    has_no_cargo = not request.user.cargo
    is_padrao = request.user.cargo and request.user.cargo.hierarquia == Cargo.HierarquiaChoices.PADRAO

    if not (has_no_cargo or is_padrao):
        raise PermissionDenied

    context = {
        'usuario': request.user,
    }

    if request.htmx:
        return render(request, 'painel/colaborador/_content_home.html', context)
    
    return render(request, 'painel/colaborador/home.html', context)

@colaborador_required
def colaborador_solicitacoes_view(request):
    context = {
        'usuario': request.user,
    }

    if request.htmx:
        return render(request, 'painel/colaborador/_content_solicitacoes.html', context)
    
    return render(request, 'painel/colaborador/solicitacoes.html', context)
