"""Avisos de períodos para os formulários atuais e seus schemas históricos.

Não altera valores, não bloqueia o fluxo e não compara totais corrigidos pelo DP
com as linhas originalmente preenchidas pelo colaborador.
"""
import re
from datetime import date


HORA_INVALIDA = 'Horário inválido. Informe um horário entre 00:00 e 23:59.'
DURACAO_INVALIDA = 'Duração inválida. Use HH:MM, com minutos entre 00 e 59.'
PERIODO_INCOMPLETO = 'Período incompleto. Informe o início e o fim.'
PERIODO_ZERADO = 'Início e fim iguais: o período resulta em zero horas. Confira os horários.'
INTERVALO_FORA = 'O intervalo deve estar inteiramente dentro do período de trabalho.'
DURACAO_DIVERGENTE = 'A duração informada não corresponde aos horários de início e fim.'
DATA_INVALIDA = 'Data inválida. Confira a data informada.'
DATAS_INVERTIDAS = 'A data final é anterior à data inicial.'


def minutos(value, relogio=False, assinado=False):
    pattern = r'\d{1,2}:\d{2}' if relogio else (r'-?\d+:\d{2}' if assinado else r'\d+:\d{2}')
    if not isinstance(value, str) or not re.fullmatch(pattern, value.strip()):
        raise ValueError
    value = value.strip()
    horas, mins = map(int, value.lstrip('-').split(':'))
    if mins > 59 or (relogio and horas > 23):
        raise ValueError
    return (-1 if value.startswith('-') else 1) * (horas * 60 + mins)


def props_campo(campo):
    props = campo.get('extra_props')
    return props if isinstance(props, dict) else {}


