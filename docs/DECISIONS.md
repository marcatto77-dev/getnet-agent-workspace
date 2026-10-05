# Decisões de implementação

Este registro é cronológico: limitações descritas dentro de uma fase podem ter sido resolvidas por uma fase posterior. O estado consolidado e os critérios finais ficam em `docs/STATUS.md`.

## Revisão de atendimento — 05/10/2026 (política vigente)

- Escopo efetivo: Getnet + cotação de câmbio. Clima e assuntos aleatórios são recusados sem handoff; valores legados `challenge`/`strict` não alteram isso. Busca financeira aceita fontes Banco Central/BCE; suporte mantém RAG/site oficial Getnet.
- Handoff exige pedido explícito ou aceite da oferta. Após três respostas de assistência e insatisfação, a IA oferece atendimento humano e aguarda consentimento. Ausência de evidência exige esclarecimento, não transferência automática.
- O idioma identificado pelo Router acompanha a composição; evidências em português não substituem o idioma da pergunta. Mensagens operacionais têm versões em português, inglês e espanhol.
- Admin → Agentes e segurança mostra prompts e código dos guardrails em modo somente leitura, com RBAC e canário oculto. Não expõe segredos nem permite edição de prompts pelo navegador.
- Decisões históricas de escopo e escalonamento abaixo foram substituídas por esta revisão. Consulte `POLITICA_ATENDIMENTO.md` para os dez exemplos do desafio.

## Fase 1 — dados, autenticação e RBAC

- `customers.id` permanece textual e `external_id` é único, inicialmente com o mesmo valor. Isso preserva o contrato público `user_id=cliente...`, as referências existentes e os dados já indexados sem uma migração destrutiva.
- Colunas legadas de clientes e terminais foram preservadas durante a transição. As ferramentas usam as novas colunas e o catálogo `machine_models`; as colunas antigas mantêm compatibilidade com a entrega original.
- As tabelas legadas `handoffs` e `tickets` não foram recriadas como um novo domínio nesta fase. Elas são apenas preservadas no baseline Alembic porque já sustentam o quarto agente e testes do desafio original. `conversations`, `messages`, `agent_runs` e `tool_calls` não foram criadas.
- O bloqueio de login é local ao processo e combina IP com nome de usuário. É suficiente para o protótipo de uma instância; produção com múltiplas réplicas deverá usar armazenamento compartilhado.
- O admin pode acessar o placeholder técnico, mas técnico recebe `403` na rota administrativa. Isso permite suporte operacional sem ampliar privilégios do técnico.
- O seed cria credenciais somente se o usuário ainda não existir; reinicializações não sobrescrevem senhas alteradas no banco. Alterar a senha seed no ambiente após a primeira inicialização não redefine a conta existente.
- O cookie usa `SameSite=Lax`, `HttpOnly` e `Secure` configurável. O padrão `Secure=false` atende HTTP local; deve ser `true` atrás de HTTPS.

## Fase 2 — conversas e telemetria

- Existe no máximo uma conversa não encerrada por cliente, garantida por índice parcial único e lock transacional. Novas mensagens reutilizam essa conversa até que seu status seja `closed`.
- Mensagens preservam o conteúdo da conversa. Mascaramento é aplicado aos resumos operacionais de `tool_calls` e erros de `agent_runs`, evitando que CPF, cartão, e-mail ou telefone sejam replicados na telemetria.
- `tokens` armazena contadores reais informados pelo provedor, separados por tipo de chamada. `cost` permanece nulo enquanto não existir uma tabela de preços versionada; não estimamos custo com valores possivelmente desatualizados.
- O Escalation Agent continua existindo e roteando pedidos humanos, porém nesta fase responde informando que a transferência ainda não está disponível. Criação/atribuição de handoff fica reservada para a Fase 3.
- Cliente inexistente continua usando HTTP 404, agora com mensagem amigável. Isso preserva a semântica e o teste do contrato anterior sem criar conversas sem chave de cliente válida.
- `sessionStorage` mantém apenas o identificador público do cliente durante a aba atual. O histórico persistido ainda não possui endpoint público de leitura nesta fase.

