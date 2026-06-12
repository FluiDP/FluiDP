# FluiDP

O **FluiDP** é um gerenciador de fluxo de solicitações ao Departamento Pessoal (DP). Essas solicitações são vinculadas aos colaboradores interessados e ao tipo do documento, além de passar pela aprovação da chefia imediata, do diretor responsável e do DP.

## Iniciando com o projeto

### Na 1ª vez iniciando o projeto:

1. Clone o repositório na sua máquina:
    ```bash
    git clone https://github.com/FluiDP/Sistema-DP/
    ```

2. Crie o ambiente virtual:
    ```bash
    python -m venv .venv
    ```

3. Entre no ambiente virtual:
    ```bash
    .\.venv\Scripts\Activate.ps1
    ```

4. Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

5. Siga os passos 2 e 3 da sessão abaixo.

### A partir da 2ª vez:

1. Entre no ambiente virtual:
    ```bash
    .\.venv\Scripts\Activate.ps1
    ```

2. Ative o Tailwind:
    ```bash
    python manage.py tailwind start
    ```

3. Em outro terminal faça o passo 1 novamente e inicie o servidor Django:
    ```bash
    python manage.py runserver
    ```

## Importando tabelas (csv/xlsx)

A importação deve ser feita via interface gráfica (em implementação) ou linha de comando.

Para realizar a importação via linha de comando, utilize o comando `import`:
```
python manage.py import [tipo] [arquivo]
```

Sendo que:
- `tipo`: corresponde a tabela a ser alimentada (cargo, usuario, lotacao).
- `arquivo`: o caminho referente à tabela a ser importada.

## Passo a passo do deploy

1. Crie um banco de dados no PostgreSQL:
    ```sql
    CREATE DATABASE sistemadp;
    ```

2. Na raiz do projeto, crier e entre no ambiente virtual:
    ```bash
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

3. Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

4. Crie e realize as migrações:
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

5. Faça build do Tailwind:
    ```bash
    python manage.py tailwind install
    python manage.py tailwind build
    ```

6. Crie um superuser:
    ```bash
    python manage.py createsuperuser
    ```
    _Siga as instruções para criar usuário e senha._

7. Inicialize o Django:
    ```bash
    python manage.py runserver 0.0.0.0:8080
    ```
