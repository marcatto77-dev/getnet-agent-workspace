# Estado do projeto e histórico de validações

**Revisão vigente em 05/10/2026:** escopo Getnet + câmbio; clima recusado sem transferência. Handoff somente a pedido explícito ou após três respostas de assistência, insatisfação, oferta e aceite do cliente. Admin → Agentes e segurança mostra prompts e guardrails em modo somente leitura. Última suíte integral: 163 testes backend aprovados em banco de teste recriado e 15 Playwright controlados aprovados. Smokes reais de telas e do novo painel aprovados; dez rotas e três classificações de consentimento passaram com modelo real. Após o ajuste final de idioma, 54 testes focados e respostas RAG reais em inglês/espanhol passaram. Câmbio sem fonte atual é tratado sem inventar cotação. Descrições de `challenge`/`strict` e escalonamento automático abaixo são históricas; README e `POLITICA_ATENDIMENTO.md` documentam a política atual.

**Estado consolidado em 04/10/2026:** o projeto inclui as Fases 1–16 e os ajustes posteriores de chat, Central, administração, segurança de IA e usabilidade. A migration atual é `0014_rag_review`; no ambiente local, API/web/banco estão saudáveis e o RAG respondeu com 241 chunks, `degraded=false`. Login e chat usam rate limit compartilhado em PostgreSQL; documentos RAG suspeitos exigem revisão administrativa e não entram na reindexação. O Dashboard distingue conversas, execuções de agentes, eventos bloqueados e estado atual da fila. Consulte o [README](../README.md), o [reteste de segurança](RETESTE_SEGURANCA_IA_2026-10-04.md) e o [reteste funcional](RETESTE_FUNCIONAL_2026-10-04.md) para reprodução.

**Atualização de validação em 04/10/2026:** suíte backend completa aprovada em `getnet_test` recém-criado (138 testes); Ruff e Bandit aprovados; `pip-audit` sem vulnerabilidades conhecidas após PyJWT 2.15.0; `npm audit` e build de produção aprovados; Trivy sem vulnerabilidades corrigíveis altas/críticas na imagem da API; Gitleaks sem achados nos 200 arquivos candidatos ao Git; Playwright com 13 testes controlados e dois smokes reais aprovados. Em um banco Docker isolado e vazio, as 16 fontes oficiais foram ingeridas em 240 chunks e a API retornou `degraded=false`. A avaliação histórica de agentes mede roteamento; respostas factuais ainda devem ser comparadas manualmente às fontes. As seções abaixo registram a evolução por fase: números, migrações e problemas descritos nelas refletem a data daquela execução. Use o [README](../README.md) e a [matriz de aderência](ADERENCIA_DESAFIO.md) para o estado atual.

## Ajustes recentes da administração de máquinas

- A tabela de terminais exibe o serial da máquina como identificador principal; novos seriais aceitam letras, números e hífen e são salvos em maiúsculas. O ID interno é gerado pelo backend quando não enviado. Os seriais demonstrativos são `A1B2C3` e `D4E5F6`.
- Cadastro/edição de terminais e modelos usam formulários na página, com seletores de cliente e modelo. O catálogo mostra a quantidade de terminais ligados a cada modelo.
- Build de produção do frontend validado após a alteração; as imagens Docker foram reconstruídas na validação final de 04/10/2026.

## Estado entregue

