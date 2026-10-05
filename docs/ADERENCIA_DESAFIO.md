# Aderência ao Desafio.md

Referência: [enunciado original](../knowledge/Desafio.md). Matriz atualizada em 04/10/2026 após os [retestes de segurança](RETESTE_SEGURANCA_IA_2026-10-04.md) e [funcionais](RETESTE_FUNCIONAL_2026-10-04.md), com migration `0014_rag_review`. O [README](../README.md) contém o procedimento reproduzível de instalação e testes. “Implementado” indica que há código e evidência verificável; limites de avaliação factual e de uso em produção são descritos separadamente.

## Requisitos centrais

| Exigência do desafio | Estado | Evidência e ressalva |
|---|---|---|
| Pelo menos três agentes distintos que cooperam | Implementado | Quatro papéis em `backend/app/agents.py` e prompts separados em `backend/app/prompts.py`. O LangGraph transporta estado tipado entre Router, Knowledge, Support e Escalation. |
| Router como entrada, roteamento e sequência | Implementado | `backend/app/agents.py`: nó router, seleção de rota, composição Knowledge + Support e saída estruturada em `backend/app/schemas.py`. |
| Knowledge com RAG sobre Getnet | Implementado | `backend/app/ingest.py`, `backend/app/rag.py`, `data/sources.json` e PostgreSQL/pgvector. Inclui páginas oficiais e os quatro manuais PDF. A atualidade do conteúdo e a precisão da extração requerem revisão. |
| Busca web para perguntas gerais | Implementado com restrição deliberada | Busca Getnet e cotação de câmbio (Banco Central/BCE). Clima foi excluído por decisão de produto, embora conste dos exemplos do enunciado. Configurações legadas não reabrem clima. Veja `POLITICA_ATENDIMENTO.md`. |
| Busca web no site Getnet | Implementado | Knowledge tenta RAG primeiro e busca oficial quando falta evidência. Domínios permitidos em `.env.example`; citações são validadas mesmo quando o modelo não aceita filtro na ferramenta. Depende de chave/saldo e disponibilidade externa. |
| Support com pelo menos duas ferramentas | Implementado | Há quatro ferramentas de leitura em `backend/app/tools.py`: perfil, recebíveis, lista de máquinas e status de máquina. Identidade vem do backend em sessão autenticada. |
| Endpoint HTTP POST com `message` e `user_id` | Implementado | `POST /api/chat` retorna JSON com resposta, rota, agentes, fontes e conversa. Compatibilidade por `CHAT_ALLOW_ANONYMOUS_DEMO=true` só em demo; o portal usa sessão. |
| Dockerfile e Compose | Implementado e verificado | `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` e `.env.example`; imagens API/web foram reconstruídas e a suíte integral executou em Linux/Docker com banco `getnet_test` vazio. O RAG é ingerido no primeiro início com chave OpenAI. |
| Estratégia de testes e integração explicada | Implementado e validado | Testes em `backend/tests` e `frontend/tests`; execução e isolamento do banco no README. Última suíte integral: 163 backend e 15 Playwright controlados; smokes reais de telas e da nova área de agentes aprovados. |
| Escolha adequada de linguagem/framework | Implementado | Python/FastAPI, LangGraph, PostgreSQL/pgvector, React/TypeScript, Docker. |
| README abrangente | Implementado | [README](../README.md) cobre instalação por clone, configuração, uso, API, arquitetura, fluxo, RAG, ferramentas, testes e limites. |

O exemplo sugerido `https://www.getnet.net/en` não é a única fonte: o manifesto usa também páginas brasileiras e manuais oficiais. A busca de similaridade sozinha não garante que a resposta seja correta; a documentação não deve vendê-la como prova de qualidade factual.

## Bônus e diferenças em relação ao mínimo

