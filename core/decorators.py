from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from .models import Cargo

def permission_required(test_func):
    def decorator(view_func):
        @wraps(view_func)
        @login_required(login_url='login')
        def _wrapped_view(request, *args, **kwargs):
            if not test_func(request.user):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def check_is_colaborador(user):
    has_no_cargo = not user.cargo
    is_padrao = user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.PADRAO
    
    return has_no_cargo or is_padrao

def check_is_aprovador(user):
    if not user.cargo:
        return False
        
    is_aprovador = user.cargo.hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR,
    ]
    
    return is_aprovador

def check_is_dp(user):
    is_dp_group = user.groups.filter(name='DP').exists()
    is_diretor = user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR
    
    return is_dp_group or is_diretor

colaborador_required = permission_required(check_is_colaborador)
aprovador_required = permission_required(check_is_aprovador)
dp_required = permission_required(check_is_dp)