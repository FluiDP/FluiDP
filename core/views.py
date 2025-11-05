from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.shortcuts import redirect
from .models import Cargo
from django.contrib.auth import logout as auth_logout

class CustomLoginView(auth_views.LoginView):
    template_name = 'login/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('painel')

def index_view(request):
    if request.user.is_authenticated:
        return redirect('painel')
    return redirect('login')

@login_required
def painel_view(request):
    if not request.user.cargo:
        return redirect('colaborador:home') 

    hierarquia = request.user.cargo.hierarquia

    if request.user.groups.filter(name='DP').exists() or hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        return redirect('dp:home')

    if hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR
    ]:
        return redirect('aprovador:home')

    return redirect('colaborador:home')

def logout_view(request):
    auth_logout(request)
    return redirect('login')
