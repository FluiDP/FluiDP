from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from .models import Cargo, Solicitacao

def permission_required(test_func):
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url='login')
        def _wrapped_view(request, *args, **kwargs):
            if not test_func(request, **kwargs):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def check_is_aprovador(request, **kwargs):
    user = request.user
    if not user.cargo:
        return False
    return user.cargo.hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR,
        Cargo.HierarquiaChoices.DIRETOR
    ]

def check_is_colaborador(request, **kwargs):
    user = request.user
    has_no_cargo = not user.cargo
    is_padrao = user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.PADRAO
    # CORREÇÃO: Chamando a função corretamente
    return has_no_cargo or is_padrao or check_is_aprovador(request, **kwargs)

def check_is_dp(request, **kwargs):
    user = request.user
    return user.groups.filter(name='DP').exists()

def check_is_system_admin(request, **kwargs):
    user = request.user
    return user.groups.filter(name='SYSTEM_ADMIN').exists()

# CORREÇÃO: Função dedicada para unir DP, Admin e Gestores (Para a view não bloquear gestores)
def check_dp_or_admin(request, **kwargs):
    return check_is_dp(request, **kwargs) or check_is_system_admin(request, **kwargs)

def check_aprove_permission(request, **kwargs):
    user = request.user
    
    solicitacao_id = kwargs.get('solicitacao_id')
    if not solicitacao_id:
        return False

    try:
        solicitacao = Solicitacao.objects.get(id=solicitacao_id)
    except Solicitacao.DoesNotExist:
        return False
    
    if (solicitacao.status == Solicitacao.StatusChoices.PENDENTE_ACEITE_SECUNDARIO and
        solicitacao.colaborador_secundario == user):
        return True

    elif (solicitacao.status == Solicitacao.StatusChoices.PENDENTE_GESTOR and
          solicitacao.aprovador_atual == user):
        return True
    
    elif (solicitacao.status == Solicitacao.StatusChoices.PENDENTE_DIRETOR and
          user.cargo and 
          user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR):
        return True

    elif ((solicitacao.status in [Solicitacao.StatusChoices.PENDENTE_DP, Solicitacao.StatusChoices.LANCAMENTO]) and
          user.groups.filter(name='DP').exists()):
        return True
        
    return False

# Inicialização dos decorators
colaborador_required = permission_required(check_is_colaborador)
aprovador_required = permission_required(check_is_aprovador)
system_admin_required = permission_required(check_is_system_admin)
is_aprovador_solicitacao = permission_required(check_aprove_permission)

# CORREÇÃO: Utilizando a função unida que avalia corretamente e permite gestores
dp_required = permission_required(check_dp_or_admin)