- Portal autenticado do cliente com chat, máquinas, conta e navegação responsiva, sem telemetria interna.
- Router, Knowledge, Support e Escalation em LangGraph; RAG PostgreSQL/pgvector e busca web.
- Persistência de conversas, mensagens, execuções, ferramentas e auditoria com mascaramento de dados sensíveis.
- Handoff automático, fila FIFO, distribuição determinística e atendimento técnico por WebSocket com fallback REST.
- Administração de usuários, máquinas, RAG, dashboard e logs operacionais.
- Alembic, seed idempotente e bootstrap idempotente do corpus RAG no primeiro `docker compose up --build`.
- Erros HTTP padronizados com `code`, `message` e `request_id`; filtros vazios e datas locais são tratados de forma consistente.
- Rotas canônicas, datas relativas de recebíveis, fontes públicas amigáveis e eventos de fila deduplicados.
- Perfil cliente com login unificado, troca obrigatória de senha, revogação de sessões e isolamento do cadastro no backend.
- Administração de clientes, contatos e terminais com serial único, transferência, soft delete, reset de senha e auditoria.
- Contexto de máquinas autorizado no backend, seleção automática/assistida de terminal e opções rápidas persistidas na conversa.
- Pipeline de guardrails com escopo Getnet, políticas challenge/strict, redação de PII, proteção contra prompt injection, ferramentas limitadas, validação de saída e observabilidade administrativa.

## Validação da Fase 12

- Migration `0009_phase12_guardrails` aplicada no volume existente e em banco vazio; ambos chegaram ao `head`.
- 81 testes Python passaram com PostgreSQL real. Incluem camadas determinísticas, RBAC do endpoint, persistência mascarada, card do dashboard, 42 ataques, 22 casos legítimos difíceis e os dez cenários originais em `challenge`/`strict`.
- O red-team determinístico bloqueou todos os ataques cobertos e mediu zero falsos positivos nos 22 casos legítimos do dataset.
- Build TypeScript/Vite passou e 11 testes Playwright controlados passaram; quatro fluxos reais permanecem opt-in.
- Playwright real passou com volume existente e novamente após `docker compose down -v`, sem banner, `[object Object]` ou 4xx/5xx inesperado.
- Evidências: `docs/evidence/fase12/bloqueio-chat.png`, `admin-guardrails.png` e `dashboard-bloqueios.png`.

## Validação da Fase 11

- Migration `0008_phase11_customer_portal` aplicada no volume existente e desde banco vazio; Alembic confirmou `head` nos dois cenários.
- 68 testes Python passaram com PostgreSQL real, incluindo IDOR de terminal, seleção automática, esclarecimento com múltiplas máquinas, cliente sem terminal, divergência sessão × `user_id`, modo anônimo e regressão do desafio.
- Build TypeScript/Vite passou; 11 testes Playwright controlados passaram (3 cenários reais ficam opt-in).
- O Playwright real passou no volume existente e novamente após `docker compose down -v`/`up --build`, cobrindo criação administrativa, login inicial, troca obrigatória, chat, máquinas, pré-seleção, conta e logout, sem banner, `[object Object]` ou 4xx/5xx inesperado.
- Evidências reais: `docs/evidence/fase11/atendimento.png`, `minhas-maquinas.png`, `minha-conta.png` e `login-cliente.png`.

## Validação da Fase 10

- Migration `0007_phase10_customer_accounts` aplicada no volume existente e desde banco vazio.
- 65 testes Python passaram, incluindo RBAC, IDOR, política/troca/reset de senha, revogação de sessão, serial único, auditoria sem credenciais, seed idempotente e migrations.
- 11 testes Playwright controlados e o fluxo real Admin → novo cliente → login com senha inicial → troca obrigatória → portal do cliente passaram.
- Evidências reais: `docs/evidence/fase10/admin-clientes.png`, `troca-obrigatoria.png` e `cliente-logado.png`.

## Fase 13 — hardening de segurança

