from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.shortcuts import redirect, render
from .models import Cargo
from django.contrib.auth import logout as auth_logout

class CustomLoginView(auth_views.LoginView):
    template_name = 'login/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('painel')

class CustomPasswordResetView(auth_views.PasswordResetView):
    template_name = 'login/reset.html'
    html_email_template_name = 'emails/_reset_password.html'
    subject_template_name = 'emails/_reset_password_subject.txt'
    success_url = reverse_lazy('login')

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

@login_required
def perfil_view(request):
    context = {
        'usuario': request.user,
    }

    if request.htmx:
        return render(request, 'painel/_content_perfil.html', context)

    if not request.user.cargo:
        return render(request, 'painel/colaborador/perfil.html', context)

    hierarquia = request.user.cargo.hierarquia

    if hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR
    ]:
        return render(request, 'painel/aprovador/perfil.html', context)

    if request.user.groups.filter(name='DP').exists() or hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        return render(request, 'painel/dp/perfil.html', context)
        
    return redirect('painel')

def logout_view(request):
    auth_logout(request)
    return redirect('login')
