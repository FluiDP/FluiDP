# Arquitetura do FluiDP

O FluiDP é uma aplicação monolítica Django, com páginas renderizadas no servidor e PostgreSQL como banco principal. O mesmo projeto fornece as telas dos perfis, a administração e as tarefas em segundo plano.

## Organização do código

| Local | Responsabilidade |
| --- | --- |
| `sistemadp/` | Configurações, URLs principais e entradas WSGI/ASGI. |
| `core/models.py` | Entidades, esquema dos formulários dinâmicos e parte das validações/permissões. |
| `core/services.py` | Operações do fluxo, histórico, notificações, e-mails e importação. |
| `core/views*.py` e `core/urls*.py` | Endpoints comuns e separados por colaborador, gestor, DP e mobile. |
| `core/forms.py` | Formulários Django para cadastros e administração. |
| `core/decorators.py`, `backends.py` e `middleware.py` | Controle de acesso, autenticação e tratamento das requisições. |
| `templates/` | Páginas, fragmentos HTMX, modais e relatórios de impressão. |
| `theme/` | Recursos visuais e compilação do Tailwind CSS. |
| `core/tasks.py` e `signals.py` | Tarefas assíncronas e reação a eventos, como criação de usuários. |
| `core/management/commands/` | Importação e rotina de acompanhamento de solicitações. |
| `core/migrations/` | Evolução do banco e migrações de dados. |

## Requisições e interface

O navegador acessa as URLs Django, que aplicam autenticação e permissões e encaminham a requisição à view. As views consultam o ORM e chamam serviços para operações de negócio. A resposta é uma página HTML ou um fragmento atualizado por HTMX. Alpine.js auxilia interações no navegador e Tailwind CSS fornece os estilos.

As rotas de perfil ficam em `/colaborador/`, `/gestor/`, `/administracao/` e `/m/`. O Django Admin fica em `/admin/`, com Unfold. A autenticação usa o usuário customizado e sessões Django; a autorização combina grupos, hierarquia, participação na solicitação e estado do fluxo.

## Persistência e regras

O ORM persiste usuários, estrutura organizacional, solicitações, histórico e notificações. Os formulários configuráveis usam JSON: `TipoDocumento.definicao_formulario` guarda a definição; `Solicitacao.dados_preenchidos` guarda `schema` e `values`.

As regras estão distribuídas entre modelos, serviços e views. `TipoDocumento.validar_regras()` valida a abertura e as datas marcadas no formulário. `Solicitacao.save()` chama `full_clean()`, mas `Solicitacao.clean()` aplica essas regras de abertura somente a registros novos. Os serviços de alteração do fluxo utilizam transações e registram ações em `LogAprovacao`.

## Processamento em segundo plano

Django Q2 processa tarefas com fila no próprio banco (`orm: default`), incluindo e-mails e importações. O acompanhamento de importações usa cache em tabela do banco. Alguns envios são enfileirados após o commit da transação.

O comando `request_scheduler` executa a rotina de acompanhamento de solicitações e resumos semanais. Sua execução periódica precisa ser configurada operacionalmente; o Compose não define um serviço separado para esse comando.

## Execução e implantação

- **Local:** Django `runserver` e compilação do Tailwind durante o desenvolvimento.
- **Web:** Gunicorn executa a aplicação WSGI; WhiteNoise está configurado para arquivos estáticos.
- **Worker:** processo separado executa `manage.py qcluster`.
- **Manutenção:** serviço `migrate`, ativado pelo perfil `maintenance`, aplica migrações, cria a tabela de cache, compila CSS e coleta estáticos.
- **Implantação com Docker:** Nginx e PostgreSQL ficam no host; o Compose publica a aplicação em `127.0.0.1:8080` por padrão e monta diretórios de estáticos e mídia. A aplicação também pode executar diretamente em um ambiente virtual, com Gunicorn e `qcluster` gerenciados pelo systemd.
- **Configuração:** variáveis de ambiente, com suporte a `.env`, definem banco, e-mail e opções da aplicação.

## Testes

Os testes existentes ficam em `core/tests.py` e `core/test_solicitacoes.py`. A listagem é verificada nos três perfis, incluindo ordenação, busca, filtros, paginação e atualização. `sistemadp/test_settings.py` utiliza SQLite em memória e e-mail em memória. Com as dependências e variáveis básicas configuradas, execute `python manage.py test core --settings=sistemadp.test_settings`. Comportamentos específicos do PostgreSQL, como concorrência e bloqueios, exigem validação nesse banco.

Fontes principais: [configurações](../sistemadp/settings.py), [serviços](../core/services.py), [Compose](../docker-compose.yml), [entrada dos processos](../entrypoint.sh) e [README](../README.md).