- Sessões, escritas autenticadas e WebSockets possuem controles de origem, tamanho, frequência e expiração; logout agora revoga o token no banco.
- CORS, CSP, HSTS de produção, cabeçalhos defensivos, schemas estritos e política explícita por rota foram centralizados.
- Na Fase 13, o chat ganhou limite por cliente/IP e orçamento diário de tokens. O limitador inicialmente em memória foi substituído por PostgreSQL compartilhado em 04/10/2026.
- A ingestão RAG aplica defesa SSRF completa e envia conteúdo suspeito para revisão sem indexação. Auditoria é imutável por trigger.
- Exportação, anonimização e retenção configurável cobrem o fluxo LGPD mínimo. O chat informa a política e evita renderização ativa de conteúdo não confiável.
- O Compose aplica usuário não-root, capacidades mínimas, filesystem somente leitura onde viável, tmpfs, healthchecks e limites; o banco só é exposto pelo override local.
- CI e Dependabot cobrem lint, testes e scans de dependências, código, histórico Git e imagens. Detalhes operacionais estão em `SECURITY.md` e ameaças em `docs/THREAT_MODEL.md`.
- Validação final: 94 testes Python, 11 Playwright controlados, 1 Playwright real pós-volume-limpo, Ruff, build Vite e `npm audit` passaram. Docker foi validado com volume existente e após `down -v`; Alembic chegou a `0010`, seed criou 4 usuários/2 clientes e o RAG gerou 55 chunks a partir do conteúdo atual das 12 fontes.
- Evidências reais: `docs/evidence/fase13/tecnico.png`, `chat-xss-texto.png` e `admin-logs.png`.

## Inventário cumulativo de pendências e riscos

### Segurança e identidade

- A identificação pública legada por `user_id` continua disponível para preservar o desafio. Em produção, desabilitar o modo público e exigir conta autenticada ou identidade federada para todos os clientes.
- A senha demo padrão `123` é deliberadamente fraca. Produção deve exigir segredo inicial aleatório ou convite de ativação com expiração.
- Não há MFA, recuperação de senha por canal verificado, política de histórico nem detecção de credenciais vazadas.
- Cookies usam `Secure=false` somente no HTTP local; produção força `Secure`, valida `Origin` nas escritas e exige HTTPS. Rotação automática do segredo JWT ainda não foi implementada.
- Rate limit, bloqueio de login e progresso de reindexação ficam em memória de uma instância; mover para Redis ou armazenamento compartilhado antes de escalar horizontalmente.
- O orçamento diário de tokens também depende do PostgreSQL local da aplicação; definir alertas no provedor continua necessário como segunda barreira contra custo.

### Dados e integrações

- Clientes, terminais, recebíveis e status são dados fictícios. APIs oficiais Getnet, consentimento, reconciliação e tratamento de indisponibilidade externa continuam pendentes.
- E-mail e telefone são opcionais e ainda não passam por verificação de posse. Normalização internacional e validação avançada devem ser adicionadas.
- Desvincular terminal mantém o registro sem cliente e ele deixa a listagem padrão baseada em cliente; uma futura tela de estoque deve listar explicitamente terminais não vinculados.
- Retenção, exportação e anonimização LGPD foram implementadas; base legal, prazos definitivos, atendimento formal ao titular e descarte de backups ainda exigem validação jurídica/operacional.

### Arquitetura e operação

- Hub WebSocket e eventos em tempo real são locais ao processo. Implantação com múltiplas réplicas exige pub/sub compartilhado e presença distribuída.
- A defesa SSRF valida DNS antes de cada requisição/redirecionamento, mas ambientes de alta criticidade ainda devem usar proxy de saída que faça DNS pinning e bloqueio de rede no nível da infraestrutura.
- `audit_logs` é imutável para a conta normal da aplicação, mas administradores/superusuários do PostgreSQL podem desabilitar triggers; restringir e auditar acesso privilegiado ao banco.
- A verificação CSRF aceita clientes sem `Origin` fora de produção para compatibilidade com curl/testes do desafio. Somente `APP_ENV=production` ativa a exigência fail-closed para toda escrita autenticada.
- O advisory lock global da fila é adequado ao protótipo, mas deve ser particionado ou substituído para grande volume.
- Bootstrap e reindexação RAG dependem de rede e OpenAI; existem retries para carga inicial, mas faltam fila durável, backoff prolongado e retomada observável por documento.
- Adicionar métricas, tracing distribuído, SLOs, alertas externos, backup/restauração ensaiados e runbooks operacionais.