## Fase 3 — handoff e atribuição

- As tabelas demonstrativas anteriores foram renomeadas para `legacy_handoffs` e `legacy_tickets`, preservando os dados e liberando o nome `handoffs` para o modelo ligado a conversas. O endpoint e o token de confirmação antigos foram removidos.
- A atribuição é serializada por um advisory lock transacional do PostgreSQL. É uma escolha simples e segura para o protótipo; em escala maior, o lock pode ser particionado por fila.
- Cada evento de disponibilidade atribui o próximo handoff FIFO. O algoritmo que escolhe o técnico não acessa banco e recebe candidatos já bloqueados pela transação.
- A expiração de atribuições offline é verificada oportunisticamente nas operações do serviço e também por uma tarefa periódica da API. O timeout vem de `HANDOFF_OFFLINE_TIMEOUT_SECONDS`.
- Encerrar um handoff devolve a conversa para `ai`; encerrar a conversa em si continua sendo uma operação separada. Nesta fase não há WebSocket nem tela operacional do técnico.

## Fase 4 — tempo real e workspace técnico

- O primeiro `POST /api/chat` cria uma sessão de cliente assinada em cookie HttpOnly. O WebSocket e o fallback REST validam simultaneamente essa sessão e a propriedade da conversa; conhecer apenas o UUID não concede acesso.
- O hub WebSocket é local ao processo e suficiente para a implantação demonstrativa de uma instância. Produção com múltiplas réplicas deve substituir o broadcast em memória por Redis/PostgreSQL pub-sub ou serviço equivalente.
- A desconexão do último socket técnico agenda a mudança para offline após o mesmo timeout configurável da reatribuição. Uma reconexão antes do prazo mantém o técnico online.
- Mensagens continuam sendo persistidas via REST antes do broadcast. O WebSocket transporta eventos e notificações, reduzindo o risco de perda de dados durante reconexões.
- O cliente usa polling periódico do histórico apenas enquanto o WebSocket está desconectado. O acesso permanece protegido pelo cookie assinado.
- Não foi necessária uma migration nesta fase: `messages`, `conversations`, `handoffs` e `technician_presence` já contêm os campos usados pelo fluxo em tempo real.

## Fase 5 — administração de usuários e máquinas

- Não foi criada migration: as tabelas `users`, `technician_presence`, `machine_models`, `terminals` e `audit_logs` já atendem o escopo desta fase.
- Usuários usam soft delete por `is_active=false`. A API não expõe exclusão física e impede autodesativação, remoção do papel do último admin e desativação do último admin ativo.
- A senha é aceita somente na criação ou redefinição, transformada imediatamente em Argon2 e nunca incluída em respostas ou diffs de auditoria. A auditoria registra apenas `credentials: password_updated`.
- Modelos e terminais compartilham `/api/admin/machines`, diferenciados por `kind`. A listagem é paginada e pesquisável; rotas de atualização/remoção incluem o tipo para evitar IDs ambíguos.
- Terminais podem ser removidos fisicamente porque são itens de inventário, enquanto modelos vinculados são protegidos por validação explícita. Alterações são lidas imediatamente pelas ferramentas do Support, sem cache.
- Dashboard e Base de conhecimento aparecem na navegação como “Em breve”. Logs já possui uma tela simples porque a auditoria faz parte desta fase.

## Fase 6 — gestão do RAG

