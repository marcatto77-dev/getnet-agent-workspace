# Guia técnico e roteiro de apresentação

Use este arquivo para explicar **o que foi construído, onde está no código e como demonstrar**. O [README](../README.md) é o passo a passo de instalação; a [matriz de aderência](ADERENCIA_DESAFIO.md) registra o que está comprovado e o que falta. O projeto é uma demonstração com dados fictícios, não um produto oficial da Getnet.

## Mensagem de abertura (30 segundos)

> “O desafio pedia três agentes, RAG, busca web, duas ferramentas de suporte, API e Docker. Entregamos quatro agentes orquestrados em LangGraph, RAG com pgvector, busca Getnet controlada por domínio, quatro ferramentas de leitura, API FastAPI e Compose. Expandimos para portal, atendimento humano, administração e guardrails. Vou mostrar o fluxo, as fontes e um pedido que passa para técnico. Também vou separar o que foi medido do que ainda precisa de validação.”

## Mapa de arquitetura

```text
React (cliente / técnico / admin)
             │ HTTP + WebSocket, sessão por perfil
             ▼
FastAPI ── guardrails ── LangGraph
             │              ├── Router → decisão tipada
             │              ├── Knowledge → RAG e web oficial
             │              ├── Support → ferramentas de leitura
             │              └── Escalation → resumo + handoff
             │
             ├── PostgreSQL/pgvector: clientes, máquinas, conversas, RAG
             ├── Central: fila, atribuição, eventos, mensagens
             └── logs, guardrail_events, métricas, auditoria
```

A comunicação entre agentes é **estado tipado dentro de um grafo em processo**, não troca livre de mensagens nem fila externa. O grafo pode executar Knowledge e Support em sequência e compor uma resposta. O LLM classifica/gera; o código impõe identidade, autorização, limites, ferramentas permitidas, transições e validação final.

### Arquivos para abrir na apresentação

| Explique | Abra |
|---|---|
| Requisito e dez perguntas | `knowledge/Desafio.md` |
| Entrada HTTP, auth e WebSocket | `backend/app/main.py` e rotas em `backend/app/` |
| Grafo, nós, decisão e passagem de estado | `backend/app/agents.py` |
| Contratos tipados das saídas | `backend/app/schemas.py` |
| Prompts dos quatro agentes | `backend/app/prompts.py` |
| Separação instruções/entrada, retry e web search | `backend/app/provider.py` |
| Ferramentas de cliente e SQL parametrizado | `backend/app/tools.py` |
| Manifesto de fontes | `data/sources.json` |
| Ingestão, extração, chunks e embeddings | `backend/app/ingest.py` |
| Recuperação vetorial/limiar | `backend/app/rag.py` |
| Distribuição automática alternativa | `backend/app/handoff/assignment.py` |
| Suite e dataset | `backend/tests/`, `frontend/tests/`, `evals/cases.json` |
| Ambiente e deploy | `.env.example`, `docker-compose.yml`, Dockerfiles |

## Como explicar os prompts sem expor segredos

Abra `backend/app/prompts.py` na tela e mostre as quatro constantes `ROUTER`, `KNOWLEDGE`, `SUPPORT` e `ESCALATION`. Explique o **contrato**, não leia o texto inteiro:

1. **Router**: delimita o escopo Getnet, interpreta intenção, escolhe rota e `safety_label`. A saída é validada por schema; classificação inválida cai em resposta segura.
2. **Knowledge**: responde somente com evidências recuperadas e citações, ou sinaliza insuficiência. Não inventa preços/taxas/prazos. O código verifica se os IDs citados foram de fato recuperados.
3. **Support**: interpreta os resultados de ferramentas de leitura do próprio cliente; não escolhe arbitrariamente a identidade nem executa operação financeira.
4. **Escalation**: resume o problema e contexto para o técnico; a criação/atribuição do chamado acontece em serviço transacional.

Em `backend/app/provider.py`, mostre que o prompt passa como `instructions`, separado do `input` do usuário. Histórico, trechos RAG e resultados web entram delimitados como **dados não confiáveis**, não como novas instruções. Há um canário interno para detectar reprodução indevida de instruções; não mostre o valor do canário nem `.env` na gravação. Demonstre uma tentativa simples de “ignore as instruções” e a recusa, sem usar dados reais de pessoas.

A regra de escopo é intencional: Getnet a partir de RAG/web oficial e dados do próprio cliente, com câmbio como exceção financeira em fontes Banco Central/BCE. Clima é recusado, inclusive em configurações legadas `challenge`. Dos dez exemplos do enunciado, nove permanecem no escopo e previsão do tempo foi restringida por decisão de produto. Veja a [política e tabela dos cenários](POLITICA_ATENDIMENTO.md).