### IA, qualidade e produto

- A memória é deliberadamente curta e determinística; sumarização semântica, memória de longo prazo e preferências persistentes exigem avaliação de privacidade e qualidade antes de adoção.
- Busca híbrida, reranking, avaliações de groundedness/recall e proteção adicional contra prompt injection permanecem futuras.
- Guardrails determinísticos reduzem ataques conhecidos, mas não provam ausência de jailbreak. Ofuscações novas, idiomas adicionais e injeções semânticas exigem atualização contínua do red-team.
- O limiar vetorial padrão precisa ser recalibrado quando o corpus, modelo de embedding ou idioma mudar; um valor inadequado pode aumentar recusas ou aceitar contexto fraco.
- Toxicidade é detectada por padrões de alta precisão e não por classificador especializado; isso reduz falsos positivos, mas não cobre toda forma de abuso contextual.
- O timeout com thread limita a espera da requisição, mas não cancela de forma garantida uma operação de driver já em execução; produção deve combinar timeout da aplicação com `statement_timeout` e cancelamento do provedor.
- Custos continuam nulos quando não há tabela de preços versionada; implementar versionamento de preços antes de usar dados financeiros do dashboard.
- O portal permite consultar dados e trocar senha, mas ainda não permite editar e-mail/telefone nem recuperar acesso por canal verificado. Recebíveis continuam acessíveis pelo chat, sem extrato estruturado.
- A seleção de máquina usa heurística determinística para decidir quando uma ocorrência é ambígua; linguagem muito indireta ainda pode depender da classificação do modelo.
- O modo anônimo existe apenas por compatibilidade com o desafio e expõe dados fictícios por identificador. Manter `CHAT_ALLOW_ANONYMOUS_DEMO=false` em qualquer ambiente não demonstrativo.
- A conversa mantém uma máquina selecionada até nova seleção; ainda não há controle explícito no chat para trocar de terminal sem voltar a “Minhas máquinas”.

### Dívida técnica e testes

- Permanecem warnings do pytest sobre marcações não registradas e uma depreciação do `TestClient`; cadastrar os markers e atualizar a dependência/test harness.
- Na época da Fase 11, Ruff reportava dívida de estilo e imports; a limpeza posterior foi concluída e a validação de 04/10/2026 passou.
- O frontend ainda usa `prompt`/`confirm` em partes administrativas antigas e no vínculo de terminais; substituir por modais acessíveis e testes de teclado/leitor de tela.
- Ampliar testes de concorrência para reset/desativação simultâneos e testes de carga para listagens, WebSocket e fila.

## Validação da Fase 9

- Diagnóstico no volume existente: banco saudável, 12 documentos RAG, 56 chunks e Alembic inicialmente em `0005`; os logs confirmaram `AmbiguousColumn` no RAG e `422` por datas vazias em Logs.
- Após o upgrade: Alembic em `0006_phase9_canonical_routes`, dados preservados e rotas históricas normalizadas.
- Evidências visuais reais ficam em `docs/evidence/fase9/` e cobrem chat, fila, todas as telas administrativas e área técnica.
- Volume limpo: migrations `0001`–`0006`, seed de 2 usuários/2 clientes e corpus de 12 documentos/56 chunks; uma falha transitória de embedding foi recuperada idempotentemente sem perda dos 55 chunks já gravados.
- Validação final: 63 testes Python (incluindo PostgreSQL e migration Fase 5 → head), 11 testes Playwright controlados, 1 smoke Playwright real e build TypeScript/Vite no Docker. A análise estática dos arquivos alterados passou; permanecem apenas três warnings conhecidos da infraestrutura pytest.

## Fase 14 — memória, resiliência e avaliação

