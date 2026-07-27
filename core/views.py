import datetime
import os
from pathlib import Path
from shutil import copy
import copy
import re

import dotenv
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_POST

from core import services
from core.services import get_config, set_config
from .decorators import dp_required
from .models import Cargo, CustomUser, Lotacao, Solicitacao
from .forms import CustomPasswordResetForm

User = get_user_model()
BASE_DIR = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)

def is_mobile(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    mobile_keywords = r'mobile|android|iphone|ipad|ipod|windows phone'
    return bool(re.search(mobile_keywords, user_agent))

class CustomLoginView(auth_views.LoginView):
    template_name = 'login/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('painel')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        env_path = BASE_DIR / '.env'
        if env_path.exists():
            dotenv.load_dotenv(env_path)
        instituicao_nome = os.environ.get('INSTITUICAO_NOME', 'FluiDP')
        context['instituicao'] = instituicao_nome
        return context

class CustomPasswordResetView(auth_views.PasswordResetView):
    template_name = 'login/reset.html'
    form_class = CustomPasswordResetForm
    html_email_template_name = 'emails/_reset_password.html'
    subject_template_name = 'emails/_reset_password_subject.txt'
    success_url = reverse_lazy('login')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tema'] = get_config() 
        return context

    def form_valid(self, form):
        self.extra_email_context = {
            'tema': get_config()
        }
        return super().form_valid(form)

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

    if request.user.groups.filter(name='DP').exists() or request.user.groups.filter(name='SYSTEM_ADMIN').exists():
        return redirect('administracao:dashboard')
    elif hierarquia in [Cargo.HierarquiaChoices.GERENTE, Cargo.HierarquiaChoices.COORDENADOR, Cargo.HierarquiaChoices.DIRETOR]:
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

@require_POST
@login_required
def processar_lote_solicitacoes_view(request):
    user = request.user
    is_dp = user.groups.filter(name='DP').exists()
    is_diretor = user.cargo and user.cargo.hierarquia == Cargo.HierarquiaChoices.DIRETOR
    
    if not (is_dp or is_diretor):
        raise PermissionDenied("Você não possui permissão para executar ações em lote.")

    solicitacao_ids = request.POST.getlist('solicitacoes_ids')
    action = request.GET.get('acao') or request.POST.get('action_lote')

    if not solicitacao_ids:
        return render(request, 'partials/_message_error.html', {'message': 'Nenhuma solicitação foi selecionada.'})
    if action not in ['aprovar', 'recusar']:
        return render(request, 'partials/_message_error.html', {'message': 'Ação de lote inválida.'})

    sucessos = 0
    erros = 0

    for sig_id in solicitacao_ids:
        try:
            solicitacao = Solicitacao.objects.get(id=sig_id)
            if action == 'aprovar':
                services.aprovar_solicitacao(solicitacao, ator=user, request_user=user, detalhes="Aprovado via Painel")
            elif action == 'recusar':
                services.recusar_solicitacao(solicitacao, ator=user, detalhes="Recusado via Painel")
            sucessos += 1
        except Exception:
            erros += 1

    if sucessos > 0:
        msg = f"{sucessos} solicitações processadas com sucesso."
        if erros > 0:
            msg += f" ({erros} ignoradas por restrição de status ou permissão)."
        response = render(request, 'partials/_message_sucess.html', {'message': msg})
    else:
        msg = f"Nenhuma solicitação processada ({erros} falharam por restrição de status ou permissão)."
        response = render(request, 'partials/_message_error.html', {'message': msg})

    response['HX-Trigger'] = 'updateContent'
    return response

@dp_required
def config_view(request):
    config = get_config()
    nome_instituicao = config.nome_instituicao or "FluiDP"
    primary_color = config.primary_color
    secondary_color = config.secondary_color
    emphasis_color = config.emphasis_color
    logo = config.logo.url if config.logo else None

    context = {
        'usuario': request.user,
        'usuario_tagname': request.user.first_name.split()[0] if request.user.first_name else request.user.username,
        'primary_color': primary_color,
        'secondary_color': secondary_color,
        'emphasis_color': emphasis_color,
        'logo': logo,
        'nome_instituicao': nome_instituicao
    }

    if request.htmx:
        return render(request, 'painel/_content_config.html', context)
    return render(request, 'painel/dp/config.html', context)

@dp_required
def save_config_view(request):
    if request.method == 'POST':
        nome_instituicao = request.POST.get('nome_instituicao')
        primary_color = request.POST.get('primary_color')
        secondary_color = request.POST.get('secondary_color')
        emphasis_color = request.POST.get('emphasis_color')
        logo_file = request.FILES.get('logo') or None

        set_config(nome_instituicao, primary_color, secondary_color, emphasis_color, logo_file)
        config = get_config()
        
        context = {
            'primary_color': config.primary_color,
            'secondary_color': config.secondary_color,
            'emphasis_color': config.emphasis_color,
            'logo': config.logo.url if config.logo else None,
            'nome_instituicao': config.nome_instituicao,
            'sucesso': True 
        }

        if request.htmx:
            return render(request, 'painel/_content_config.html', context)
    return redirect('config')

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

    total_minutos_extras = 0
    total_minutos_compensados = 0

    def time_str_to_minutes(t_str):
        if isinstance(t_str, str) and ':' in t_str:
            try:
                t_str = t_str.replace('-', '').strip()
                h, m = t_str.split(':')
                return (int(h) * 60) + int(m)
            except ValueError:
                return 0
        return 0

    def minutes_to_time_str(mins):
        h = mins // 60
        m = mins % 60
        return f"{h:02d}:{m:02d}"

    for sol in qs_base:
        if sol.status == Solicitacao.StatusChoices.FINALIZADO:
            dados = sol.dados_preenchidos
            valores = dados.get('values', dados) if isinstance(dados, dict) else {}
            schema = dados.get('schema', []) if isinstance(dados, dict) else []
            
            if isinstance(valores, dict) and isinstance(schema, list):
                calc_time_fields = [
                    campo for campo in schema 
                    if campo.get('type') == 'calculated' and campo.get('calc_format') == 'time'
                ]
                nome_documento = sol.tipo_documento.nome_documento.lower()
                
                if len(calc_time_fields) == 2:
                    val1_str = valores.get(calc_time_fields[0].get('name'), '00:00')
                    val2_str = valores.get(calc_time_fields[1].get('name'), '00:00')
                    mins1 = time_str_to_minutes(val1_str)
                    mins2 = time_str_to_minutes(val2_str)
                    minutos_compensados_doc = min(mins1, mins2)
                    total_minutos_compensados += minutos_compensados_doc

                elif len(calc_time_fields) == 1:
                    campo = calc_time_fields[0]
                    nome_campo = campo.get('name', '').lower()
                    label_campo = campo.get('label', '').lower()
                    valor_str = valores.get(nome_campo, '00:00')
                    minutos = time_str_to_minutes(valor_str)
                    
                    if minutos > 0:
                        if 'compensa' in nome_campo or 'compensa' in label_campo or 'banco' in nome_documento:
                            total_minutos_compensados += minutos
                        elif 'extra' in nome_campo or 'extra' in label_campo or 'ocorrencia' in nome_campo:
                            total_minutos_extras += minutos

    horas_extras_formatadas = minutes_to_time_str(total_minutos_extras)
    horas_compensadas_formatadas = minutes_to_time_str(total_minutos_compensados)

    docs_scoped = qs_base.values('tipo_documento__nome_documento').annotate(total=Count('id')).order_by('-total')[:5]
    lotacoes_scoped = qs_base.values('colaborador__lotacao__nome_lotacao').annotate(total=Count('id')).order_by('-total')[:5]

    ranking_data = []
    colab_ids = qs_base.values_list('colaborador', flat=True).distinct()
    colaboradores = CustomUser.objects.filter(id__in=colab_ids)
    
    for colab in colaboradores:
        qs_colab = qs_base.filter(colaborador=colab)
        total = qs_colab.count()
        top_tipos = qs_colab.values('tipo_documento__nome_documento').annotate(qtd=Count('id')).order_by('-qtd')
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
        'data_impressao': timezone.now(),
        'horas_extras': horas_extras_formatadas,
        'horas_compensadas': horas_compensadas_formatadas
    }
    return render(request, 'pdf/_report_geral.html', context)