def data_iso(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError
    return date.fromisoformat(value)


def pares_periodos(campos):
    """Usa vínculos explícitos do schema e convenções existentes de início/fim."""
    nomes = {c.get('name') for c in campos}
    pares = {}
    for campo in campos:
        props = props_campo(campo)
        auto = props.get('auto_calc_time_diff') or {}
        if isinstance(auto, dict) and auto.get('start') in nomes and auto.get('end') in nomes:
            pares.setdefault((auto['start'], auto['end']), []).append(campo['name'])
    for nome in sorted(n for n in nomes if isinstance(n, str)):
        fim = nome.replace('inicio', 'fim') if 'inicio' in nome else None
        if nome == 'entrada':
            fim = 'saida'
        elif nome == 'start':
            fim = 'end'
        campo_inicio = next(c for c in campos if c.get('name') == nome)
        campo_fim = next((c for c in campos if c.get('name') == fim), {})
        e_periodo = (campo_inicio.get('type') == campo_fim.get('type') == 'date') or (
            props_campo(campo_inicio).get('day_time_field') and props_campo(campo_fim).get('day_time_field')
        ) or nome in ('inicio', 'hora_inicio', 'horario_inicio', 'inicio_intervalo', 'entrada', 'start')
        if fim and fim != nome and fim in nomes and e_periodo:
            pares.setdefault((nome, fim), [])
    return pares


def avisos_escopo(campos, valores):
    campos = [c for c in campos if isinstance(c, dict) and c.get('name')]
    valores = valores if isinstance(valores, dict) else {}
    por_nome = {c['name']: c for c in campos}
    pares = pares_periodos(campos)
    avisos = {}

    def avisar(nome, mensagem):
        if nome not in por_nome:
            return
        mensagens = avisos.setdefault(nome, [])
        if mensagem not in mensagens:
            mensagens.append(mensagem)

    relogios = set()
    for (inicio, fim), _ in pares.items():
        if por_nome[inicio].get('type') != 'date' and por_nome[fim].get('type') != 'date':
            relogios.update((inicio, fim))
    ignorar_intervalo = valores.get('sem_intervalo') in (True, 'true', 'on', '1')
    if ignorar_intervalo:
        relogios.difference_update(('inicio_intervalo', 'fim_intervalo'))
    for campo in campos:
        nome = campo['name']
        if ignorar_intervalo and nome in ('inicio_intervalo', 'fim_intervalo'):
            continue
        props = props_campo(campo)
        valor = valores.get(nome)
        if valor in (None, ''):
            continue
        e_relogio = nome in relogios or props.get('day_time_field')
        e_duracao = props.get('count_time_field') or props.get('auto_calc_time_diff') or (
            campo.get('type') == 'calculated' and campo.get('calc_format') == 'time'
        )
        if e_relogio or e_duracao:
            try:
                minutos(valor, relogio=bool(e_relogio), assinado=campo.get('type') == 'calculated')
            except ValueError:
                avisar(nome, HORA_INVALIDA if e_relogio else DURACAO_INVALIDA)

    periodos = {}
    for (inicio, fim), resultados in pares.items():
        if ignorar_intervalo and (inicio, fim) == ('inicio_intervalo', 'fim_intervalo'):
            continue
        a, b = valores.get(inicio), valores.get(fim)
        if a in (None, '') and b in (None, ''):
            continue
        if a in (None, '') or b in (None, ''):
            avisar(inicio if a in (None, '') else fim, PERIODO_INCOMPLETO)
            for nome in resultados:
                avisar(nome, PERIODO_INCOMPLETO)
            continue
        if por_nome[inicio].get('type') == por_nome[fim].get('type') == 'date':
            try:
                data_inicio, data_fim = data_iso(a), data_iso(b)
                if data_fim < data_inicio:
                    avisar(fim, DATAS_INVERTIDAS)
            except (ValueError, TypeError):
                for nome in (inicio, fim):
                    try:
                        data_iso(valores[nome])
                    except (ValueError, TypeError):
                        avisar(nome, DATA_INVALIDA)
            continue
        try:
            start, end = minutos(a, relogio=True), minutos(b, relogio=True)
        except ValueError:
            for nome in resultados:
                avisar(nome, PERIODO_INCOMPLETO)
            continue
        duracao = (end - start) % 1440
        periodos[(inicio, fim)] = (start, duracao)
        if duracao == 0:
            for nome in (inicio, fim, *resultados):
                avisar(nome, PERIODO_ZERADO)
        for nome in resultados:
            valor = valores.get(nome)
            if valor not in (None, ''):
                try:
                    if minutos(valor) != duracao:
                        avisar(nome, DURACAO_DIVERGENTE)
                except ValueError:
                    pass

    intervalo = periodos.get(('inicio_intervalo', 'fim_intervalo'))
    jornada = next((periodos[p] for p in pares if p in periodos and p != ('inicio_intervalo', 'fim_intervalo')), None)
    if not ignorar_intervalo and jornada and ('inicio_intervalo', 'fim_intervalo') in pares and not intervalo:
        for nome in ('inicio_intervalo', 'fim_intervalo'):
            if valores.get(nome) in (None, ''):
                avisar(nome, PERIODO_INCOMPLETO)
    if not ignorar_intervalo and intervalo and jornada:
        inicio, duracao = jornada
        pausa, duracao_pausa = intervalo
        if (pausa - inicio) % 1440 + duracao_pausa > duracao:
            avisar('inicio_intervalo', INTERVALO_FORA)
            avisar('fim_intervalo', INTERVALO_FORA)
    return {nome: ' '.join(mensagens) for nome, mensagens in avisos.items()}


def analisar_periodos(schema, valores):
    campos = [c for c in schema if isinstance(c, dict)] if isinstance(schema, list) else []
    valores = valores if isinstance(valores, dict) else {}
    avisos = {(nome,): mensagem for nome, mensagem in avisos_escopo(campos, valores).items()}
    for campo in campos:
        if campo.get('type') != 'repeater':
            continue
        linhas = valores.get(campo.get('name'))
        if not isinstance(linhas, list):
            continue
        for indice, linha in enumerate(linhas):
            for nome, mensagem in avisos_escopo(campo.get('sub_fields', []), linha).items():
                avisos[(campo['name'], indice, nome)] = mensagem
    return avisos
