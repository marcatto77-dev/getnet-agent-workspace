# Modelo de ameaças — Getnet Agent Workspace

## Escopo e ativos

Ativos protegidos: credenciais e sessões, dados cadastrais/recebíveis, conversas, inventário de terminais, corpus RAG, telemetria/auditoria, orçamento de IA e disponibilidade. As fronteiras principais são navegador–nginx, nginx–API, API–PostgreSQL, API–OpenAI e ingestão–internet.

## Atores

Cliente autenticado ou anônimo de demonstração, técnico, administrador, atacante externo, usuário interno malicioso, página externa hostil e conteúdo RAG comprometido.

## STRIDE resumido

| Categoria | Ameaças principais | Mitigações implementadas |
|---|---|---|
| Spoofing | roubo/reuso de cookie, enumeração de login, WebSocket sem identidade | HttpOnly/Secure/SameSite, JWT curto e versionado, logout revogável, resposta genérica e limitação progressiva, autenticação no handshake |
| Tampering | mass assignment, SQL injection, alteração de auditoria/RAG poisoning | Pydantic `extra=forbid`, parâmetros SQL e allowlists, trigger append-only, detecção e revisão de conteúdo suspeito |
| Repudiation | negação de alterações administrativas | `audit_logs` imutável e eventos de guardrail com `request_id` |
| Information disclosure | IDOR, XSS, SSRF, PII em erro/log, dados entre clientes | RBAC e filtro de dono no backend, React como texto, CSP, DNS/IP/redirect allowlist na ingestão, mensagens de erro padronizadas e mascaramento |
| Denial of service | frames/bodies enormes, spam, denial-of-wallet | limites de corpo/frame/mensagem, timeout ocioso, rate limits por IP/sessão, orçamento diário por cliente e limites de recursos Docker |
| Resiliência | indisponibilidade OpenAI ou corpus vazio | timeout, retry, circuit breaker, modo degradado de RAG e restauração por snapshot |
| Elevation of privilege | cliente acessando técnico/admin, função nova sem proteção | dependências de perfil, matriz de autorização e `x-required-role` obrigatório em toda operação OpenAPI |

## Riscos residuais

O rate limit de login/chat usa PostgreSQL compartilhado; presença WebSocket, notificações entre réplicas e estado de jobs ainda são locais e exigem pub/sub ou fila para escala horizontal. SameSite e verificação de Origin pressupõem HTTPS e proxy confiável corretamente configurados. Guardrails determinísticos, classificação do Router e quarentena/revisão de RAG reduzem risco, mas não eliminam jailbreak semântico, conteúdo em imagem ou erro de revisão humana. A ingestão depende da resolução DNS observada e deve usar egress proxy/DNS pinning em ambientes de alta criticidade. O chat anônimo só é habilitável em desenvolvimento com `DEMO_MODE=true`; ainda é necessário manter esse ambiente e banco fisicamente separados de dados reais. Scanners de supply chain dependem da disponibilidade e das bases de vulnerabilidade do CI.
