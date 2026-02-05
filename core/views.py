import datetime
from django.utils import timezone
from shutil import copy
import copy
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from core.views_colaborador import User
from .models import Cargo, CustomUser, Lotacao, Solicitacao
from django.contrib.auth import logout as auth_logout
from django.db.models import Count, Q

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

class CustomPasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'login/password_reset_done.html'

class CustomPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'login/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')

class CustomPasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = 'login/password_reset_complete.html'

def index_view(request):
    if request.user.is_authenticated:
        return redirect('painel')
    return redirect('login')

@login_required
def painel_view(request):
    
    hierarquia = request.user.cargo.hierarquia if request.user.cargo else Cargo.HierarquiaChoices.PADRAO

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
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
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
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
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
    """
    Exibe a solicitação em formato de impressão (HTML).
    A impressão para PDF é feita pelo navegador (Ctrl+P).
    """
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    
    campos_schema = copy.deepcopy(solicitacao.dados_preenchidos.get('schema', []))
    dados_valores = solicitacao.dados_preenchidos.get('values', {})
    
    campos_formatados = []
    
    colaboradores_lotacao = {
        str(u.id): f"{u.first_name}".strip() or u.username 
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

        if campo.get('type') == 'date' and valor_bruto:
            try:
                data_obj = datetime.datetime.strptime(valor_bruto, '%Y-%m-%d')
                valor_exibicao = data_obj.strftime('%d/%m/%Y')
            except ValueError:
                pass

        campo['valor_exibicao'] = valor_exibicao
        campos_formatados.append(campo)

    campos_rows = []
    for i in range(0, len(campos_formatados), 2):
        if campos_formatados[i].get('name') != "colaborador_substituto":
            campos_rows.append(campos_formatados[i:i+2])

    logs = solicitacao.logs.all().order_by('data_acao')

    context = {
        'solicitacao': solicitacao,
        'campos_rows': campos_rows,
        'logs': logs,
        'data_impressao': timezone.now(), 
        'usuario_impressao': request.user
    }

    return render(request, 'pdf/_report_solicitacao.html', context)

@login_required
def relatorio_geral_view(request):
    user = request.user
    
    minhas_lotacoes = set()
    q_lotacoes = Lotacao.objects.filter(
        Q(chefia=user) | Q(chefia_secundaria=user, chefia__isnull=True)
    )
    
    for lotacao in q_lotacoes:
        if not lotacao.arquivado:
            minhas_lotacoes.add(lotacao)
            minhas_lotacoes.update(lotacao.get_descendentes(include_self=True))

    if (user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR) or user.groups.filter(name='DP').exists():
        minhas_lotacoes = set(Lotacao.objects.filter(arquivado=False))

    hoje = timezone.now().date()
    padrao_inicio = hoje.replace(day=1)
    proximo_mes = (padrao_inicio.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    padrao_fim = proximo_mes - datetime.timedelta(days=1)
    
    data_inicio_str = request.GET.get('data_inicio', padrao_inicio.strftime('%Y-%m-%d'))
    data_fim_str = request.GET.get('data_fim', padrao_fim.strftime('%Y-%m-%d'))
    
    try:
        data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d')
        data_fim_base = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d')
        data_fim = data_fim_base.replace(hour=23, minute=59, second=59)
    except ValueError:
        data_inicio = datetime.datetime.combine(padrao_inicio, datetime.time.min)
        data_fim = datetime.datetime.combine(padrao_fim, datetime.time.max)

    qs_base = Solicitacao.objects.filter(
        colaborador__lotacao__in=minhas_lotacoes,
        arquivado=False,
        data__range=(data_inicio, data_fim)
    )

    docs_scoped = qs_base.values('tipo_documento__nome_documento')\
        .annotate(total=Count('id')).order_by('-total')[:5]
    
    lotacoes_scoped = qs_base.values('colaborador__lotacao__nome_lotacao')\
        .annotate(total=Count('id')).order_by('-total')[:5]

    ranking_data = []
    
    colab_ids = qs_base.values_list('colaborador', flat=True).distinct()
    colaboradores = CustomUser.objects.filter(id__in=colab_ids)
    
    for colab in colaboradores:
        qs_colab = qs_base.filter(colaborador=colab)
        total = qs_colab.count()
        
        top_tipos = qs_colab.values('tipo_documento__nome_documento')\
            .annotate(qtd=Count('id'))\
            .order_by('-qtd')
            
        lista_textos = [f"{t['tipo_documento__nome_documento']} ({t['qtd']})" for t in top_tipos]
        texto_principais = ", ".join(lista_textos)
        
        ranking_data.append({
            'colaborador': colab,
            'total': total,
            'texto_principais': texto_principais
        })
    
    ranking_data.sort(key=lambda x: x['total'], reverse=True)
    
    for idx, item in enumerate(ranking_data, 1):
        item['posicao'] = idx

    context = {
        'ranking_data': ranking_data,
        'data_inicio': data_inicio_str,
        'data_fim': data_fim_str,
        'chart_docs_labels': [x['tipo_documento__nome_documento'] for x in docs_scoped],
        'chart_docs_data': [x['total'] for x in docs_scoped],
        'chart_lot_labels': [x['colaborador__lotacao__nome_lotacao'] for x in lotacoes_scoped],
        'chart_lot_data': [x['total'] for x in lotacoes_scoped],
        'data_impressao': timezone.now()
    }

    return render(request, 'pdf/_report_geral.html', context)