- `rag_documents` passa a ser a fonte de verdade administrativa. A tabela `documents` foi preservada para compatibilidade do coletor legado, e `chunks.rag_document_id` liga todos os vetores ao novo modelo.
- A migration reconstrói o conteúdo dos documentos legados concatenando os chunks na ordem original. Nenhum chunk ou embedding é recriado durante a migration; os 56 vetores existentes são apenas vinculados.
- Criação e edição calculam embeddings antes de iniciar a escrita e gravam documento, chunks e auditoria em uma única transação. Falha do provedor não altera o estado anterior.
- Reindexação calcula todos os vetores antes da transação de substituição. Isso aumenta temporariamente o uso de memória, mas garante que uma falha não deixe o corpus parcialmente atualizado.
- O progresso da reindexação fica em memória, adequado à instância única de demonstração. Uma implantação distribuída deverá mover jobs e estado para uma fila compartilhada.
- Fontes manuais usam URI interna `manual://`, não exposta como link público. Na recuperação, recebem `kind=manual`, URL nula e o sufixo “conteúdo manual” no título.
- A ingestão por URL mantém a allowlist HTTPS oficial já usada pelo crawler, limites de download, extração e chunking existentes.

## Fase 7 — logs e dashboard

- “Atendimento” é uma conversa cujo `started_at` está no período. “Cliente em contato” é um `customer_id` distinto com ao menos uma mensagem de `sender_type=customer` no período, inclusive em conversa iniciada anteriormente.
- “Resolvido pela IA” corresponde a conversas iniciadas no período sem qualquer handoff; “escalado” corresponde a conversas do período com handoff. Fila e andamento usam o estado atual dessas conversas.
- Tempo médio de resposta usa `agent_runs.latency_ms`, a medição consistente disponível para todo o fluxo da IA. Latências das etapas/ferramentas são mostradas individualmente em `tool_calls`.
- Distribuição por rota usa execuções de agentes no período. A interface normaliza `knowledge`, `support`, `combined` e `escalate` para os nomes do desafio.
- O custo permanece a soma dos valores persistidos. Quando a aplicação não possui tabela de preços, `cost` continua nulo/zero, sem estimativa inventada.
- Logs aplicam novamente o mascaramento na leitura de input, output e erros. Isso protege também registros históricos anteriores ao mascaramento na escrita.
- A migration desta fase adiciona apenas índices para ferramenta/data, handoff/período, técnico/período e mensagens de cliente/data.

## Fase 8 — fechamento

- O bootstrap automático do RAG é habilitado no Compose por `RAG_AUTO_INGEST=true`, mas permanece desligado por padrão na configuração Python. Assim, testes e comandos locais não fazem chamadas pagas acidentais; o caminho Docker exigido faz a carga inicial.
- O bootstrap consulta `chunks` antes da ingestão. Um corpus existente é preservado sem coleta ou embeddings; falha no corpus vazio impede readiness em vez de iniciar uma aplicação aparentemente saudável sem conhecimento.
- Uma chave OpenAI válida é pré-requisito explícito do primeiro bootstrap. Embeddings portáveis não são versionados, evitando acoplar o repositório a artefatos do provedor e a snapshots potencialmente desatualizados.
- Os casos de handoff foram incorporados ao dataset principal com metadados de presença, carga e decisão esperada. O campo `route` preserva compatibilidade com o avaliador de roteamento existente.
- Testes de regressão controlados são a barreira determinística de CI. Avaliações com o modelo e busca web reais permanecem opt-in porque têm custo e variabilidade externa.
- Segredos de demonstração ficam apenas em `.env.example`, acompanhados de aviso. `.env`, relatórios, snapshots e resultados de testes permanecem ignorados pelo Git.

## Fase 9 — correções do teste manual

