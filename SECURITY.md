# Segurança

## Relato responsável

Não abra uma issue pública contendo exploração, credenciais ou dados pessoais. Envie um relato privado ao responsável pelo repositório com versão, impacto, reprodução mínima e evidências já sanitizadas. A equipe deve acusar recebimento, classificar severidade e combinar uma janela de correção antes da divulgação.

## Configuração segura

Produção exige `APP_ENV=production`, HTTPS, segredo JWT aleatório com no mínimo 32 caracteres, credenciais iniciais e senha de banco próprias, `DEMO_MODE=false`, chat anônimo desligado e origens CORS explícitas. A aplicação falha na inicialização quando encontra padrões inseguros. O arquivo `.env.example` contém somente valores demonstrativos.

Sessões usam cookie HttpOnly, `Secure` em produção, SameSite Lax, JWT curto renovado em `/api/auth/me`, versão de token conferida no banco e revogação no logout, troca/reset e desativação. Escritas autenticadas verificam a origem no ambiente produtivo.

## Operação

- Login e chat usam tabelas PostgreSQL com bloqueio de linha transacional e chaves com hash. Os limites são compartilhados entre réplicas que usam o mesmo banco. A implementação em memória permanece apenas para testes/desenvolvimento, e `APP_ENV=production` exige `RATE_LIMIT_BACKEND=database`. Monitore lockouts, 429 e carga do banco; use também limites no proxy/WAF.
- Documentos RAG suspeitos ficam em quarentena (`review_required`, sem chunks recuperáveis). O administrador deve aprovar ou rejeitar com motivo; ator, data e decisão são registrados. A reindexação não promove itens pendentes.
- O PostgreSQL não é publicado no Compose principal. O override local o expõe apenas em `127.0.0.1:5433` para desenvolvimento.
- Execute `pip-audit`, `npm audit --audit-level=high`, Bandit, Gitleaks com histórico completo e Trivy antes de promover imagens.
- `audit_logs` é append-only por trigger. Backup, restauração, rotação de chaves e resposta a incidentes continuam responsabilidades operacionais.

## Privacidade

Mensagens têm retenção configurável por `RETENTION_DAYS` e `RETENTION_ACTION`. Administradores podem exportar ou anonimizar um cliente; anonimização revoga sessões, remove dados de recebíveis, desvincula terminais e substitui conteúdo de mensagens.
