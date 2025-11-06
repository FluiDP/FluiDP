from django.core.exceptions import PermissionDenied
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.shortcuts import render
from .models import Cargo
from .decorators import aprovador_required

@aprovador_required
def aprovador_painel_view(request):
    is_aprovador = request.user.cargo and request.user.cargo.hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR,
    ]

    if not is_aprovador:
        raise PermissionDenied
    
    context = {
        'usuario': request.user,
    }

    if request.htmx:
        return render(request, 'painel/aprovador/_content_home.html', context)
    
    return render(request, 'painel/aprovador/home.html', context)
