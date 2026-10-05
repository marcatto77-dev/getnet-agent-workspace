# Relatório de teste funcional e usabilidade

**Data:** 04/10/2026
**Ambiente:** portal local em `127.0.0.1:8080`, dados de demonstração
**Método:** teste manual orientado a papéis, com navegador em viewport de 768 × 864 px. Nenhuma ação destrutiva foi executada.

## Resultado executivo

Os fluxos navegáveis dos três papéis estão operacionais: autenticação, portal do cliente, consultas de máquinas e conta, administração de usuários/clientes/máquinas/base/logs e Central técnica/histórico. O bloqueio de código no chat também foi validado pela interface, sem chamar a IA.

Foram encontrados dois problemas de usabilidade/informação; nenhum defeito funcional bloqueante foi observado no escopo executado.

| ID | Severidade | Situação |
|---|---|---|
| UX-01 | Média | Painel administrativo extrapola a largura em tablet e exige rolagem horizontal da página |
| UX-02 | Baixa | Dashboard apresenta métricas com bases diferentes sem explicá-las |

## Casos executados

| Perfil | Caso | Resultado |
|---|---|---|
| Cliente | Login com `cliente1988`; abertura do atendimento | Passou: portal apresentou identificação de Café Aurora e chat disponível |
| Cliente | Consulta de “Minhas máquinas” | Passou: Get Smart, serial mascarado, estado offline e atalho de ajuda apresentados |
| Cliente | Consulta de “Minha conta” | Passou: dados cadastrais e formulário de troca de senha exibidos |
| Cliente | Envio de bloco Python fora de escopo | Passou: mensagem foi bloqueada e respondeu com texto de escopo; não houve resposta sobre o código |
| Administrador | Login; usuários, clientes, detalhes de cliente e busca | Passou: listagem, filtro e modal de detalhes funcionaram |
| Administrador | Dashboard | Passou: indicadores, período e tabela de técnicos carregaram |
| Administrador | Máquinas | Passou: terminais, associação com cliente/modelo e ações disponíveis exibidos |
| Administrador | Base de conhecimento | Passou: documentos, origem, status de embedding, filtros, paginação e ação “Reindexar aprovados” exibidos |
| Administrador | Logs | Passou: execuções, filtros e status de guardrails carregaram |
| Técnico | Login e disponibilidade | Passou: Central abriu em estado Online e com tempo real ativo |
| Técnico | Fila sem atendimentos | Passou: estado vazio é claro e sem erro visual |
| Técnico | Histórico encerrado, busca/filtro e paginação | Passou: lista e página 2 carregaram corretamente |

## Bugs encontrados

### UX-01 — rolagem horizontal indevida no Admin em largura de tablet

**Reprodução:** abrir `/admin` em viewport de 768 px e acessar Usuários, Clientes ou Máquinas.

**Resultado atual:** há barra de rolagem horizontal no nível da página. A navegação lateral fixa com 245 px, combinada à tabela com `min-width: 700px`, deixa a área principal maior que o viewport.

**Impacto:** em tablets e janelas estreitas, o usuário precisa deslocar a página inteira para acessar a tabela e suas ações; isso prejudica leitura e aumenta risco de ação na linha errada.

**Correção sugerida:** aplicar `min-width: 0` a `.admin-main` (item de grid), manter a rolagem restrita a `.admin-table` e criar breakpoint intermediário, por exemplo entre 701 e 1000 px, para reduzir sidebar/padding e preservar a tabela dentro da área de conteúdo.

**Aceite:** em 768 px, não existe scroll horizontal no `body`; apenas a área de tabela pode rolar horizontalmente, se necessário, sem esconder navegação nem botões de ação.

### UX-02 — métricas do Dashboard são ambíguas

**Reprodução observada:** no período “Hoje”, o card mostrou **Atendimentos: 3**, enquanto a distribuição por rota exibiu **Bloqueado: 4** e **Conhecimento: 2**.

**Causa:** “Atendimentos” e o gráfico diário contam conversas; a distribuição por rota conta execuções de agentes, incluindo bloqueios. Ambas podem estar corretas, mas a tela não informa que são universos distintos.

**Impacto:** um administrador pode interpretar o dashboard como inconsistente ou concluir que os bloqueios são atendimentos resolvidos.

**Correção sugerida:** renomear/explicar indicadores, por exemplo “Conversas iniciadas”, “Execuções por rota (inclui bloqueios)”, e incluir tooltip/legenda de origem e período. Avaliar também separar bloqueios do gráfico principal.

**Aceite:** a soma e o significado das métricas ficam explícitos na interface, sem exigir conhecimento do modelo de dados.

## Cobertura pendente

- Handoff completo (cliente pede humano → técnico assume → mensagem em tempo real → transferência/nota/encerramento). Não foi disparado porque a mensagem de escalonamento aciona o provedor de IA e pode consumir crédito; a fila estava vazia.
- Criação/edição/desativação de usuários, clientes, máquinas e documentos RAG. Foram evitadas para não modificar dados persistentes de demonstração.
- Reindexação e perguntas RAG completas. A ação pode consumir embeddings/modelo e deve ser feita em homologação com orçamento aprovado.
- Troca de senha: a tela foi verificada, mas a alteração de credencial não foi executada.

## Recomendação de reteste

Após corrigir UX-01 e UX-02, executar Playwright em desktop, 1024 px, 768 px e 375 px. Em ambiente descartável e com crédito autorizado, executar os testes reais já existentes para handoff e tempo real (`phase16-real`, `technician-realtime-real` e `technician-closed-real`).
