# Guia resumido de modificações do FluiDP

Este documento descreve o fluxo recomendado para alterar, testar e publicar o FluiDP sem sobrepor versões ou executar mudanças acidentais no banco de produção.

## Princípios

- A branch `dev` do GitHub é a fonte única do código.
- Faça alterações e commits na máquina de desenvolvimento, nunca diretamente em `/var/www/sistemadp`.
- Não versione `.env`, credenciais, certificados, `media/`, logs ou arquivos importados.
- O PostgreSQL de produção permanece fora do Docker e não deve ser usado por testes destrutivos.
- Restart da aplicação e execução de migrations são operações separadas.
- Nginx é compartilhado por outras aplicações: não o reinicie nem altere sua configuração global para publicar o FluiDP.

## Fluxo de desenvolvimento

Antes de começar:

```powershell
git switch dev
git pull --ff-only origin dev
git status
```

Depois da alteração:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test core.tests
git diff --check
git status
```

Se o modelo foi alterado, crie a migration localmente, revise seu conteúdo e repita os testes:

```powershell
python manage.py makemigrations core
python manage.py migrate --plan
```

Não aplique migrations no banco real durante o desenvolvimento.

## Teste Docker com banco descartável

Este é o teste padrão. Ele usa PostgreSQL 12 temporário em memória e publica o FluiDP em `127.0.0.1:18080`:

```powershell
docker compose --env-file .env.docker.example `
  -f docker-compose.yml -f docker-compose.local.yml `
  --profile maintenance up -d --build
```

Verifique:

```powershell
docker compose --env-file .env.docker.example `
  -f docker-compose.yml -f docker-compose.local.yml `
  --profile maintenance ps
```

Ao terminar, remova o laboratório e o banco descartável:

```powershell
docker compose --env-file .env.docker.example `
  -f docker-compose.yml -f docker-compose.local.yml `
  --profile maintenance down
```

Conectar o Docker local ao banco de produção é excepcional. Nesse caso, suba somente `web`, nunca `worker` ou `migrate`, pois as ações na interface gravam dados reais e um segundo worker pode consumir a fila de produção.

## Commit e envio

Revise os arquivos antes de adicioná-los:

```powershell
git status
git diff
git add caminho/do/arquivo
git commit -m "tipo: descrição objetiva"
git push origin dev
```

Use, por exemplo, `feat:`, `fix:`, `docs:`, `refactor:` ou `chore:`. Prefira listar arquivos no `git add`; use `git add .` somente após conferir cuidadosamente o status.

## Atualização do servidor

No servidor:

```bash
cd /var/www/sistemadp
git status
git fetch origin
git pull --ff-only origin dev
```

Se `git status` não estiver limpo ou o `pull --ff-only` falhar, pare. Não use `reset --hard`, não faça merge improvisado e não copie arquivos manualmente por SCP/FTP.

Antes de migrations:

```bash
docker compose run --rm --no-deps web python manage.py migrate --plan
```

Após backup validado e revisão do plano:

```bash
docker compose --profile maintenance run --rm migrate
```

Uma atualização comum, sem migrations, será ativada por:

```bash
sudo systemctl restart sistemadp
sudo systemctl status sistemadp
docker compose ps
docker compose logs --tail=100 web worker
```

O Nginx continua encaminhando `fluidp.intranet.com` para `127.0.0.1:8080`; não é necessário reiniciá-lo em uma atualização normal do FluiDP.

## Verificação e retorno

Confirme a tela de login, uma consulta sem escrita e a saúde da fila. Em caso de falha, preserve logs e identifique o último commit estável. O retorno deve usar um commit conhecido e o procedimento documentado para a versão, nunca alterações manuais sobre o diretório ativo.

