# Reteste do relatório de segurança de IA — 04/10/2026

Este documento complementa, sem substituir, o [relatório original](RELATORIO_SEGURANCA_IA_2026-10-04.md). Os testes usam dados sintéticos e provedor falso; não demonstram resistência universal a ataques inéditos.

| Achado | Correção implementada | Evidência automatizada | Estado |
|---|---|---|---|
| IA-001: código Python com “Getnet” chegava ao Router | Detecção determinística antes do Router, inclusive bloco de código, zero-width, URL encoding e Base64; resposta fixa e evento de guardrail | `backend/tests/security/test_qa_20261004.py::test_code_is_blocked_before_routing`; `backend/tests/test_integration.py::test_security_review_code_payload_never_calls_provider` | Corrigido para corpus testado |
| IA-RAG-002: reindexação promovia conteúdo pendente | Seleção apenas de documentos não pendentes, verificação adicional antes de gravar, recuperação exclui `review_required`, conteúdo suspeito é colocado em quarentena; aprovação/rejeição com motivo, ator e data | `backend/tests/test_integration.py::test_suspicious_rag_document_requires_review_and_reindex_skips_it` | Corrigido para fluxo testado |
| AUTH-003: cookie sem `Secure` após troca de senha | Função única para cookie de login, renovação e troca de senha, `Secure` obrigatório em produção | `backend/tests/security/test_qa_20261004.py::test_all_session_cookies_are_secure_in_production` | Corrigido |
| AI-004: evasão semântica/indireta | Padrões ampliados, decodificação comum, varredura de HTML bruto e texto extraído, quarentena e revisão; mantém histórico/fonte como dados não confiáveis e ferramentas com identidade definida pelo backend | `backend/tests/security/test_qa_20261004.py::test_multilingual_and_encoded_instruction_is_blocked`, `::test_indirect_html_and_encoded_poisoning_are_flagged` | Parcial; risco residual abaixo |
| OPS-005: limitador por processo | Login e chat passaram a tabelas PostgreSQL com transação e bloqueio de linha; chaves com hash; limite por IP, conta e sessão/cliente; produção recusa backend local | `backend/tests/test_integration.py::test_rate_limits_are_shared_between_process_instances` | Corrigido para réplicas com o mesmo banco; não usa Redis |
| DEMO-006: chat anônimo em produção | Só pode ser ativado com `APP_ENV=development` e `DEMO_MODE=true`; validação de produção rejeita configuração explícita anônima | `backend/tests/security/test_qa_20261004.py::test_anonymous_demo_never_enabled_in_production` | Controle de configuração implementado; segregação física é operacional |

## Procedimento recomendado ao QA

1. Atualizar imagens e migrar o banco sem remover volumes: `docker compose up --build -d`. Confirmar migração `0014_rag_review` e `/api/health/ready`.
2. Repetir T-AI-01 a T-AI-05 e T-AUTH-09 do relatório. Em T-AI-01/02, observar `route=blocked`, `agents_used=["Guardrail"]` e ausência de chamadas ao provedor. Em T-AI-04/05, confirmar `review_required=true`, `status_embedding=pending`, zero chunks recuperáveis e evento de auditoria da exclusão.
3. Em **Admin > Base de conhecimento**, abrir documento pendente, ler sinais e conteúdo, rejeitar ou aprovar com motivo. A aprovação deve gerar embeddings; a rejeição mantém o item não recuperável. Usar apenas conteúdo sintético no teste.
4. Em duas instâncias de API apontadas ao mesmo PostgreSQL, repetir T-AUTH-08 e o limite de chat. Confirmar o mesmo bloqueio `429` em ambas e `Retry-After`.
5. Repetir T-AI-06/07 e T-WEB-10 a T-SSRF-12. Esses cenários não são declarados aprovados apenas pelos testes novos; exigem regressão funcional e revisão manual.

## Evidência local e limites

Os testes focados de segurança/unitários passaram (47 casos), os quatro testes unitários da API passaram, três integrações novas com PostgreSQL passaram, dois testes Playwright do painel RAG passaram e o frontend compilou. Após `docker compose up --build -d`, a API respondeu `ready` com `degraded=false` e a migração estava em `0014_rag_review`. A suíte backend ampla inicial teve **129 aprovados e 8 falhas** no banco `getnet_test` reutilizado; parte das falhas de API e modo anônimo foi corrigida depois dessa execução. O reteste final dos cenários não legados teve **74 aprovados e 8 desmarcados**. Os oito desmarcados incluem testes que esperam distribuição automática apesar do padrão atual `HANDOFF_MODE=manual`, testes que encontram dados persistidos (409) e dois cenários antigos com estado/mocks incompatíveis. Reexecutar a regressão completa em banco limpo e revisar essas expectativas antes de afirmar CI verde; este documento não é certificado de produção.

O filtro lexical não substitui um classificador semântico independente e não cobre texto em imagens, todas as codificações ou engenharia social inédita. Redis não foi adicionado: PostgreSQL é o armazenamento compartilhado escolhido para evitar um serviço extra; monitore sua carga. Presença WebSocket/jobs continuam locais a cada instância. O modo demo não prova isolamento físico: não carregue dados reais no banco de demonstração e mantenha configurações e credenciais separadas. WAF, alertas de credential stuffing e revisão adversarial contínua são próximos passos operacionais.