# ==========================================
# VIEWS GENÉRICAS DE SOLICITAÇÕES
# ==========================================

@login_required
def edit_solicitacao_modal_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    user = request.user

    is_autor = solicitacao.colaborador == user
    is_dp = user.groups.filter(name='DP').exists() or user.is_superuser

    pode_editar_como_autor = is_autor and solicitacao.can_edit(user)
    pode_editar_como_dp = is_dp and solicitacao.can_edit_dp(user)

    if not (pode_editar_como_autor or pode_editar_como_dp):
        return render(request, 'partials/_message_error.html', {
            'message': 'Você não tem permissão para editar esta solicitação no status atual.'
        })

    tipo_doc = solicitacao.tipo_documento
    schema = solicitacao.dados_preenchidos.get('schema', tipo_doc.definicao_formulario)

    if request.method == 'POST':
        if pode_editar_como_autor:
            novos_valores = {}
            for campo in schema:
                campo_nome = campo.get('name')
                campo_tipo = campo.get('type')
                if campo_nome:
                    if campo_tipo == 'repeater':
                        lista_final_objetos = []
                        sub_campos = campo.get('sub_fields', [])
                        dados_crus = {}
                        qtd_linhas = 0

                        for sub in sub_campos:
                            chave_post = f"{campo_nome}_{sub['name']}[]"
                            valores_lista = request.POST.getlist(chave_post)
                            dados_crus[sub['name']] = valores_lista
                            if len(valores_lista) > qtd_linhas:
                                qtd_linhas = len(valores_lista)

                        for i in range(qtd_linhas):
                            linha_obj = {}
                            for sub in sub_campos:
                                lista_valores = dados_crus.get(sub['name'], [])
                                valor = lista_valores[i] if i < len(lista_valores) else ""
                                linha_obj[sub['name']] = valor
                            lista_final_objetos.append(linha_obj)

                        novos_valores[campo_nome] = lista_final_objetos
                    else:
                        novos_valores[campo_nome] = request.POST.get(campo_nome)

        elif pode_editar_como_dp:
            novos_valores = dict(solicitacao.dados_preenchidos.get('values', {}))
            for campo in schema:
                if campo.get('type') == 'calculated':
                    nome_campo = campo.get('name')
                    if nome_campo in request.POST:
                        novos_valores[nome_campo] = request.POST.get(nome_campo)

        try:
            services.editar_solicitacao(
                solicitacao=solicitacao,
                ator=user,
                novos_valores=novos_valores
            )
            msg = mark_safe('Solicitação <span class="font-bold">atualizada</span> com sucesso!')
            response = render(request, 'partials/_message_sucess.html', {'message': msg})
            response['HX-Trigger'] = 'updateContent'
            return response
        except ValidationError as ve:
            msg_erro = ve.message if hasattr(ve, 'message') else str(ve)
            return render(request, 'partials/_message_error.html', {'message': mark_safe(msg_erro)})
        except PermissionError as pe:
            return render(request, 'partials/_message_error.html', {'message': str(pe)})
        except Exception as e:
            return render(request, 'partials/_message_error.html', {'message': f'Erro ao editar: {e}'})

    dados_valores = solicitacao.dados_preenchidos.get('values', {})

    if pode_editar_como_dp and not pode_editar_como_autor:
        campos_formulario = []
        for campo in schema:
            if campo.get('type') == 'calculated':
                campo_name = campo.get('name')
                campo['value'] = dados_valores.get(campo_name)
                campos_formulario.append(campo)
        template_name = 'partials/_dp_solicitacao_edit_form.html'
    else:
        campos_formulario = []
        for campo in schema:
            campo_name = campo.get('name')
            campo['value'] = dados_valores.get(campo_name)
            campos_formulario.append(campo)
        template_name = 'partials/_solicitacao_edit_form.html'

    context = {
        'solicitacao': solicitacao,
        'tipo_documento': tipo_doc,
        'campos_formulario': campos_formulario,
        'campos_exclusivos_dp': campos_formulario,
        'action_url': reverse('edit_solicitacao_modal', args=[solicitacao.id])
    }
    return render(request, template_name, context)