- O histórico limitado e resumo incremental são montados no servidor e entram nos prompts como conteúdo não confiável. Router, composição Knowledge/Support e Escalation usam o mesmo contexto.
- OpenAI usa timeout, retry exponencial e circuit breaker; indisponibilidade retorna mensagem amigável e caminho de handoff.
- Bootstrap RAG agora degrada sem derrubar a API. Readiness informa `degraded` e uma ação de reindexação; `backend/scripts/rag_snapshot.py` permite criar/restaurar dump de chunks.
- `/metrics` expõe formato Prometheus restrito; alertas sugeridos estão em `docs/ALERTS.md`.
- Em Docker limpo, a API chegou a `0011_phase14_memory`, o seed criou os dados demo e o RAG indexou 55 chunks; readiness retornou `ready`. O smoke Playwright real de cliente, admin e técnico passou e salvou imagens em `docs/evidence/fase14/`.
- O roteamento dos 10 cenários originais foi medido três vezes, com 100% nas três execuções. `evals/report.md` deixa explícito que groundedness, custo e latência exigem a rodada end-to-end aprovada.

## Fase 15 — Central de Atendimento (backend)

- Migrations `0012_service_center` e `0013_service_center_compat` adicionam estados operacionais, FIFO por `waiting_since`, eventos, notas internas e compatibilidade para inserções legadas.
- O serviço centraliza assumir, puxar, encaminhar, devolver à fila, encerrar e timeout. `HANDOFF_MODE=manual` é padrão e `auto` preserva o algoritmo legado.
- A API técnica expõe fila, contadores, atendimentos próprios/de terceiros, encerrados, técnicos e ações; `docs/ROLES.md` registra a separação de privacidade.
- A validação dedicada cobre fluxo manual completo, privacidade de nota interna, RBAC, timeout com prioridade preservada, WebSocket público/técnico, dez técnicos concorrendo pelo mesmo handoff e corrida pull × transfer. Foram 9 testes de Central/migration e 7 regressões de handoff/WebSocket em modo auto, todos aprovados.
- O smoke Playwright real comprovou acesso técnico e bloqueio do cliente, sem banner de erro nem `[object Object]`; evidências em `docs/evidence/fase15/`. O banco demo está em `0013_service_center_compat` e saudável.

## Fase 16 — Tela de Atendimento do técnico

- A antiga área técnica foi substituída pela Central responsiva em `/tecnico/atendimento`; `/tecnico` redireciona para a mesma implementação.
- Cabeçalho, presença, estado da conexão, fila, atendimentos próprios/de terceiros e encerrados usam os endpoints da Fase 15 e atualização em tempo real com fallback por polling.
- Ações de assumir, puxar, encaminhar, devolver à fila e encerrar possuem estados e diálogos próprios. Notas internas ficam visualmente separadas das mensagens públicas.
- O chat atribuído exibe histórico completo e contexto autorizado: cliente, máquinas, resumo do Escalation e linha do tempo do handoff. Atendimentos encerrados são somente leitura.
- O cliente recebe mudanças públicas com deduplicação por `event_id`/`message_id` e continua sem acesso, link ou indicação da Central.
- O recuo lateral causado pela regra global legada `main { margin-left: 246px }` foi neutralizado especificamente em `.center-shell`, mantendo a Tela de Atendimento em largura total.
- A fila agora ocupa a área central como lista operacional. Cada item apresenta cliente, máquina, motivo, resumo legível, tempo de espera, botão `Ver chat` e botão `Assumir`; a prévia mostra apenas o histórico público antes da atribuição.
- Validação: build Vite aprovado; 8 testes dedicados da Central, 98 testes legados em modo `auto` e 11 Playwright controlados aprovados. Playwright real validou cliente → fila → assumir, isolamento do cliente e três contextos reais com Tecnico1/Tecnico2, pull, nota interna privada e encerramento. Evidências em `docs/evidence/fase16/`.

### Pendências e riscos após a Fase 16

