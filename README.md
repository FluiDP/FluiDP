# Sistema DP

O **Sistema DP** é um gerenciador de fluxo de solicitações ao Departamento Pessoal (DP). Essas solicitações são vinculadas aos colaboradores interessados e ao tipo do documento, além de passar pela aprovação da chefia imediata, do diretor responsável e do DP.

## Iniciando com o projeto

### Se for a 1ª vez iniciando:

1. Clone o repositório na sua máquina:
    ```bash
    git clone https://github.com/Sistema-DP/Sistema-DP/
    ```

2. Crie o ambiente virtual:
    ```bash
    python -m venv venv
    ```

3. Entre no ambiente virtual:
    ```bash
    & C:/Users/Ramom/Documents/sistemadp/venv/Scripts/Activate.ps1
    ```

4. Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

5. Siga os passos 2 e 3 da sessão abaixo.

### A partir da 2ª vez:

1. Entre no ambiente virtual:
    ```bash
    & C:/Users/Ramom/Documents/sistemadp/venv/Scripts/Activate.ps1
    ```

2. Ative o Tailwind:
    ```bash
    python manage.py tailwind start
    ```

3. Em outro terminal faça o passo 1 novamente e inicie o servidor Django:
    ```bash
    python manage.py runserver
    ```
