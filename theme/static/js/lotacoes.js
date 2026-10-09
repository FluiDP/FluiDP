(function () {
    window.lotacoesExplorer = function (root) {
        return {
            query: '',
            current: null,
            closed: {},
            nodes: [],
            byId: {},
            init() {
                this.nodes = Array.from(root.querySelectorAll('.lotacao-item'));
                this.byId = Object.fromEntries(this.nodes.map(node => [node.dataset.lotacaoId, node]));
                this.nodes.forEach(node => {
                    const names = [];
                    let cursor = node;
                    while (cursor && cursor.classList.contains('lotacao-item')) {
                        names.unshift(cursor.dataset.lotacaoName);
                        cursor = cursor.parentElement.closest('.lotacao-item');
                    }
                    node.querySelector('[data-lotacao-path]').textContent = names.join(' / ');
                });
            },
            normalize(value) {
                return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
            },
            matches(node) {
                const term = this.normalize(this.query.trim());
                return !term || this.normalize(node.dataset.lotacaoName).includes(term);
            },
            hasMatch(node) {
                return this.matches(node) || Array.from(node.querySelectorAll('.lotacao-item')).some(child => this.matches(child));
            },
            visible(node) {
                if (this.query.trim()) return this.hasMatch(node);
                if (!this.current || !this.byId[this.current]) return true;
                const selected = this.byId[this.current];
                return node === selected || node.contains(selected) || selected.contains(node);
            },
            showCard(node) {
                if (this.query.trim() || !this.current || !this.byId[this.current]) return true;
                return this.byId[this.current].contains(node);
            },
            isAncestor(node) {
                const selected = this.byId[this.current];
                return !!selected && node !== selected && node.contains(selected);
            },
            showChildren(node) {
                if (this.query.trim()) return true;
                const selected = this.byId[this.current];
                if (selected && node !== selected && node.contains(selected)) return true;
                return !this.closed[node.dataset.lotacaoId];
            },
            toggle(id) {
                this.closed = { ...this.closed, [id]: !this.closed[id] };
            },
            enter(id) {
                this.query = '';
                this.current = id;
                this.closed = { ...this.closed, [id]: false };
                this.$refs.tree.scrollTop = 0;
            },
            go(id) {
                this.query = '';
                this.current = id;
                this.$refs.tree.scrollTop = 0;
            },
            get breadcrumbs() {
                if (!this.current || !this.byId[this.current]) return [];
                const result = [];
                let cursor = this.byId[this.current];
                while (cursor && cursor.classList.contains('lotacao-item')) {
                    result.unshift({ id: cursor.dataset.lotacaoId, name: cursor.dataset.lotacaoName });
                    cursor = cursor.parentElement.closest('.lotacao-item');
                }
                return result;
            },
            get resultCount() {
                return this.nodes.filter(node => this.matches(node)).length;
            }
        };
    };
})();