- O banner incorreto da Base RAG não era indisponibilidade do PostgreSQL nem migration ausente. A evidência mostrou Alembic em `0005_dashboard_log_indexes (head)`, 12 documentos/56 chunks, e o log da consulta revelou `AmbiguousColumn`: a busca referenciava `title`, `source` e `content` sem o alias de `rag_documents`, embora a junção de auditoria também expusesse colunas homônimas. As colunas foram qualificadas e erros SQL que não sejam falhas reais de conexão agora retornam erro interno com `request_id`, nunca “Banco indisponível”.
- O erro de Logs era um `422`: o frontend enviava `start=&end=&route=&...` e o FastAPI tentava validar strings vazias como datas. O cliente agora omite filtros vazios; o backend aceita vazio como ausência, faz parsing explícito e atribui `America/Sao_Paulo` a datas sem offset.
- Foi adicionada a migration idempotente `0006_phase9_canonical_routes`: normaliza rotas históricas, recria/vincula documentos RAG que eventualmente faltem e pode rodar novamente sem duplicar ou apagar chunks. O entrypoint continua executando `alembic upgrade head` antes do seed e da API; a migration original da Fase 6 deixou de depender de IDs coincidentes entre `documents` e `rag_documents`, permitindo upgrade seguro desde a Fase 5.
- Rotas persistidas usam exclusivamente `knowledge`, `support`, `knowledge_support`, `escalation`, `clarify` e `blocked`. “Web” é uma origem de conhecimento, não uma rota separada. Interfaces apresentam rótulos em português.
- Eventos públicos de handoff têm `event_id`. O servidor só publica posição quando ela muda e o cliente deduplica IDs, inclusive quando WebSocket e resposta HTTP chegam em ordem invertida.
- Em `DEMO_MODE`, o seed atualiza os recebíveis determinísticos em toda subida usando a data de São Paulo. Isso mantém “ontem” coerente sem afetar ambientes de produção nem criar linhas extras.
- Na validação com volume limpo, uma fonte sofreu erro transitório de embeddings depois de 11 documentos já confirmados. O bootstrap agora compara a quantidade de documentos indexados com o manifesto e tenta novamente até três vezes; reiniciar após uma carga parcial completa apenas a fonte ausente, preservando os 55 chunks já gravados. A recuperação foi comprovada chegando a 12 documentos/56 chunks.

## Fase 10 — perfil cliente e administração de clientes

- O login é unificado em `POST /api/auth/login`. O redirecionamento é feito por perfil: administrador para `/admin`, técnico para `/tecnico` e cliente para `/`. O `username` é o identificador único de acesso e permanece separado de `display_name`/`nome`, que podem se repetir.
- Clientes usam a mesma tabela `users`, ligados um-a-um a `customers` por `customer_id`. A constraint exige `customer_id` apenas para `role=cliente` e impede duas contas para o mesmo cadastro.
- `token_version` é incluído no JWT e conferido no banco em toda autenticação. Troca ou reset de senha e desativação incrementam a versão, invalidando imediatamente cookies anteriores sem armazenar tokens.
- Enquanto `must_change_password=true`, a sessão só pode consultar identidade, sair ou trocar a senha. A autorização é aplicada no backend, não apenas no redirecionamento do frontend.
- O contrato público de `POST /api/chat {message,user_id}` foi preservado. Quando existe sessão autenticada de cliente, o backend exige que `user_id` corresponda ao `customer_id` da sessão, bloqueando IDOR; o modo público demonstrativo anterior permanece disponível.
- Terminais legados recebem `serial_number=id` durante a migration. Novos terminais exigem serial no fluxo de Clientes; o CRUD legado de Máquinas usa o ID como serial quando ele não é informado, preservando compatibilidade.
- A senha inicial vem de `DEFAULT_CUSTOMER_PASSWORD`; o padrão `123` existe somente para demonstração e deve ser substituído em qualquer ambiente real.

## Fase 11 — portal e contexto de máquinas