- O hub WebSocket e a presença continuam em memória de uma instância; múltiplas réplicas exigem Redis/pub-sub e presença distribuída.
- O som de notificação permanece opcional e não foi habilitado por padrão para evitar reprodução sem consentimento do navegador.
- A validação visual automatizada cobre desktop; ampliar a matriz real para diferentes navegadores, leitor de tela e dispositivos móveis físicos.
- Listas muito grandes usam paginação somente em Encerrados; fila e atendimentos ativos deverão adotar paginação ou virtualização em escala elevada.
- Pull e encerramento possuem cobertura visual real com dois técnicos; encaminhar/devolver à fila e a corrida de ações permanecem cobertos deterministicamente no backend. Ampliar também esses dois caminhos na automação visual é uma melhoria de cobertura, não uma lacuna funcional conhecida.

## Ajuste posterior: resposta fundamentada antes de handoff

- O Router não transforma contagem de falhas anteriores em novo chamado. Para perguntas sem pedido humano explícito, Support/Knowledge buscam evidências no cadastro e RAG; se a composição continuar insuficiente, tentam o site oficial Getnet antes de abrir handoff.
- Quatro manuais oficiais em PDF (Get Smart, Get Clássica, Get Mini e Get Lite) foram adicionados ao manifesto, extraídos e indexados no volume existente: 185 chunks novos, 240 no total. `GET /api/health/ready` reportou `degraded=false`.
- A primeira chamada real revelou HTTP 400 do web_search: `gpt-4.1-mini` não suporta o parâmetro `filters`. O adaptador foi corrigido para omiti-lo nesse modelo e validar localmente os domínios das citações. A nova chamada web retornou apenas URL `site.getnet.com.br`.
- Regressão backend local: 74 testes aprovados, 36 ignorados por exigirem banco de teste dedicado. A pergunta real sobre vendas de ontem para `cliente1988` retornou `support/ok`, com data prevista e fonte “Seus recebíveis”, sem handoff. A consulta vetorial “Como conectar Get Smart ao Wi-Fi?” recuperou o manual Get Smart em primeiro lugar. Injeção de prompt e receita fora de escopo foram bloqueadas com mensagens Getnet.
- Smoke Playwright real contra Docker: login de administrador, quatro manuais visíveis e indexados, login de cliente e resposta à pergunta de Wi-Fi com citação do manual Get Smart, sem banner de erro ou `[object Object]`. Evidências em `docs/evidence/rag-manuais/`.
- Correção posterior para pergunta ampla de modelos: trace real mostrou RAG sem diversidade (apenas trechos do Get Smart) e busca web com URLs externas, bloqueada pelo guardrail de saída. O Knowledge agora inclui os quatro manuais na recuperação de catálogo e formula a lista somente dos modelos documentados, com ressalva de atualidade; consulta ao site é automática, e resposta web contendo link não permitido é descartada. A mesma pergunta do print retornou `knowledge/ok` com quatro citações, sem pedir permissão ou abrir handoff. Regressão backend: 78 aprovados, 36 ignorados por exigir banco dedicado. Playwright real passou; `docs/evidence/rag-manuais/cliente-catalogo.png` mostra os nomes dos quatro manuais como fontes distintas, sem banner de erro.
- Chamados já abertos continuam na fila até encerramento pelo técnico. Não são cancelados automaticamente após a correção para preservar o histórico e as mensagens do cliente.

## Checklist final

