(function (global) {
    'use strict';
    const messages = {
        clock: 'Horário inválido. Informe um horário entre 00:00 e 23:59.',
        duration: 'Duração inválida. Use HH:MM, com minutos entre 00 e 59.',
        incomplete: 'Período incompleto. Informe o início e o fim.',
        zero: 'Início e fim iguais: o período resulta em zero horas. Confira os horários.',
        interval: 'O intervalo deve estar inteiramente dentro do período de trabalho.',
        mismatch: 'A duração informada não corresponde aos horários de início e fim.',
        date: 'Data inválida. Confira a data informada.',
        dates: 'A data final é anterior à data inicial.'
    };
    const empty = value => value === undefined || value === null || value === '';
    const noBreak = value => [true, 'true', 'on', '1'].includes(value);
    const modDay = value => ((value % 1440) + 1440) % 1440;
    function minutes(value, clock, signed) {
        const pattern = clock ? /^\d{1,2}:\d{2}$/ : signed ? /^-?\d+:\d{2}$/ : /^\d+:\d{2}$/;
        if (typeof value !== 'string' || !pattern.test(value.trim())) return null;
        value = value.trim();
        const [h, m] = value.replace(/^-/, '').split(':').map(Number);
        if (m > 59 || (clock && h > 23)) return null;
        return (value.startsWith('-') ? -1 : 1) * (h * 60 + m);
    }
    function pairs(fields) {
        const names = new Set(fields.map(f => f.name));
        const found = new Map();
        function add(start, end, result) {
            const key = JSON.stringify([start, end]);
            if (!found.has(key)) found.set(key, { start, end, results: [] });
            if (result) found.get(key).results.push(result);
        }
        fields.forEach(field => {
            const auto = field.extra_props?.auto_calc_time_diff;
            if (auto && names.has(auto.start) && names.has(auto.end)) add(auto.start, auto.end, field.name);
        });
        [...names].filter(n => typeof n === 'string').sort().forEach(name => {
            let end = name.includes('inicio') ? name.replaceAll('inicio', 'fim') : null;
            if (name === 'entrada') end = 'saida';
            if (name === 'start') end = 'end';
            const startField = fields.find(f => f.name === name);
            const endField = fields.find(f => f.name === end);
            const temporal = (startField.type === 'date' && endField?.type === 'date') ||
                (startField.extra_props?.day_time_field && endField?.extra_props?.day_time_field) ||
                ['inicio', 'hora_inicio', 'horario_inicio', 'inicio_intervalo', 'entrada', 'start'].includes(name);
            if (end && end !== name && names.has(end) && temporal) add(name, end);
        });
        return [...found.values()];
    }
    function validDate(value) {
        if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
        const parsed = new Date(value + 'T00:00:00Z');
        return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
    }
    function scopeWarnings(fields, values) {
        fields = (fields || []).filter(f => f && typeof f === 'object' && f.name);
        values = values && typeof values === 'object' && !Array.isArray(values) ? values : {};
        const byName = Object.fromEntries(fields.map(f => [f.name, f]));
        const periods = pairs(fields);
        const warnings = {};
        const clocks = new Set();
        const skipBreak = noBreak(values.sem_intervalo);
        const isBreak = p => p.start === 'inicio_intervalo' && p.end === 'fim_intervalo';
        function warn(name, message) {
            if (!byName[name]) return;
            if (!warnings[name]) warnings[name] = [];
            if (!warnings[name].includes(message)) warnings[name].push(message);
        }
        periods.forEach(p => {
            if (byName[p.start].type !== 'date' && byName[p.end].type !== 'date') {
                clocks.add(p.start); clocks.add(p.end);
            }
        });
        if (skipBreak) { clocks.delete('inicio_intervalo'); clocks.delete('fim_intervalo'); }
        fields.forEach(field => {
            if (skipBreak && ['inicio_intervalo', 'fim_intervalo'].includes(field.name)) return;
            const value = values[field.name];
            if (empty(value)) return;
            const props = field.extra_props || {};
            const clock = clocks.has(field.name) || props.day_time_field;
            const duration = props.count_time_field || props.auto_calc_time_diff || (field.type === 'calculated' && field.calc_format === 'time');
            if ((clock || duration) && minutes(value, !!clock, field.type === 'calculated') === null) warn(field.name, clock ? messages.clock : messages.duration);
        });
        const computed = new Map();
        periods.forEach(p => {
            if (skipBreak && isBreak(p)) return;
            const a = values[p.start], b = values[p.end];
            if (empty(a) && empty(b)) return;
            if (empty(a) || empty(b)) {
                warn(empty(a) ? p.start : p.end, messages.incomplete);
                p.results.forEach(n => warn(n, messages.incomplete));
                return;
            }
            if (byName[p.start].type === 'date' && byName[p.end].type === 'date') {
                if (validDate(a) && validDate(b)) {
                    if (b < a) warn(p.end, messages.dates);
                } else {
                    [p.start, p.end].forEach(n => { if (!validDate(values[n])) warn(n, messages.date); });
                }
                return;
            }
            const start = minutes(a, true), end = minutes(b, true);
            if (start === null || end === null) {
                p.results.forEach(n => warn(n, messages.incomplete));
                return;
            }
            const duration = modDay(end - start);
            computed.set(JSON.stringify([p.start, p.end]), { start, duration });
            if (!duration) [p.start, p.end, ...p.results].forEach(n => warn(n, messages.zero));
            p.results.forEach(n => {
                const saved = minutes(values[n]);
                if (!empty(values[n]) && saved !== null && saved !== duration) warn(n, messages.mismatch);
            });
        });
        const interval = computed.get(JSON.stringify(['inicio_intervalo', 'fim_intervalo']));
        const shiftPair = periods.find(p => !isBreak(p) && computed.has(JSON.stringify([p.start, p.end])));
        const shift = shiftPair && computed.get(JSON.stringify([shiftPair.start, shiftPair.end]));
        if (!skipBreak && shift && periods.some(isBreak) && !interval) {
            ['inicio_intervalo', 'fim_intervalo'].forEach(name => { if (empty(values[name])) warn(name, messages.incomplete); });
        }
        if (!skipBreak && interval && shift && modDay(interval.start - shift.start) + interval.duration > shift.duration) {
            warn('inicio_intervalo', messages.interval); warn('fim_intervalo', messages.interval);
        }
        return Object.fromEntries(Object.entries(warnings).map(([name, texts]) => [name, texts.join(' ')]));
    }
    function analyze(schema, values) {
        schema = Array.isArray(schema) ? schema.filter(f => f && typeof f === 'object') : [];
        values = values && typeof values === 'object' && !Array.isArray(values) ? values : {};
        const warnings = {};
        Object.entries(scopeWarnings(schema, values)).forEach(([name, text]) => { warnings[JSON.stringify([name])] = text; });
        schema.filter(f => f.type === 'repeater').forEach(field => {
            if (!Array.isArray(values[field.name])) return;
            values[field.name].forEach((row, index) => {
                Object.entries(scopeWarnings(field.sub_fields, row)).forEach(([name, text]) => { warnings[JSON.stringify([field.name, index, name])] = text; });
            });
        });
        return warnings;
    }
    const api = { analyze, minutes };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    global.FluidpTimeValidation = api;
    if (typeof document === 'undefined') return;

    // O balão fica fora das tabelas e modais para não ser cortado pelo scroll.
    let floating, activeBadge;
    function hideTooltip() {
        if (floating) floating.hidden = true;
        activeBadge = null;
    }
    function showTooltip(badge) {
        if (!badge) return;
        if (!floating) {
            floating = document.createElement('span');
            floating.className = 'time-inconsistency-floating';
            floating.dataset.timeWarning = '';
            floating.setAttribute('role', 'tooltip');
            document.body.appendChild(floating);
        }
        activeBadge = badge;
        floating.textContent = badge.title;
        floating.hidden = false;
        const rect = badge.getBoundingClientRect();
        const left = Math.max(8, Math.min(rect.left, window.innerWidth - floating.offsetWidth - 8));
        const top = rect.top >= floating.offsetHeight + 12 ? rect.top - floating.offsetHeight - 8 : rect.bottom + 8;
        floating.style.left = left + 'px';
        floating.style.top = Math.max(8, Math.min(top, window.innerHeight - floating.offsetHeight - 8)) + 'px';
    }
    document.addEventListener('focusin', e => {
        const badge = e.target.closest('.time-inconsistency');
        if (badge) showTooltip(badge);
        else hideTooltip();
    });
    document.addEventListener('focusout', e => { if (e.target === activeBadge) hideTooltip(); });
    document.addEventListener('pointerover', e => {
        const badge = e.target.closest('.time-inconsistency');
        if (badge && badge !== activeBadge) showTooltip(badge);
    });
    document.addEventListener('pointerout', e => {
        if (activeBadge && !activeBadge.contains(e.relatedTarget) && document.activeElement !== activeBadge) hideTooltip();
    });
    document.addEventListener('scroll', hideTooltip, true);
    document.addEventListener('keydown', e => { if (e.key === 'Escape') hideTooltip(); });
    window.addEventListener('resize', hideTooltip);

    const timers = new WeakMap();
    function readForm(root) {
        const script = root.querySelector('script[type="application/json"]');
        if (!script) return { warnings: {}, inputs: new Map() };
        let schema;
        try { schema = JSON.parse(script.textContent); } catch (_) { return { warnings: {}, inputs: new Map() }; }
        const inputs = new Map(), values = {};
        function read(container, name, path) {
            const elements = Array.from(container.querySelectorAll('input,select,textarea')).filter(el => el.name === name);
            const input = elements.find(el => el.type !== 'radio' || el.checked);
            if (!input) return '';
            inputs.set(JSON.stringify(path), input);
            return input.type === 'checkbox' ? (input.checked ? 'true' : 'false') : input.value;
        }
        schema.forEach(field => {
            if (field.type === 'repeater') {
                const container = Array.from(root.querySelectorAll('[data-repeater]')).find(el => el.dataset.repeater === field.name);
                values[field.name] = Array.from(container?.querySelectorAll('.repeater-row') || []).map((row, index) => Object.fromEntries(
                    (field.sub_fields || []).map(sub => [sub.name, read(row, field.name + '_' + sub.name + '[]', [field.name, index, sub.name])])
                ));
            } else values[field.name] = read(root, field.name, [field.name]);
        });
        return { warnings: analyze(schema, values), inputs };
    }
    function update(root) {
        if (!root.isConnected) return;
        const { warnings, inputs } = readForm(root);
        const existing = new Map(Array.from(root.querySelectorAll('[data-dynamic-time-warning]')).map(el => [el.dataset.dynamicTimeWarning, el]));
        Object.entries(warnings).forEach(([key, message]) => {
            const input = inputs.get(key);
            if (!input) return;
            let badge = existing.get(key);
            existing.delete(key);
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'time-inconsistency';
                badge.tabIndex = 0;
                badge.setAttribute('role', 'img');
                badge.dataset.timeWarning = '';
                badge.dataset.dynamicTimeWarning = key;
                badge.innerHTML = '<ion-icon name="warning-outline" aria-hidden="true"></ion-icon><span class="time-inconsistency-tooltip" role="tooltip"></span>';
                const wrapper = input.closest('[data-subfield]') || input.parentElement;
                const label = wrapper.querySelector('label');
                if (label) label.appendChild(badge);
                else input.insertAdjacentElement('afterend', badge);
            }
            badge.title = message;
            badge.setAttribute('aria-label', 'Inconsistência de horas: ' + message);
            badge.querySelector('[role="tooltip"]').textContent = message;
        });
        existing.forEach(badge => badge.remove());
    }
    function schedule(root) {
        if (!root) return;
        clearTimeout(timers.get(root));
        timers.set(root, setTimeout(() => update(root), 180));
    }
    function init() { document.querySelectorAll('[data-time-validation]').forEach(schedule); }
    ['input', 'change'].forEach(event => document.addEventListener(event, e => schedule(e.target.closest('[data-time-validation]'))));
    document.addEventListener('htmx:afterSwap', init);
    const observer = new MutationObserver(changes => {
        changes.forEach(change => {
            const nodes = [...change.addedNodes, ...change.removedNodes];
            if (!nodes.some(node => node.nodeType === 1 && !node.matches('[data-time-warning], [data-time-warning] *'))) return;
            schedule(change.target.closest?.('[data-time-validation]'));
            nodes.forEach(node => {
                if (node.nodeType !== 1 || !node.isConnected) return;
                if (node.matches('[data-time-validation]')) schedule(node);
                node.querySelectorAll('[data-time-validation]').forEach(schedule);
            });
        });
    });
    function start() { init(); observer.observe(document.body, { childList: true, subtree: true }); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
    else start();
    api.warningForForm = (root, path) => readForm(root).warnings[JSON.stringify(path)] || '';
})(typeof window === 'undefined' ? globalThis : window);
