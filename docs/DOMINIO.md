# Domínio do FluiDP

O FluiDP organiza solicitações de colaboradores ao Departamento Pessoal (DP), desde o preenchimento até o aceite, as aprovações e o processamento final. Este resumo descreve o código do repositório; configurações cadastradas no banco podem variar.

## Pessoas e estrutura

- **Colaborador:** abre solicitações, acompanha o histórico e realiza as ações permitidas em cada etapa.
- **Colaborador secundário:** colega envolvido no pedido, cujo aceite pode iniciar o fluxo.
- **Gestor e diretor:** analisam pedidos conforme a responsabilidade e a hierarquia.
- **DP:** administra cadastros, analisa solicitações e registra seu processamento.
- **Administrador do sistema:** possui acesso administrativo conforme os grupos e permissões.

O cargo define o nível hierárquico. A lotação representa uma unidade organizacional, pode ter uma unidade superior e possui chefias principal e secundária. A busca do aprovador considera a estrutura de lotações e os períodos de ausência.

## Conceitos principais

| Entidade | Responsabilidade |
| --- | --- |
| `CustomUser` | Identificação, matrícula, cargo, lotação, grupos e ausência do usuário. |
| `Cargo` e `Lotacao` | Estrutura funcional e organizacional. |
| `TipoDocumento` | Formulário configurável, prazos e opções de aprovação. |
| `Solicitacao` | Pedido, participantes, aprovador atual, estado e mês de referência. |
| `LogAprovacao` | Histórico de criação, decisões, edições, comentários e reversões. |
| `Notificacao` | Avisos associados aos usuários e às solicitações. |
| `Config` | Identidade visual e configurações gerais da instituição. |

Cada solicitação armazena uma cópia do esquema do formulário e dos valores preenchidos. Isso preserva a estrutura utilizada na abertura mesmo que o tipo de documento seja alterado depois.

## Ciclo da solicitação

O fluxo usual é: abertura → aceite do colega, quando houver → gestor → diretor, quando aplicável → DP → recebido pelo DP (`LANCAMENTO`) → aprovado (`FINALIZADO`). Algumas etapas variam conforme o responsável encontrado e as regras do documento.

Recusa e cancelamento encerram o pedido. Reversões permitidas desfazem decisões e registram o ocorrido no histórico. O autor pode editar antes de haver decisões de fluxo; o DP pode corrigir campos calculados nas etapas autorizadas. Arquivamento preserva o registro e é diferente de cancelamento.

## Datas e troca de plantão

Troca de plantão é representada como um tipo de documento, dentro do fluxo genérico de solicitações. Não há uma entidade própria de escala ou plantão no modelo atual.

A migração `0002_referencia_mensal` configura os documentos existentes chamados “Troca de Plantão” para abertura do dia 25 do mês anterior ao dia 10 do mês de referência, com antecedência mínima de dois dias. Ela marca os campos `data_plantao_origem` e `data_plantao_destino` para validar antecedência e pertencimento ao mês de referência. Essas regras dependem da configuração do documento.

O encerramento da janela de abertura não cancela solicitações em andamento. A rotina `request_scheduler` trata encaminhamentos, cancelamento de pedidos sem colega no estágio de aceite, arquivamento após 30 dias da finalização e resumos semanais.

## Recursos de apoio

O sistema oferece notificações internas e e-mails, relatórios para impressão, importação de colaboradores/cargos/lotações e interfaces por perfil, incluindo telas móveis.

Fontes principais: [modelos](../core/models.py), [serviços](../core/services.py), [rotina de acompanhamento](../core/management/commands/request_scheduler.py) e [manual do usuário](MANUAL_USUARIO.md).