- **ATENDIDO — A tela inicial mostra somente o chat.** Identificação leve, conversa, fontes discretas e link de acesso interno; painéis técnicos ficam fora da área pública.
- **ATENDIDO — Admin/Admin e Tecnico/Tecnico abrem suas áreas; o backend rejeita acessos indevidos.** Guards melhoram a navegação, mas a autorização efetiva está em `require_role`; há testes de 401 e 403.
- **ATENDIDO — Admin gerencia usuários, máquinas e RAG e vê logs/dashboard.** Alterações RAG recalculam embeddings, reindexação é real e transacional; dashboard diferencia conversas iniciadas de clientes distintos com mensagem.
- **ATENDIDO — O handoff segue a regra exata de distribuição.** Testes cobrem livres, ocupados, pausa/offline, desempates, FIFO, concorrência e reatribuição.
- **ATENDIDO — Técnico atende vários clientes em tempo real.** Lista múltiplas atribuições, troca mensagens via WebSocket, encerra atendimentos e reconecta automaticamente.
- **ATENDIDO — A suíte passa.** Validação da Fase 14: 98 testes Python, build Vite e smoke Playwright real para cliente/admin/técnico. Os dez cenários originais também atingiram 100% de rota em três execuções reais.
- **ATENDIDO COM PRÉ-REQUISITO — `docker compose up --build` parte de banco vazio.** É necessário copiar `.env.example`, definir uma `OPENAI_API_KEY` válida e trocar os segredos de demonstração fora do ambiente local. Migrations, seed e RAG rodam automaticamente; corpus já existente não é reindexado.

## Avaliação

`evals/cases.json` contém os dez cenários do desafio, casos bilíngues de regressão, segurança e quatro casos de handoff: pedido explícito, baixa confiança, técnico livre/ocupado e fila. A regressão sem custo atravessa o grafo com provedor controlado. A avaliação com OpenAI real é deliberadamente separada e grava `data/reports/evaluation.json`.

O bootstrap final foi validado após `docker compose down -v`: Alembic chegou a `0011_phase14_memory`, o seed criou 2 usuários e 2 clientes, e o RAG indexou automaticamente 12 documentos/55 chunks. API e PostgreSQL ficaram saudáveis e o frontend subiu localmente.

## Limites conhecidos e próximos passos

- Identidade pública ainda é demonstrativa; clientes reais exigem autenticação e autorização fortes.
- Perfil, terminal e recebíveis são fictícios; integrar APIs oficiais Getnet e gestão segura de consentimento.
- O hub WebSocket e o progresso de reindexação ainda ficam em memória de uma instância; distribuir com pub/sub/fila antes de escalar horizontalmente. O rate limit de login/chat passou a PostgreSQL compartilhado em 04/10/2026.
- Adicionar alertas externos, SLOs e exportação de métricas/traces para uma plataforma observável.
- A memória de conversa é curta e não substitui uma estratégia de memória de longo prazo com consentimento e avaliação de privacidade.
- Evoluir a recuperação para busca híbrida, reranking e avaliação de groundedness/recall.
- Executar periodicamente a avaliação end-to-end tripla para preencher groundedness, recusas, handoff, p50/p95, tokens e custo com dados reais; o relatório atual mede roteamento para controlar custo.
- Revisar preços/versionamento para custo preciso e políticas de retenção/privacidade antes de produção.

## Correção do ciclo de vida do chat (29/09/2026)

- O chat autenticado mantém o `conversation_id` enquanto a tela está aberta. Ao reabrir a área de atendimento, só restaura conversas em fila ou com técnico; uma conversa apenas com IA começa em branco e recebe um novo ID na primeira mensagem. O contrato legado de `/api/chat` continua aceito.
- O encerramento por técnico fecha também a conversa. O cliente pode encerrar um chat próprio, inclusive após entrar na fila ou ser atribuído; a Central move o handoff para Encerrados e rejeita mensagens técnicas posteriores. A lista Encerrados está ordenada pela data de fechamento, com o mais recente primeiro.
- O detalhe técnico recebe o `handoff_id` e limita o histórico ao intervalo daquele atendimento, inclusive para registros antigos reutilizados indevidamente. Nenhum histórico foi apagado. Mensagem final e fechamento são atômicos.
- Evidências reais no Docker com volume existente: `docs/evidence/chat-lifecycle/`. Compilação Python e build Vite passaram; testes focados de Central, contrato e segurança: 29/29; Playwright real: 2/2. Readiness: 241 chunks, sem degradação.
- **Histórico resolvido:** nessa execução com banco de teste reutilizado, 112 passaram e 5 falharam. Após isolar/corrigir os testes e recriar `getnet_test`, a suíte completa passou com 138 testes em 04/10/2026.
- **Risco residual atual:** o hub WebSocket segue em memória de uma instância, enquanto o rate limit de login/chat já usa PostgreSQL compartilhado. O chat anônimo de demonstração mantém o comportamento legado de reaproveitar a conversa por identificador; em produção ele é desativado pela configuração.