@require_POST
@login_required
def cancelar_solicitacao_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    detalhes = request.POST.get('detalhes', '').strip()

    try:
        services.cancelar_solicitacao(solicitacao, request.user, detalhes)
        msg = mark_safe('Solicitação <span class="font-bold">cancelada</span> com sucesso.')
        response = render(request, 'partials/_message_sucess.html', {'message': msg})
        response['HX-Trigger'] = 'updateContent'
        return response
    except ValidationError as e:
        return render(request, 'partials/_message_error.html', {'message': str(e)})
    except PermissionError as e:
        return render(request, 'partials/_message_error.html', {'message': str(e)})
    except Exception as e:
        return render(request, 'partials/_message_error.html', {'message': f"Erro ao cancelar: {e}"})


@require_POST
@login_required
def solicitacao_reverter_status_view(request, solicitacao_id):
    solicitacao = get_object_or_404(Solicitacao, id=solicitacao_id)
    detalhes = request.POST.get('detalhes', '').strip()

    try:
        services.reverter_status_solicitacao(solicitacao, request.user, detalhes)
        msg = mark_safe('Status da solicitação <span class="font-bold">revertido</span> com sucesso.')
        response = render(request, 'partials/_message_sucess.html', {'message': msg})
        response['HX-Trigger'] = 'updateContent'
        return response
    except ValidationError as e:
        return render(request, 'partials/_message_error.html', {'message': str(e)})
    except PermissionError as e:
        return render(request, 'partials/_message_error.html', {'message': str(e)})
    except Exception as e:
        return render(request, 'partials/_message_error.html', {'message': f"Erro ao reverter status: {e}"})