Na apresentação, abra **Admin → Agentes e segurança**. Os prompts exibidos são os carregados pela API; os guardrails mostram o código das camadas de entrada, fontes, ferramentas, saída e inspeção de RAG. A tela é somente leitura e esconde o canário. Para alterar prompts, edite `backend/app/prompts.py`, rode as regressões e reconstrua a API. O README traz diagramas da arquitetura, do LangGraph e do RAG.

O técnico é acionado por pedido explícito ou aceite. Após três respostas de assistência e nova insatisfação, o Router oferece atendimento humano; o cliente pode aceitar ou continuar com a IA. Uma dúvida sem evidência tenta RAG/site oficial e pede contexto, sem abrir chamado. Use um exemplo em inglês ou espanhol para demonstrar que o idioma da pergunta é preservado sem mudar as permissões.

## RAG, de ponta a ponta

1. **Fontes**: `data/sources.json` lista URLs oficiais, inclusive quatro manuais PDF (Get Smart, Get Clássica, Get Mini e Get Lite). Há metadados de título/idioma/país; o manifesto delimita o corpus.
2. **Ingestão**: `backend/app/ingest.py` valida esquema/domínio/IP/redirecionamentos e limite de tamanho; extrai texto de HTML/PDF, remove elementos perigosos, sinaliza possível instrução maliciosa e cria chunks. Fontes inalteradas não precisam de embedding novo.
3. **Armazenamento**: documentos, metadados, chunks e vetores estão em PostgreSQL com pgvector. O Admin vê título, origem, prévia e status em **Base de conhecimento**.
4. **Recuperação**: `backend/app/rag.py` embeda a pergunta e consulta os trechos mais próximos por distância cosseno; o padrão recupera cinco, sujeito a um limiar. Isso é similaridade, **não** confiança probabilística.
5. **Geração**: o Knowledge recebe os trechos e gera resposta estruturada com IDs de evidência; a aplicação valida citações. Se o RAG não sustenta a resposta, tenta busca limitada ao site Getnet antes de oferecer técnico.
6. **Limites**: documento presente no banco não garante que o trecho correto foi recuperado, nem que o LLM interpretou uma tabela corretamente. Mostre a fonte clicável e formule uma pergunta cujo manual tenha evidência legível. A busca web depende de serviço externo e não pede autorização ao cliente durante o atendimento.

Para mostrar os vetores, não é necessário exibir chaves nem dados sensíveis. Mostre a tela Admin e `/api/health/ready` com `rag_chunks > 0`. O snapshot atual desta revisão tinha 241 chunks; não prometa esse número em um volume novo. Se a ingestão estiver degradada, explique o modo fail-safe e use **Reindexar** depois de corrigir a chave/fonte.

## Support e identidade

`backend/app/tools.py` implementa quatro ferramentas: `get_customer_profile`, `get_receivables`, `get_terminal_status` e `list_customer_terminals`. Demonstre “Quando recebo o dinheiro das vendas de ontem?” com `cliente1988`: a resposta deve usar recebíveis fictícios, não um valor inventado. Demonstre “Minha máquina não conecta” e o terminal vinculado. Na sessão, o backend injeta o cliente autenticado e impede consultar outro cadastro ou serial alheio. A ferramenta é somente leitura e as consultas SQL são parametrizadas.

O contrato `{message,user_id}` do enunciado permanece para curl **somente no modo demo anônimo**; explique que ele não serve de autenticação real. No portal, um usuário novo com perfil Cliente pode conversar independentemente do formato do login.

## Handoff e Central

O fluxo padrão usa `HANDOFF_MODE=manual`:

```text
Cliente pede técnico / IA não sustenta resposta
→ Escalation resume e cria atendimento
→ cliente vê mensagem de fila
→ técnicos online veem item na Central
→ um assume; todos veem nova contagem
→ técnico responde publicamente ou registra nota interna
→ transferência / pull / devolução à fila, se necessário
→ encerramento gera evento e fecha aquele histórico
→ próxima conversa do cliente começa separada
```

O cliente nunca acessa a Central; o Admin a vê em leitura. Notas internas não aparecem no portal. Toda escrita relevante gera eventos de handoff/auditoria. O modo `auto` mantém o algoritmo por técnicos online, carga e tempo desde a última atribuição; mostre `backend/app/handoff/assignment.py` em vez de alterar o modo ao vivo. Não diga que o chat encerrado “volta à IA”: **o chamado fecha; a próxima visita cria nova conversa**.

## Segurança e operação em linguagem de entrevista

