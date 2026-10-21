(() => {
    'use strict';

    const editors = new WeakMap();
    const selector = 'textarea[data-json-editor]';

    function textareas(root) {
        const fields = Array.from(root.querySelectorAll ? root.querySelectorAll(selector) : []);
        if (root.matches && root.matches(selector)) fields.unshift(root);
        return fields;
    }

    function initialize(root) {
        if (!window.CodeMirror) return;
        textareas(root).forEach((textarea) => {
            if (editors.has(textarea)) return;

            const editor = window.CodeMirror.fromTextArea(textarea, {
                mode: {name: 'javascript', json: true},
                theme: 'fluidp-json',
                lineNumbers: true,
                indentUnit: 2,
                tabSize: 2,
                indentWithTabs: false,
                smartIndent: true,
                autoCloseBrackets: true,
                matchBrackets: true,
                lineWrapping: false,
                screenReaderLabel: 'Definição do formulário em JSON',
                extraKeys: {
                    Tab(cm) {
                        if (cm.somethingSelected()) cm.indentSelection('add');
                        else cm.replaceSelection('  ', 'end', '+input');
                    },
                    'Shift-Tab': 'indentLess',
                    'Ctrl-Shift-F': () => format(),
                    'Cmd-Shift-F': () => format(),
                    Esc(cm) { cm.getInputField().blur(); },
                },
            });
            editors.set(textarea, editor);
            const wrapper = editor.getWrapperElement();
            wrapper.classList.add('json-editor');

            const toolbar = document.createElement('div');
            toolbar.className = 'json-editor-toolbar';
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = 'Formatar JSON';
            button.title = 'Formatar JSON (Ctrl/Cmd + Shift + F)';
            const feedback = document.createElement('span');
            feedback.className = 'json-editor-feedback';
            feedback.setAttribute('role', 'status');
            toolbar.append(button, feedback);
            wrapper.before(toolbar);

            function format() {
                try {
                    const formatted = JSON.stringify(JSON.parse(editor.getValue()), null, 2);
                    if (formatted !== editor.getValue()) {
                        editor.operation(() => editor.replaceRange(
                            formatted, {line: 0, ch: 0},
                            {line: editor.lastLine(), ch: editor.getLine(editor.lastLine()).length},
                            '+format',
                        ));
                    }
                    feedback.textContent = 'JSON formatado.';
                } catch (error) {
                    feedback.textContent = 'JSON inválido. Corrija a sintaxe para formatar.';
                }
                editor.focus();
            }

            button.addEventListener('click', format);
            // HTMX lê o textarea diretamente: mantê-lo sincronizado a cada edição.
            editor.on('change', () => {
                editor.save();
                feedback.textContent = '';
            });
            requestAnimationFrame(() => editor.refresh());
        });
    }

    document.addEventListener('DOMContentLoaded', () => initialize(document));
    document.addEventListener('htmx:load', (event) => initialize(event.detail.elt));
    document.addEventListener('htmx:beforeCleanupElement', (event) => {
        textareas(event.detail.elt).forEach((textarea) => {
            const editor = editors.get(textarea);
            if (!editor) return;
            const toolbar = editor.getWrapperElement().previousElementSibling;
            if (toolbar?.classList.contains('json-editor-toolbar')) toolbar.remove();
            editor.toTextArea();
            editors.delete(textarea);
        });
    });
})();