| Tema | Estado | O que foi além |
|---|---|---|
| Quarto agente | Implementado | Escalation cria resumo estruturado e aciona atendimento humano. |
| Guardrails | Implementado, eficácia não absoluta | Entrada, classificação, ferramentas, RAG/web e saída em `backend/app/guardrails/`; eventos auditáveis. Red-team existe, mas ataques novos ainda exigem validação. |
| Handoff humano | Implementado | Pedido explícito ou aceite após oferta. Após três respostas e insatisfação, a IA oferece um técnico; não abre chamado por falta de fontes. Central com fila, disponibilidade, assumir/puxar/encaminhar/encerrar e notas internas. |
| Observabilidade | Implementado parcialmente como medição de qualidade | Dashboard, logs, rastros, auditoria e métricas; há dataset em `evals/cases.json`. `evals/report.md` mede principalmente roteamento em três execuções; não prova groundedness ou satisfação. |
| Produto além da API | Implementado | Portal do cliente, cadastro/administração de clientes e máquinas, autenticação por perfil, conversa isolada por atendimento e interface técnica. Esses itens não substituem os requisitos centrais. |
| Segurança/produção | Parcial para operação real | Há RBAC, guardrails, quarentena/revisão de RAG, proteção SSRF/XSS/CSRF e configuração fail-closed. Login/chat têm limite compartilhado em PostgreSQL. O ambiente de demo ainda usa senhas seed e dados fictícios; não deve ser tratado como produção pronta. |

## Dez cenários do enunciado

Os dez exemplos do [enunciado](../knowledge/Desafio.md) aparecem no dataset de avaliação. Nove pertencem ao escopo atual; clima recebe `blocked`, conforme decisão de produto. Câmbio permanece permitido com fonte financeira oficial. A [tabela de interpretação](POLITICA_ATENDIMENTO.md) explica a rota de cada pergunta. O relatório de avaliação deve ser lido com sua data e versão de política; acerto de rota não equivale a correção factual das respostas.

## Validação consolidada (05/10/2026)

| Verificação | Resultado |
|---|---|
| Imagens Docker | API e web reconstruídas do código desta entrega. |
| Backend em Linux/Docker, `getnet_test` recriado | **163 aprovados**; migrations até `head`, seed e integração no banco de teste. Banco demo preservado. Após o ajuste final de idioma, 54 testes focados passaram. |
| Bootstrap RAG em banco Docker isolado e vazio | 16 fontes oficiais indexadas, 240 chunks, `degraded=false`; falso positivo do manual Get Mini corrigido com regressão de segurança. O volume temporário foi removido após o teste. |
| Ruff e Bandit | Ruff sem achados. Bandit sem achados de severidade alta pelo critério do CI (`-lll`); alertas médios não são excluídos dessa afirmação. Há um aviso de depreciação de dependência nos testes. |
| Auditoria de dependências e imagem | `pip-audit` sem vulnerabilidades conhecidas após PyJWT 2.15.0; `npm audit --audit-level=high` sem achados; Trivy sem vulnerabilidades corrigíveis altas/críticas na imagem da API. |
| Arquivos candidatos ao Git | 212 arquivos preparados. `.env`, caches e build ignorados; Gitleaks sem segredos no snapshot atual de publicação. Sem commit nem remoto configurados. |
| Frontend | Build TypeScript/Vite aprovado. Playwright: **15 controlados aprovados**, 15 reais ignorados por padrão. |
| Smoke real | Telas de cliente/Admin/técnico e nova área de agentes aprovadas; RAG/manuais passaram na preparação anterior. |
| Avaliação de agentes | Política atual: dez rotas e três classificações de consentimento aprovadas com modelo real; respostas RAG em inglês/espanhol aprovadas. Câmbio sem fonte atual tratado sem invenção. Relatório histórico: três execuções com 100% de acerto de rota da política anterior. Nenhum desses resultados comprova correção factual. |

Os comandos exatos estão no [README](../README.md). Os smokes reais usam a chave configurada e não substituem a revisão humana de respostas e fontes. Os relatórios originais de QA permanecem em `docs/` como histórico das correções.

## Como demonstrar

Abra `/` com `cliente1988`, faça uma pergunta coberta pelo manual Get Smart e mostre as citações. Depois use uma pergunta sobre recebíveis para mostrar uma ferramenta com dados fictícios do cliente. Peça atendimento humano, entre em `/tecnico/atendimento` com `Tecnico` e mostre a fila, o histórico e a separação de notas internas. Finalmente, em `/admin`, apresente a Base de conhecimento, a revisão de conteúdo suspeito, os logs e o dashboard. O [guia técnico](GUIA_TECNICO_APRESENTACAO.md) traz o fluxo e os arquivos para explicar os prompts, o RAG e a orquestração.

Os prompts e guardrails são controles de projeto, mas nenhum teste finito prova segurança absoluta. O RAG depende da chave OpenAI e da disponibilidade das fontes oficiais na primeira ingestão. O portal, as credenciais seed e os dados financeiros são de demonstração; a arquitetura de tempo real em uma única instância não é um desenho de produção com múltiplas réplicas.
