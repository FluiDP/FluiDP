"""Cálculos do relatório geral, sem alterar os dados das solicitações."""
from collections import Counter
from datetime import datetime, time, timedelta
import re

from django.utils import timezone

from .models import Solicitacao


def periodo_relatorio(params):
    hoje = timezone.localdate()
    inicio_padrao = hoje.replace(day=1)
    fim_padrao = (inicio_padrao.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    inicio_str = params.get('data_inicio', inicio_padrao.isoformat())
    fim_str = params.get('data_fim', fim_padrao.isoformat())
    context = {'data_inicio': inicio_str, 'data_fim': fim_str}
    try:
        inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
        fim = datetime.strptime(fim_str, '%Y-%m-%d').date()
        if inicio > fim:
            raise ValueError
        limite = fim + timedelta(days=1)
    except (ValueError, OverflowError):
        context['erro_periodo'] = 'Informe um período válido, com a data inicial anterior ou igual à final.'
        return None, None, context
    context.update(periodo_inicio=inicio, periodo_fim=fim)
    return (
        timezone.make_aware(datetime.combine(inicio, time.min)),
        timezone.make_aware(datetime.combine(limite, time.min)),
        context,
    )


def minutos_duracao(value):
    """Duração assinada HH:MM; horas podem ultrapassar 24."""
    if not isinstance(value, str) or not re.fullmatch(r'-?\d+:\d{2}', value.strip()):
        raise ValueError('Duração inválida')
    value = value.strip()
    horas, minutos = map(int, value.lstrip('-').split(':'))
    if minutos >= 60:
        raise ValueError('Minutos inválidos')
    return (-1 if value.startswith('-') else 1) * (horas * 60 + minutos)


def minutos_relogio(value):
    minutos = minutos_duracao(value)
    if minutos < 0 or minutos >= 1440:
        raise ValueError('Horário inválido')
    return minutos


def horas_solicitacao(sol):
    """Retorna extras e compensadas; respeita os totais salvos pelo DP.

    Formulários novos de HE não possuem total calculado e usam o cronograma.
    Na compensação, o Total Compensado é a quantidade efetivamente registrada;
    o saldo da ocorrência não limita os ajustes posteriores feitos pelo DP.
    """
    dados = sol.dados_preenchidos
    if not isinstance(dados, dict):
        raise ValueError('Dados do formulário inválidos')
    valores = dados.get('values', dados)
    schema = dados.get('schema', [])
    if not isinstance(valores, dict) or not isinstance(schema, list):
        raise ValueError('Dados do formulário inválidos')
    campos = [c for c in schema if isinstance(c, dict)]
    calculados = [c for c in campos if c.get('type') == 'calculated' and c.get('calc_format') == 'time']
    por_nome = {c.get('name'): c for c in calculados}
    if 'total_compensacao' in por_nome:
        plano = minutos_duracao(valores.get('total_compensacao'))
        return 0, abs(plano)
    extras = compensadas = 0
    for campo in calculados:
        nome = campo.get('name', '')
        descricao = (nome + ' ' + str(campo.get('label', ''))).lower()
        documento = sol.tipo_documento.nome_documento.lower()
        if 'compensa' in descricao or 'banco' in documento:
            compensadas += abs(minutos_duracao(valores.get(nome)))
        elif 'extra' in descricao or ('hora extra' in documento):
            minutos = minutos_duracao(valores.get(nome))
            if minutos < 0:
                raise ValueError('Horas extras negativas')
            extras += minutos
    if calculados:
        return extras, compensadas

    cronograma = next((c for c in campos if c.get('name') == 'cronograma_he' and c.get('type') == 'repeater'), None)
    if cronograma is None:
        if 'hora extra' in sol.tipo_documento.nome_documento.lower() or 'compensa' in sol.tipo_documento.nome_documento.lower():
            raise ValueError('Formulário sem definição de horas reconhecida')
        return 0, 0
    linhas = valores.get('cronograma_he')
    if not isinstance(linhas, list) or not linhas:
        raise ValueError('Cronograma ausente ou inválido')
    for linha in linhas:
        if not isinstance(linha, dict):
            raise ValueError('Linha de cronograma inválida')
        inicio = minutos_relogio(linha.get('hora_inicio'))
        periodo = (minutos_relogio(linha.get('hora_fim')) - inicio) % 1440
        intervalo = 0
        if linha.get('sem_intervalo') not in (True, 'true', 'on', '1'):
            intervalo_inicio = minutos_relogio(linha.get('inicio_intervalo'))
            intervalo = (minutos_relogio(linha.get('fim_intervalo')) - intervalo_inicio) % 1440
            if (intervalo_inicio - inicio) % 1440 + intervalo > periodo:
                raise ValueError('Intervalo fora da jornada')
        extras += periodo - intervalo
    return extras, 0


def formatar_minutos(minutos):
    return f'{minutos // 60:02d}:{minutos % 60:02d}'


def grafico_grupos(grupos):
    ordenados = sorted(grupos.values(), key=lambda g: (-g['total'], g['nome'].casefold()))
    selecionados = ordenados[:5]
    if len(ordenados) > 5:
        selecionados.append({'nome': 'Outros', 'total': sum(g['total'] for g in ordenados[5:])})
    return [g['nome'] for g in selecionados], [g['total'] for g in selecionados]


def resumir_solicitacoes(solicitacoes):
    ranking, documentos, lotacoes = {}, {}, {}
    total = arquivadas = extras = compensadas = 0
    avisos = []
    for sol in solicitacoes:
        total += 1
        arquivadas += int(sol.arquivado)
        colab = sol.colaborador
        item = ranking.setdefault(colab.pk, {'colaborador': colab, 'total': 0, 'tipos': Counter()})
        item['total'] += 1
        item['tipos'][sol.tipo_documento.nome_documento] += 1
        for grupos, chave, nome in (
            (documentos, sol.tipo_documento_id, sol.tipo_documento.nome_documento),
            (lotacoes, colab.lotacao_id, colab.lotacao.nome_lotacao if colab.lotacao else 'Sem lotação'),
        ):
            grupo = grupos.setdefault(chave, {'nome': nome, 'total': 0})
            grupo['total'] += 1
        if sol.status == Solicitacao.StatusChoices.FINALIZADO:
            try:
                he, hc = horas_solicitacao(sol)
                extras += he
                compensadas += hc
            except (ValueError, TypeError):
                avisos.append(sol.pk)
    ranking_data = sorted(ranking.values(), key=lambda i: (-i['total'], i['colaborador'].get_full_name().casefold(), i['colaborador'].pk))
    for posicao, item in enumerate(ranking_data, 1):
        item['posicao'] = posicao
        item['texto_principais'] = ', '.join(f'{nome} ({qtd})' for nome, qtd in sorted(item.pop('tipos').items(), key=lambda t: (-t[1], t[0])))
    docs_labels, docs_data = grafico_grupos(documentos)
    lot_labels, lot_data = grafico_grupos(lotacoes)
    return {
        'ranking_data': ranking_data, 'total_solicitacoes': total,
        'total_arquivadas': arquivadas, 'avisos_horas': sorted(avisos),
        'horas_extras': formatar_minutos(extras), 'horas_compensadas': formatar_minutos(compensadas),
        'chart_docs_labels': docs_labels, 'chart_docs_data': docs_data,
        'chart_lot_labels': lot_labels, 'chart_lot_data': lot_data,
    }
