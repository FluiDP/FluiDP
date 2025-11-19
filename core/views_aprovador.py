from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from .models import Solicitacao, Cargo
from .decorators import aprovador_required, is_aprovador_solicitacao

from . import services 

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
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
    }

    if request.htmx:
        return render(request, 'painel/aprovador/_content_home.html', context)
    
    return render(request, 'painel/aprovador/home.html', context)

@require_POST
@is_aprovador_solicitacao
def aprovar_solicitacao_view(request, solicitacao_id):
    """
    Chama o service.aprovar_solicitacao
    """
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    
    try:
        services.aprovar_solicitacao(solicitacao, ator=request.user)
        
        return HttpResponse("""
            <div class="p-6 bg-green-100 text-green-800 rounded-2xl text-center">
                <h3 class="text-xl font-bold">Solicitação Aprovada!</h3>
                <p>O status foi atualizado com sucesso.</p>
            </div>
        """)
        
    except (ValidationError, PermissionDenied) as e:
        return HttpResponse(f"""
            <div class="p-6 bg-yellow-50 text-yellow-800 rounded-2xl text-center border border-yellow-200">
                <h3 class="text-xl font-bold">Atenção</h3>
                <p>{e}</p>
            </div>
        """)
        
    except Exception as e:
        return HttpResponse(f"""
            <div class="p-6 bg-red-100 text-red-800 rounded-2xl text-center">
                <h3 class="text-xl font-bold">Erro no Sistema</h3>
                <p>Ocorreu um erro inesperado: {e}</p>
            </div>
        """)


@require_POST
@is_aprovador_solicitacao
def recusar_solicitacao_view(request, solicitacao_id):
    """
    Chama o service.recusar_solicitacao
    """
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    
    try:
        services.recusar_solicitacao(solicitacao, ator=request.user, detalhes="Recusado via Painel")

        return HttpResponse("""
            <div class="p-6 bg-red-100 text-red-800 rounded-2xl text-center">
                <h3 class="text-xl font-bold">Solicitação Recusada</h3>
                <p>A solicitação foi marcada como recusada.</p>
            </div>
        """)
        
    except Exception as e:
        return HttpResponse(f"""
            <div class="p-6 bg-red-100 text-red-800 rounded-2xl text-center">
                <h3 class="text-xl font-bold">Erro ao Recusar</h3>
                <p>{e}</p>
            </div>
        """)