- A raiz `/` não aceita mais identificação por `sessionStorage`: sem sessão exibe login do cliente e, com sessão `role=cliente`, exibe o portal. Admin e técnico continuam usando `/login` e suas áreas próprias.
- Em sessão autenticada, o `customer_id` é sempre derivado do JWT e confirmado no banco. Um `user_id` divergente ou `terminal_id` sem vínculo com o cliente retorna `403`; o LLM recebe somente o contexto já autorizado pelo servidor.
- O contrato original permanece compatível no modo anônimo de demonstração. `CHAT_ALLOW_ANONYMOUS_DEMO` pode sobrescrever o comportamento; quando ausente, ele só fica ativo se `DEMO_MODE=true`. Esse modo deve ser explicitamente desativado fora da demonstração porque `user_id` não é credencial.
- A máquina selecionada e um esclarecimento pendente ficam na conversa (`selected_terminal_id` e `pending_terminal_selection`), não no navegador. Uma máquina é escolhida automaticamente; com várias e uma ocorrência ambígua, a API devolve opções rápidas e aguarda a seleção.
- As ferramentas `list_customer_terminals` e `get_terminal_status` recebem identidade/terminal do código. A validação de propriedade ocorre antes do grafo; IDs sugeridos pelo modelo jamais autorizam acesso.
- Datas e outros tipos de banco no `customer_context` são serializados no limite do Router, mantendo o estado interno tipado e evitando falhas do provedor.

## Fase 12 — escopo e guardrails

- Guardrails são camadas de código em `backend/app/guardrails`, executadas antes e depois do grafo. Falha na inspeção de entrada resulta em bloqueio seguro e log JSON; decisões relevantes são persistidas em `guardrail_events`.
- `OFF_TOPIC_POLICY` herda `challenge` somente em `DEMO_MODE`; fora dele herda `strict`. `challenge` libera exclusivamente clima/câmbio geral para preservar os exemplos originais. `strict` recusa também essas utilidades.
- Dados sensíveis são normalizados e mascarados antes de mensagens, telemetria e LLM. A solicitação legítima pode continuar usando o texto redigido, acompanhada de aviso ao cliente; não é necessário persistir o valor original para responder.
- O detector determinístico é propositalmente limitado a sinais de alta precisão. A classificação estruturada do Router acrescenta `safety_label`, mas nunca concede identidade nem ferramentas; qualquer rótulo diferente de `ok` força rota bloqueada antes de uma ferramenta.
- Support possui allowlist fixa, no máximo quatro ferramentas de leitura e timeout por chamada. `customer_id` e terminal continuam injetados pelo servidor.
- A busca web Getnet envia `allowed_domains` ao provedor e também valida as citações retornadas. A exceção geral de clima/câmbio só existe em modo `challenge`.
- O RAG descarta resultados acima de `RAG_MAX_DISTANCE`. O valor padrão `0.8` é conservador para o corpus demonstrativo e deve ser recalibrado com métricas de recuperação antes de produção.
- Um canário não secreto detecta tentativa de reprodução do prompt. Ele é um sinal de contenção, não um segredo nem uma defesa isolada; saída também bloqueia enums internos, URLs não permitidas e alegações de ações não realizadas.

## Fase 13 — hardening de segurança

- A política de autorização de todas as operações OpenAPI é fail-closed e centralizada em `security.route_role`; uma rota nova sem classificação impede a geração do schema. As dependências `require_role` continuam sendo a autorização executável no backend.
- CSRF usa verificação de `Origin` em toda escrita autenticada em produção. No ambiente demonstrativo, a ausência de `Origin` continua aceita para preservar clientes CLI do desafio, mas uma origem presente e não confiável é recusada.
- O JWT de acesso tem renovação deslizante em `/api/auth/me`; `token_version` revoga também logout, troca/reset de senha e desativação. O cookie legado da conversa passou a conferir a mesma versão no banco.
- Rate limits implementam uma interface plugável, porém o adaptador atual é local ao processo. Redis é obrigatório antes de escalar horizontalmente.
- Ingestão URL valida esquema, domínio, porta, DNS e IP a cada redirecionamento; bloqueia destinos não globais, limita hops/tempo/tamanho/tipo e não encaminha cookies. Conteúdo com sinais de instrução é persistido como `pending` e `review_required`, sem gerar vetores antes da revisão.
- Conteúdo de conversa deixou de usar renderização Markdown e é exibido como texto React. CSP e demais cabeçalhos são aplicados tanto na API quanto no nginx.
- `audit_logs` é append-only por trigger. Retenção de mensagens é configurável; exportação e anonimização LGPD são ações administrativas auditadas.
- O PostgreSQL não fica publicado no Compose principal. `docker-compose.override.yml` mantém a porta exclusivamente para desenvolvimento local.