- Entrada: tamanho, normalização Unicode, mascaramento de PII, padrões de injeção e abuso; falha fechada.
- Router: saída tipada; rótulos de segurança e rota segura para saída inválida.
- Fontes: RAG/web/histórico não confiáveis; allowlist de domínios e verificação de URLs.
- Ferramentas: allowlist por agente, somente leitura, limite de chamadas/timeout, identidade injetada pelo servidor.
- Saída: validação de citações, PII/IDs, canário e alegações não executadas.
- App: cookie HttpOnly, RBAC, CSRF/CORS, proteção WebSocket/SSRF/XSS, headers, auditoria.
- Resiliência: timeout/retry/backoff/circuit breaker, modo RAG degradado e `/api/health/live` versus `ready`.
- Observabilidade: Admin > Logs/Guardrails, Dashboard, `/api/metrics` restrito e `docs/ALERTS.md`.

Não prometa segurança absoluta. `SECURITY.md` e `docs/THREAT_MODEL.md` registram ameaças e riscos. O rate limit de login/chat é compartilhado via PostgreSQL; presença em tempo real e jobs ainda não têm pub/sub entre réplicas. Dados fictícios e credenciais seed limitam o ambiente de demonstração.

## Roteiro de demonstração (8–12 minutos)

**Antes de apresentar:** inicie Compose e confirme `/api/health/ready`; verifique chave e créditos; abra três perfis isolados de navegador (cliente, Tecnico, Admin). Em volume novo, use `cliente1988/123`, `Tecnico/Tecnico` e `Admin/Admin`. Em volume já usado, confirme as senhas vigentes sem redefini-las às cegas. Para mostrar transferência, crie/prepare um segundo técnico e deixe ambos online. Não mostre `.env`, cookies ou token.

1. **Contexto (1 min):** abra `knowledge/Desafio.md`, explique os três agentes exigidos e o quarto adicionado. Mostre o diagrama deste guia.
2. **Prompt e fluxo (1–2 min):** abra `backend/app/prompts.py`, depois `backend/app/agents.py`; aponte instruções separadas, rota estruturada e sequência de nós.
3. **RAG (2 min):** em Admin > Base de conhecimento, mostre os quatro manuais e um documento oficial. No cliente, pergunte a diferença entre Get Clássica e Get Smart. Abra a fonte citada e explique recuperação/citação; não force afirmação além da fonte.
4. **Support (1 min):** pergunte sobre recebíveis ou status da máquina. Mostre em código as quatro ferramentas e como o `customer_id` vem da sessão.
5. **Handoff (2–3 min):** cliente pede “Quero falar com um técnico sobre minha máquina”. Na Central, mostre fila, resumo amigável e **Ver chat** antes de **Assumir**. Assuma, envie resposta pública e nota interna; no cliente, comprove que a nota não aparece. Se houver segundo técnico, encaminhe ou puxe; finalize e mostre o item em Encerrados e o novo chat limpo do cliente.
6. **Guardrail e operação (1 min):** faça uma pergunta fora de escopo ou tentativa de instrução “ignore suas regras”; mostre recusa e evento em Admin > Logs > Guardrails. Abra Dashboard e `/api/health/ready`.
7. **Fechamento (1 min):** mostre a matriz de aderência, os 138 testes backend e os smokes reais aprovados. Explique que o relatório de avaliação mede acerto de rota; correção factual exige comparar respostas com as fontes. O workflow do GitHub executará seus próprios gates após a publicação.

**Plano B:** se OpenAI estiver indisponível, mostre ingestão, documentos, código, resultados históricos claramente identificados como históricos e o modo degradado; não simule uma resposta ao vivo. Se a busca web não devolver fonte válida, explique o fallback para técnico. Se algum login de volume antigo não funcionar, use um volume de demonstração preparado previamente — não apague o volume existente durante a apresentação.

## Perguntas que o avaliador pode fazer

- **Por que quatro agentes?** O quarto isola resumo/handoff humano da geração de resposta; facilita teste e auditoria.
- **Por que LangGraph?** Fluxo condicional explícito e estado tipado; mais claro que um agente com ferramentas irrestritas.
- **O que impede vazamento entre clientes?** Identidade autenticada no backend, filtros de posse, RBAC e IDOR tests; o LLM não escolhe `customer_id`.
- **Quando faz web search?** Após RAG insuficiente para Getnet ou em consultas de cotação de câmbio. Clima é recusado sem encaminhamento.
- **Como sabe que a resposta é correta?** Validação de IDs evita citações inventadas, mas presença de fonte não prova precisão semântica; responda com um exemplo real e compare a afirmação ao trecho recuperado.
- **Como escala?** Login/chat já usam limite compartilhado em PostgreSQL; o hub WebSocket e a presença ainda exigiriam pub/sub distribuído para múltiplas réplicas.
- **Qual o maior risco residual?** Qualidade e atualidade das fontes e interpretação do modelo, especialmente tabelas de manuais e informação que muda.