## Atualização imediata das mensagens no painel técnico (29/09/2026)

- Causa: o backend publicava o evento `message` ao técnico, mas a Tela de Atendimento ignorava esse tipo de evento e só atualizava o histórico ao reabrir a conversa.
- A conversa selecionada agora incorpora a mensagem recebida por WebSocket, deduplicada por ID. Um polling apenas do detalhe selecionado a cada 3 segundos cobre perda de conexão; o polling das listas continua a cada 8 segundos. A conexão anterior é fechada ao trocar de atendimento ou sair da tela.
- Validação em Docker com volume existente: build Vite aprovado, teste de integração do fluxo WebSocket aprovado e Playwright real com cliente e técnico logados aprovado sem alternar a conversa. Evidência: `docs/evidence/chat-realtime/tecnico-mensagem-cliente.png`; sem banner de erro nem `[object Object]`.
- **Histórico resolvido:** a suíte completa foi repetida em banco de teste isolado e passou em 04/10/2026.
- **Riscos:** o teste visual cria contas de demonstração próprias no volume existente e elas permanecem no histórico; o hub em memória continua exigindo pub/sub distribuído antes de operar com múltiplas réplicas.

## Ajuste de rolagem e avisos do chat (29/09/2026)

- O painel técnico rola o histórico até a mensagem mais recente quando uma nova mensagem chega ou ao abrir outro atendimento.
- Mensagens do cliente durante fila/atendimento humano continuam registradas e entregues ao técnico, mas a API não gera mais um aviso de sistema para cada envio. Os avisos de entrada na fila, atribuição, transferência e encerramento continuam independentes.
- Avisos rotineiros antigos permanecem no banco para preservação do histórico, mas não são mais exibidos nos chats do cliente, na prévia e no painel técnico.
- Validação no Docker com volume existente: build Vite, integração do WebSocket e Playwright real com dez mensagens na mesma conversa aprovados. O teste confirmou rolagem até o fim e ausência do aviso repetido nas duas telas; captura em `docs/evidence/chat-realtime/tecnico-mensagem-cliente.png`.
- **Riscos de escala:** a suíte completa passou posteriormente; a política de preservar avisos antigos no banco aumenta marginalmente o volume histórico até a retenção configurada. O hub WebSocket em memória continua sem suporte a múltiplas réplicas.

## Encerrados na área central do técnico (29/09/2026)

- A aba Encerrados mantém apenas o contador no menu lateral. Busca, filtro, cartões de atendimentos e paginação de 10 itens ficam na área central, como a Fila. Os botões mostram páginas numeradas e permitem avançar/voltar.
- Cada cartão mostra cliente, máquina, categoria, nota, responsável, duração e data de encerramento. “Ver histórico” abre o chat em somente leitura e “Voltar aos encerrados” conserva a página selecionada. Meus atendimentos e Com outros técnicos não tiveram o layout alterado.
- Build Vite no Docker e Playwright real com o volume existente aprovados: 10 itens na página 1, itens restantes na página 2, histórico somente leitura, retorno à página 2, sem respostas API 4xx/5xx nem `[object Object]`. Evidências em `docs/evidence/closed-pagination/`.
- **Riscos de escala:** o endpoint de encerrados ainda carrega os registros filtrados antes de paginar em memória; para grande volume, mover `LIMIT/OFFSET` e `COUNT` ao PostgreSQL. A suíte completa passou posteriormente; o hub WebSocket em memória permanece limitado a uma instância.