## Fase 14 — memória e resiliência

- A memória usa as últimas mensagens e um resumo incremental determinístico para manter o prompt limitado. Histórico e resumo são sempre conteúdo não confiável.
- Falhas de bootstrap do RAG não impedem a API de iniciar. A readiness assume `degraded=true` quando não há corpus utilizável e orienta reindexação/restauração.
- Circuit breaker e retry ficam no adaptador OpenAI, preservando resposta segura e encaminhamento ao técnico quando o provedor falha.
- A avaliação de roteamento pode rodar três vezes; groundedness completo exige execução end-to-end com fontes, portanto não é inferido de rodada routing-only.

## Fase 15 — Central de Atendimento

- `HANDOFF_MODE=manual` é o padrão seguro: a IA coloca o atendimento na fila e um técnico online o assume explicitamente. `auto` preserva o algoritmo determinístico da Fase 3.
- Pull exige motivo de ao menos 10 caracteres e não expõe esse motivo ao cliente; a mensagem pública informa somente a troca de responsável.
- A lista de atendimentos de outros técnicos contém apenas metadados e resumo. Histórico e notas internas dependem de posse do handoff.
- `MAX_CHATS_PER_TECH=5` limita carga; `0` desativa o limite explicitamente para demonstração.

## Fase 16 — Tela de Atendimento

- `/tecnico/atendimento` é a rota canônica e `/tecnico` somente redireciona para ela. A implementação reutiliza um único componente para evitar duas telas técnicas divergentes.
- A interface consome os contadores canônicos da Central e mantém WebSocket com polling de oito segundos como fallback. A autorização e a posse do atendimento continuam exclusivamente no backend.
- Mensagem pública e nota interna usam compositores distintos. Conteúdo recebido é renderizado como texto React; notas internas nunca são publicadas no WebSocket do cliente.
- Ao assumir ou puxar, a tela abre imediatamente a conversa atribuída. Conflitos `409` recarregam a lista e apresentam uma mensagem amigável.
- Eventos públicos persistidos carregam `message_id`, permitindo deduplicar a mesma atualização recebida por WebSocket e posteriormente pelo polling.
- A disputa entre `pull` e `transfer` usa verificação otimista da versão observada antes do bloqueio da linha; somente uma ação concorrente vence.

### Melhoria de fila da Central

- Técnicos podem consultar uma prévia pública de um atendimento ainda em fila antes de assumir. A prévia expõe somente mensagens públicas e o resumo do Escalation; notas internas e dados de outros atendimentos continuam inacessíveis.
- A fila é renderizada como lista operacional central, com problema em linguagem natural, tempo de espera, `Ver chat` e `Assumir`. O JSON estruturado do Escalation é convertido no frontend para o campo `problem` e as tentativas relevantes.

## Administração de máquinas — serial como identificador visível

- O `terminals.id` permanece como chave interna para preservar conversas, vínculos e APIs existentes. A tela administrativa usa `serial_number` como identificador principal, exige serial único em novos terminais e gera uma chave interna quando ela não é enviada.
- O serial aceita letras, números e hífen e é normalizado para maiúsculas ao salvar. O catálogo de modelos mantém a contagem de terminais vinculados.
- Os dois terminais demonstrativos usam os seriais fictícios `A1B2C3` e `D4E5F6`.
- Cadastro e edição de máquinas são feitos em modal na própria página, com seleção por nome de cliente/modelo; o ID interno deixa de ser solicitado ao administrador.

## Identidade do cliente no chat autenticado

