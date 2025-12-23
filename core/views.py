from django.utils import timezone
from django.utils.text import slugify
from shutil import copy
import copy
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from core.views_colaborador import User
from .models import Cargo, Solicitacao
from django.contrib.auth import logout as auth_logout
from xhtml2pdf import pisa

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
    
    hierarquia = request.user.cargo.hierarquia

    if request.user.groups.filter(name='DP').exists() or hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        return redirect('administracao:dashboard')

    elif hierarquia in [
        Cargo.HierarquiaChoices.GERENTE,
        Cargo.HierarquiaChoices.COORDENADOR
    ]:
        return redirect('gestor:home')
    
    else:
        return redirect('colaborador:home')

@login_required
def perfil_view(request):
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
    }

    hierarquia = Cargo.objects.get(id=request.user.cargo.id).hierarquia

    if request.htmx:
        return render(request, 'painel/_content_perfil.html', context)

    if request.user.groups.filter(name='DP').exists() or hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        return render(request, 'painel/dp/perfil.html', context)

    if hierarquia in [2, 3]:
        return render(request, 'painel/colaborador/perfil.html', context)

    if hierarquia == 4:
        return render(request, 'painel/colaborador/perfil.html', context)
        
    return redirect('painel')

@login_required
def logout_view(request):
    auth_logout(request)
    return redirect('login')

@login_required
def indisponibilidade_view(request):
    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[-1] if request.user.first_name else request.user.username,
    }

    hierarquia = Cargo.objects.get(id=request.user.cargo.id).hierarquia

    if request.htmx:
        return render(request, 'painel/_content_indisponibilidade.html', context)

    if request.user.groups.filter(name='DP').exists() or hierarquia == Cargo.HierarquiaChoices.DIRETOR:
        return render(request, 'painel/dp/indisponibilidade.html', context)

    if hierarquia in [2, 3]:
        return render(request, 'painel/colaborador/indisponibilidade.html', context)
    
    if hierarquia == 4:
        return render(request, 'painel/colaborador/indisponibilidade.html', context)

    return redirect('painel')

@login_required
def gerar_pdf_solicitacao_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    
    campos_schema = copy.deepcopy(solicitacao.dados_preenchidos.get('schema', []))
    dados_valores = solicitacao.dados_preenchidos.get('values', {})
    
    campos_formatados = []
    
    colaboradores_lotacao = {
        str(u.id): f"{u.first_name} {u.last_name or ''}".strip() or u.username 
        for u in User.objects.filter(lotacao=solicitacao.colaborador.lotacao)
    }

    for campo in campos_schema:
        nome_campo = campo.get('name')
        valor_bruto = dados_valores.get(nome_campo)
        valor_exibicao = valor_bruto

        if campo.get('type') in ['select', 'radio']:
            if campo.get('options_source') == 'colaboradores_lotacao':
                valor_exibicao = colaboradores_lotacao.get(str(valor_bruto), valor_bruto)
            elif 'options' in campo:
                for opcao in campo['options']:
                    if str(opcao['value']) == str(valor_bruto):
                        valor_exibicao = opcao['label']
                        break
        
        if campo.get('type') == 'checkbox':
            valor_exibicao = "Sim" if valor_bruto else "Não"

        campo['valor_exibicao'] = valor_exibicao
        campos_formatados.append(campo)

    logs = solicitacao.logs.all().order_by('data_acao')

    campos_rows = []
    for i in range(0, len(campos_formatados), 2):
        campos_rows.append(campos_formatados[i:i+2])

    context = {
        'solicitacao': solicitacao,
        'campos_rows': campos_rows,
        'logs': logs,
        'data_impressao': timezone.now(), 
        'usuario_impressao': request.user
    }

    html_string = render_to_string('pdf/_report_solicitacao.html', context)
    response = HttpResponse(content_type='application/pdf')
    
    data_str = solicitacao.data.strftime('%Y-%m-%d')

    nome_colab = slugify(solicitacao.colaborador.first_name)
    tipo_doc = slugify(solicitacao.tipo_documento.nome_documento)
    filename = f"{data_str}_{nome_colab}_{tipo_doc}.pdf"
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    pisa_status = pisa.CreatePDF(html_string, dest=response)

    if pisa_status.err:
       return HttpResponse('Ocorreu um erro ao gerar o PDF <pre>' + html_string + '</pre>')
    
    return response
