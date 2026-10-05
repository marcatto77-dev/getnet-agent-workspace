# Revisão da política e preparação da apresentação — 05/10/2026

## Entrega

- Getnet e cotação de câmbio são permitidos; clima e assuntos aleatórios são recusados sem handoff. O enunciado original permanece intacto e não exige documentação em inglês.
- Knowledge consulta RAG e busca oficial quando faltam evidências, sem pedir permissão ao cliente. Support consulta ferramentas autorizadas do próprio cliente; `knowledge_support` combina os dois.
- Pedido explícito abre handoff. Após três respostas de assistência e insatisfação, a IA oferece um técnico e aguarda aceite. Falta de fonte, sozinha, não abre chamado; recusa da oferta mantém a IA.
- Admin → Agentes e segurança permite demonstrar os quatro prompts e guardrails em modo somente leitura. Canário oculto, autenticação e RBAC preservados.
- README contém diagramas Mermaid, tabela de atividades, rotas HTTP e dos agentes, segurança, orquestração LangGraph e instalação/testes por clone.
- Respostas usam o idioma classificado pelo Router; composição recebe instrução explícita para não copiar o idioma das evidências.

## Validações

| Verificação | Resultado |
|---|---|
| Backend com PostgreSQL de teste | 163 testes aprovados; banco demo preservado. |
| Regressão focada após ajuste de idioma | 54 testes aprovados. |
| Playwright controlado | 15 aprovados; 15 testes reais ignorados por padrão. |
| Smoke real de telas | Cliente, Admin e técnico aprovados. |
| Smoke real da política/painel | Prompts, guardrails, RBAC e recusa de clima aprovados; screenshots em `docs/evidence/agent-policy/`. |
| Modelo real: dez cenários | 10/10 rotas de acordo com a política vigente. |
| Modelo real: insatisfação/aceite/recusa | 3/3 classificações esperadas. O fluxo persistido também tem teste de integração. |
| Modelo real: idiomas | Link de Pagamento respondido em inglês e espanhol com fontes RAG. |
| Modelo real: câmbio | Rota permitida; sem confirmação de fonte atual, respondeu honestamente sem cotação inventada e sem handoff. Não demonstra obtenção bem-sucedida de cotação nesta execução. |
| Ruff | Sem achados em `backend/app`, `backend/tests` e `backend/scripts`. |
| Bandit, critério do CI (`-lll`) | Sem achados de severidade alta. A execução sem esse filtro aponta alertas médios, incluindo construção de SQL com campos controlados e valores parametrizados; não se afirma ausência de todo alerta estático. |
| Docker | API/web reconstruídas; build TypeScript/Vite aprovado. |
| Snapshot de publicação | 212 arquivos; Gitleaks sem segredos detectados, `.env` fora do índice e diff sem erros de whitespace. |

As auditorias de dependências, imagem, bootstrap RAG vazio e snapshot anterior de segredos estão registradas no README como evidências de 04/10/2026. Não são prova de segurança absoluta nem avaliação factual de todas as respostas. `evals/report.md` é histórico da política anterior; o roteiro atual é `backend/scripts/verify_policy_live.py`.

Reutilizar o banco de teste após uma rodada completa produziu duas falhas por dados residuais (cadastro duplicado e vínculo de máquina). O procedimento do README recria exclusivamente `getnet_test` antes da suíte; não execute testes de integração no banco demo nem interprete a rodada com banco reutilizado como evidência de aprovação.

## Publicação

Não publicar `.env`, banco/volumes, caches nem credenciais pessoais. Credenciais seed são de demonstração. Esta cópia não possui commit nem remoto; a publicação exige URL do repositório e identidade Git do autor. Os passos reproduzíveis para o avaliador ficam no README; não é necessário vídeo.