- No portal, `/api/chat` resolve o cliente exclusivamente pela sessão autenticada. O frontend não envia nem pede `user_id`; assim, qualquer usuário ativo com perfil `cliente` conversa após entrar e cumprir a troca obrigatória de senha, se aplicável.
- `user_id` permanece opcional no contrato para compatibilidade com integrações existentes e é exigido apenas no chat anônimo de demonstração. Quando enviado junto de uma sessão, precisa corresponder ao cliente autenticado.

## Respostas antes do encaminhamento humano

- Um retorno vazio de uma ferramenta pessoal, como recebíveis de um novo cliente, não prova que a Getnet não publicou orientação geral. O Support consulta o RAG para essa orientação; se a resposta continuar insuficiente, o Knowledge pesquisa apenas domínios oficiais permitidos. O handoff automático ocorre somente depois de ambas as fontes não fornecerem resposta verificável, ou por pedido explícito do cliente.
- Contagens antigas de falha não causam encaminhamento automático de uma nova pergunta. Se houver resposta pública mas faltarem dados individuais, o agente declara essa limitação e oferece a opção de pedir um técnico, sem criar chamado por conta própria.
- Os quatro manuais oficiais em PDF entram no manifesto de fontes. PDFs recebem limite próprio de 10 MB/100 páginas; o teto HTML permanece em 2 MB. A extração mantém validação SSRF, checagem de robots, detecção de instruções suspeitas, citações por URL oficial e vetorização transacional.
- Diagnóstico real da busca web: `gpt-4.1-mini` retorna HTTP 400 quando recebe `filters.allowed_domains`. Nesse modelo, omitimos o filtro incompatível, instruímos o provedor a usar fontes oficiais e descartamos citações fora da allowlist. Outros modelos continuam recebendo o filtro quando suportado; se responderem que `filters` não é compatível, a chamada é repetida uma vez sem esse parâmetro e a validação local de citações permanece obrigatória.

## Consulta ampla sobre modelos e fallback web sem confirmação

- A pergunta “todos os modelos de máquina” recuperava trechos vetoriais periféricos e perdia a intenção de lista quando o Router encurtava `search_query`. Para essa intenção específica, o Knowledge preserva a pergunta original e recupera um trecho de cada manual oficial em PDF, mantendo diversidade de fontes. A resposta enumera somente os modelos documentados e declara que os manuais não comprovam catálogo completo nem disponibilidade de venda atual.
- O `gpt-4.1-mini` pode devolver links externos no corpo da busca mesmo que parte das citações seja oficial. Uma resposta com URL externa não é aproveitada: o provedor devolve ausência de fonte utilizável, e o fluxo continua com sua política de evidência/handoff. Nunca mostramos a frase “posso buscar no site” depois de uma busca que já ocorreu, nem pedimos permissão para consultar páginas públicas oficiais.

## Ciclo de vida de cada atendimento

- A interface do cliente só restaura automaticamente conversas em fila ou atribuídas a um técnico. Assim, sair e voltar não esconde uma resposta humana pendente. Para uma visita nova sem atendimento humano ativo, a primeira mensagem autenticada abre uma nova conversa e fecha a conversa anterior de IA; mensagens na mesma tela enviam `conversation_id` opcional, validado no backend contra a sessão. O contrato legado `{message, user_id}` e o reaproveitamento no modo anônimo de demonstração permanecem.
- O técnico encerra o handoff **e** a conversa. A próxima pergunta do cliente à IA cria outra conversa, sem acrescentar mensagens ao atendimento encerrado. O cliente também pode encerrar a própria conversa, inclusive na fila ou com técnico, com checagem de propriedade e atualização atômica de handoff, auditoria e eventos.
- A consulta de um atendimento encerrado limita mensagens por `handoffs.closed_at` e aceita o `handoff_id` específico da lista. Isso mantém legíveis os registros antigos que, antes desta correção, podiam compartilhar uma conversa com mensagens posteriores. Não apagamos dados históricos.
- O aviso público de encerramento é gravado na mesma transação e com o mesmo instante do fechamento, de modo que apareça no recorte histórico do técnico e não exista janela em que a conversa esteja fechada sem a mensagem final.
