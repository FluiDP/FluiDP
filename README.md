# FluiDP

O **FluiDP** é um gerenciador de fluxo de solicitações ao Departamento Pessoal (DP). Essas solicitações são vinculadas aos colaboradores interessados e ao tipo do documento, além de passar pela aprovação da chefia imediata, do diretor responsável e do DP.

---

## Desenvolvimento Local (Sem Docker)
Ideal para codificação diária, testes rápidos e hot-reload do Tailwind.

### Na 1ª vez iniciando o projeto:

1. Clone o repositório na sua máquina:
    ```bash
    git clone [https://github.com/FluiDP/Sistema-DP/](https://github.com/FluiDP/Sistema-DP/)
    ```

2. Crie uma cópia do arquivo `.env.example` com o nome `.env` e preencha as variáveis locais.

3. Crie o ambiente virtual:
    ```bash
    python -m venv .venv
    ```

4. Entre no ambiente virtual:
    ```bash
    .\.venv\Scripts\Activate.ps1
    ```

5. Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

6. Siga os passos da sessão abaixo.

### A partir da 2ª vez:

1. Entre no ambiente virtual:
    ```bash
    .\.venv\Scripts\Activate.ps1
    ```

2. Ative o Tailwind (ficará monitorando as mudanças no CSS):
    ```bash
    python manage.py tailwind start
    ```

3. Em outro terminal, ative o ambiente virtual novamente e inicie o servidor Django:
    ```bash
    python manage.py runserver
    ```

---

## Deploy em Produção (Com Docker)
A infraestrutura de produção é totalmente conteneirizada, garantindo isolamento e estabilidade no servidor.

1. No servidor, clone ou atualize o repositório.
2. Certifique-se de ter criado o arquivo `.env` na raiz do projeto com as credenciais de produção (Banco de dados, E-mail, `DJANGO_DEBUG=False`).
3. Faça o build e suba o container em segundo plano:
    ```bash
    docker compose up -d --build
    ```
*(O script `entrypoint.sh` fará automaticamente o build do Tailwind, as migrações do banco e a coleta dos arquivos estáticos).*

**Comandos Úteis no Docker:**
* Para ver os logs em tempo real:
  `docker compose logs -f`
* Para criar um superusuário no banco de produção:
  `docker compose exec web python manage.py createsuperuser`
* Para reiniciar a aplicação:
  `docker compose restart`

---

## Importando tabelas (csv/xlsx)

A importação deve ser feita via interface gráfica (em implementação) ou linha de comando.

Para realizar a importação via linha de comando localmente, utilize o comando `importer`:
```bash
python manage.py importer [tipo] [arquivo]
```

Se o sistema já estiver rodando via Docker, rode o comando dentro do container:
```bash
docker compose exec web python manage.py importer [tipo] [arquivo]
```

Sendo que:
- `tipo`: corresponde a tabela a ser alimentada (cargo, usuario, lotacao).
- `arquivo`: o caminho referente à tabela a ser importada.
