from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from .models import Cargo
from .decorators import dp_required

@dp_required
def dp_painel_view(request):
    is_dp = request.user.groups.filter(name='DP').exists()
    is_diretor = request.user.cargo and request.user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR

    if not (is_dp or is_diretor):
        raise PermissionDenied

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
    }

    if request.htmx:
        return render(request, 'painel/dp/_content_home.html', context)
    
    return render(request, 'painel/dp/home.html', context)
