# Plano do projeto — Getnet Multi-Agent Support

Status: planejamento inicial histórico. A entrega atual usa repositório GitHub e apresentação ao vivo, conforme o [README](../README.md).
Base: `knowledge/Desafio.md`. Elaborado em 20/09/2026.

## 1. Objetivo e limites

Entregar um sistema demonstrável de atendimento com agentes cooperando, respostas fundamentadas, consulta a dados fictícios de clientes, interface web, API, execução Docker, testes e documentação. O repositório e a apresentação ao vivo devem permitir ao avaliador entender, executar e verificar a solução.

Não temos acesso a sistemas internos da Getnet. Os dados de clientes, recebíveis, terminais e chamados serão sintéticos e identificados como demonstração. As informações públicas sobre produtos serão obtidas de fontes oficiais reais. O sistema não fará pagamentos ou alterações financeiras.

## 2. Matriz de requisitos e evidências

| Requisito | Implementação planejada | Evidência de conclusão |
|---|---|---|
| Router Agent | Classificação estruturada de intenção e seleção de sequência de agentes | Testes de roteamento e trace da execução |
| Knowledge Agent | Recuperação na base Getnet e ferramenta de busca web | Respostas com fontes verificáveis e ingestão reproduzível |
| Customer Support Agent | Consulta a clientes e operações sintéticas por ferramentas | Testes de dados corretos e isolamento entre clientes |
| Pelo menos duas ferramentas de suporte | Consultar recebíveis e consultar terminal; perfil como terceira ferramenta | Contratos, chamadas reais ao banco e testes |
| Comunicação entre agentes | Estado tipado compartilhado em grafo e resultados estruturados | Cenário em que suporte e conhecimento cooperam |
| API POST | `POST /api/chat` aceita `message` e `user_id` | Teste HTTP e exemplo no README |
| Docker | Imagens e Compose para interface, API e banco | Build e execução a partir de ambiente limpo |
| Estratégia de testes | Testes unitários, integração, ponta a ponta e avaliações de IA | Comandos reproduzíveis e relatório |
| README completo | Instalação, decisões, arquitetura, RAG, ferramentas e limitações | Execução seguindo apenas o README |
| GitHub e apresentação | Repositório sem segredos, roteiro e demonstração ao vivo | URL do repositório e apresentação técnica |
| Interface web solicitada | Chat com fontes, estados de carregamento e erros | Demonstração pelo navegador |
| Bônus | Escalonamento, guardrails e observabilidade | Chamado persistido, testes adversariais e traces |

## 3. Arquitetura proposta

### Stack

- Backend: Python, FastAPI e Pydantic para API e contratos validados.
- Orquestração: LangGraph, com nós separados, estado explícito, limites de execução e transições testáveis.
- Banco: PostgreSQL com pgvector. Dados transacionais e documentos ficam em tabelas separadas no mesmo serviço; pgvector permite busca vetorial dentro do PostgreSQL.
- Frontend: React, TypeScript e Vite, servido por Nginx no contêiner final. Proxy para a API simplifica a origem das requisições.
- Modelos: adaptadores para geração e embeddings; provedor e modelos serão definidos antes da integração, conforme acesso, qualidade e orçamento.
- Busca web: adaptador de provedor com resultados contendo URL, título, trecho e horário de consulta. Seleção do serviço depende de chave e orçamento.
- Testes: pytest no backend e Playwright para os fluxos principais no navegador.
- Operação: Docker Compose, migrações do banco, logs JSON e identificação de cada execução.

Não precisamos de vários bancos ou microsserviços para demonstrar agentes distintos. Cada agente terá responsabilidade, instruções, ferramentas e contrato próprios dentro da mesma aplicação. Isso facilita execução e diagnóstico.

### Fluxo

1. Interface envia mensagem e identificador de cliente de demonstração.
2. API valida payload, limites e contexto de acesso.
3. Router identifica intenção: conhecimento Getnet, consulta geral atual, suporte, combinação, esclarecimento ou escalonamento.
4. Orquestrador executa o agente ou sequência permitida.
5. Knowledge recupera evidências; Support consulta dados; resultados estruturados retornam ao estado compartilhado.
6. A resposta é construída a partir das evidências, com fontes e eventuais limitações.
7. Verificações de saída impedem exposição de dados de outros clientes e referências inexistentes.
8. API devolve JSON e registra métricas sem segredos ou dados pessoais desnecessários.

O estado incluirá request_id, user_id validado, mensagem, intenção, plano de execução, resultados de ferramentas, evidências, resposta e erros. O frontend poderá mostrar um resumo operacional de agentes e ferramentas, sem expor raciocínio interno do modelo.

### Agentes

**Router:** interpreta a mensagem com saída estruturada e escolhe rotas permitidas. Solicita esclarecimento quando faltar informação. Não poderá criar loops ilimitados ou nomes arbitrários de ferramentas.

**Knowledge:** usa RAG para produtos Getnet e busca web para consultas gerais, como clima ou câmbio. Conteúdo público não substitui dados específicos do contrato do cliente. Sem evidência suficiente, informa a limitação. Para perguntas atuais, registra data, localidade e fonte; não usa conhecimento estático para inventar valores.

**Support:** consulta dados do cliente através de ferramentas com argumentos validados. Ferramentas iniciais: `get_customer_profile`, `get_receivables` e `get_terminal_status`. O backend vincula o cliente ao contexto; o modelo não escolhe livremente a identidade consultada. Pode solicitar ao Knowledge instruções oficiais para o terminal identificado.

**Escalation (bônus planejado):** prepara resumo objetivo e categoria do problema e cria chamado local mediante fluxo explícito de confirmação. Retorna protocolo persistido. A interface informa que é uma fila de demonstração; integração com atendimento humano real fica fora do escopo inicial.

Exemplo de cooperação: “Minha máquina não conecta e preciso saber quando recebo minhas vendas”. Router organiza duas necessidades; Support consulta terminal e recebíveis; Knowledge recupera instruções compatíveis; o resultado reúne orientação documentada e previsão registrada no banco.

## 4. Dados e RAG

### Fontes e aquisição

Ingerir a URL global indicada no desafio e páginas oficiais brasileiras relevantes. A página global consultada aponta para `https://site.getnet.com.br/` como destino Brasil. Inventariar páginas de maquininhas, Pix, antecipação, crediário, link de pagamento e suporte. Verificar durante a ingestão se os produtos dos exemplos continuam documentados; não preencher lacunas com informações inventadas.

Pipeline:

1. Manifesto de URLs autorizadas, tema, país e idioma.
2. Coleta com timeout, limite de páginas, controle de redirecionamento e respeito às condições de acesso.
3. Extração do texto útil, remoção de menus repetidos e detecção de páginas vazias.
4. Armazenamento de snapshot, URL original/canônica, título, data de coleta e hash.
5. Divisão por seções, preservando títulos; tamanho e sobreposição calibrados por testes.
6. Geração de embeddings e armazenamento dos trechos com metadados.
7. Recuperação por similaridade e filtros de país/idioma; testar busca textual complementar se nomes exatos de produtos falharem.
8. Geração fundamentada e citações ligadas aos trechos realmente recuperados.

A ingestão será um comando separado, idempotente, com relatório de páginas, trechos, falhas e cobertura. Não acontecerá a cada pergunta. Atualizações identificarão documentos alterados, removidos ou vencidos. Uma indisponibilidade não apagará silenciosamente a última versão válida.

Não existe um limiar universal que transforme similaridade vetorial em certeza. Critérios de suficiência serão calibrados com perguntas de avaliação. Evidências contraditórias ou desatualizadas exigem indicação de limitação ou esclarecimento.

### Banco transacional

Tabelas previstas: customers, terminals, receivables, tickets; documents e document_chunks para RAG; conversations/messages apenas se incluirmos histórico persistente. Seeds determinísticos incluirão `cliente1988`, outro cliente para isolamento e cenários de recebíveis e terminais.

Datas dos testes usarão relógio controlado. A demonstração terá dados relativos a uma data-base declarada para que “ontem” não consulte um conjunto obsoleto sem explicação. Previsão de depósito será apresentada como previsão, conforme registro de origem.

## 5. API e interface

Contrato mínimo de entrada:

```json
{"message": "Quando recebo as vendas de ontem?", "user_id": "cliente1988"}
```

Resposta planejada: `request_id`, `answer`, `route`, `agents_used`, `sources` e `status`. Quando necessário, incluir identificador de conversa e protocolo. Fontes podem ser públicas ou referências internas seguras; não expor registros completos de clientes. O HTTP diferenciará payload inválido, limite excedido e indisponibilidade; falta de evidência será um resultado de negócio explícito.

Endpoints auxiliares: liveness, readiness e documentação OpenAPI. Readiness verificará dependências locais e disponibilidade da base; não fará chamadas pagas ao modelo a cada healthcheck.

Interface:

- Chat responsivo com estados de envio, conclusão e falha.
- Perguntas sugeridas baseadas nos dez exemplos do desafio.
- Seleção de clientes fictícios exclusivamente no modo demonstração.
- Fontes clicáveis e data de consulta quando relevante.
- Resumo dos agentes acionados e ferramentas utilizadas.
- Aviso visível de dados sintéticos e confirmação de abertura de chamado.
- Falhas compreensíveis, sem stack traces ou chaves no navegador.

O payload com user_id não é autenticação. No modo local, limitar aos clientes sintéticos. Antes de disponibilização pública, vincular identidade a sessão/token validado e aplicar autorização no servidor, ou publicar apenas uma demonstração restrita com dados fictícios e limites de uso. Chaves de serviços ficam somente no backend.

## 6. Qualidade, segurança e operação

- Prompts versionados por agente, com objetivo, ferramentas permitidas, saída e comportamento sem evidência.
- Tratar páginas recuperadas e resultados web como dados não confiáveis, nunca como instruções de sistema.
- Bloquear consultas a arquivos locais, endereços privados e destinos fora das regras da coleta.
- Ferramentas com permissões mínimas, argumentos tipados e SQL parametrizado.
- Limites de mensagem, chamadas de ferramentas, duração, tokens e concorrência.
- Timeouts e retries limitados para operações idempotentes; prevenção de duplicação na criação de chamados.
- Falha de busca ou do modelo gera erro honesto; nunca uma resposta simulada apresentada como real.
- Segredos em variáveis de ambiente; `.env.example` sem credenciais; logs com redação de dados sensíveis.
- Logs por request_id: rota, agentes, ferramentas, documentos consultados, duração, erros e consumo quando informado pelo provedor.
- Métricas de latência p50/p95, erros, escalonamento, cobertura de fontes e custo estimado. Estimativa de custo usa tarifas configuradas e datadas.
- Dashboard e exportação de traces ficam como incremento após funcionamento ponta a ponta; os logs estruturados entram desde a primeira implementação.

## 7. Testes e avaliação

### Camadas

1. Unitários: contratos, transições, validação de ferramentas, autorização, montagem de citações e tratamento de falhas.
2. Integração: API + grafo + PostgreSQL/pgvector reais em ambiente de teste, com provedores externos substituídos por respostas controladas.
3. Integração real opt-in: ingestão de páginas e chamadas aos provedores reais, exigindo credenciais; separada da suíte determinística.
4. Ponta a ponta: navegador envia mensagem e exibe resposta, fontes, erro e chamado.
5. Avaliação de IA: dataset versionado e pequeno conjunto de regressão ampliado ao longo das entregas. Julgamento automatizado complementa revisão humana, sem ser a única evidência.

### Dataset inicial

Cobrir os dez exemplos do desafio, paráfrases em português/inglês, perguntas combinadas, falta de dados, cliente inexistente, tentativa de acessar outro cliente, prompt injection, ausência de fonte, timeout, resultado web desatualizado e base vazia. Prever aproximadamente 40–60 casos, divididos entre calibração e validação reservada.

Cada caso registra rota/ferramentas esperadas, evidência necessária, fatos proibidos e rubrica. Para clima/câmbio, avaliar data, localidade, unidade e fonte; não congelar um valor como resposta correta permanente.

Metas iniciais propostas, a validar após baseline: acerto de roteamento >= 90%; Recall@5 >= 85% no subconjunto com documentos relevantes rotulados; nenhuma exposição entre clientes na suíte; todas as citações retornadas correspondem a fontes reais utilizadas. Qualidade factual exige revisão de afirmações, não apenas presença de links. Latência e custo serão medidos antes de estabelecer SLO realista.

## 8. Etapas e critérios para avançar

| Etapa | Entrega | Como você valida |
|---|---|---|
| 0. Decisões e ambiente | Prazo, orçamento, provedores, destino; verificação de Python, Node, Git e Docker | Pré-requisitos e checklist executável |
| 1. Fundação | Estrutura, FastAPI, Compose, PostgreSQL/pgvector, migrações, seeds, healthchecks e `.env.example` | Subir contêineres e consultar saúde e dados fictícios |
| 2. Primeiro fluxo completo | Chat simples → API → Router → Support → ferramenta → resposta | Consultar recebíveis de `cliente1988` e verificar origem do dado |
| 3. RAG | Manifesto, ingestão, embeddings, Knowledge e citações | Inspecionar relatório e perguntar sobre produtos documentados |
| 4. Busca e cooperação | Busca web real, consultas atuais e rotas combinadas | Clima/câmbio com data e suporte técnico com evidência oficial |
| 5. Experiência e bônus | Interface final, escalonamento, controles de segurança e observabilidade | Abrir chamado e testar falha, cliente diferente e pedido sem evidência |
| 6. Validação | Suítes, dataset, relatório de métricas e ajustes | Executar testes e os dez exemplos; revisar respostas |
| 7. Entrega | README, diagrama, guia de operação, roteiro do vídeo e repositório | Executar do zero seguindo README e gravar demonstração |

Cada etapa terá instruções curtas de execução, resultado esperado, limitações conhecidas e evidência de validação. Não avançar para apresentação final com ingestão ou ferramentas apenas simuladas. Doubles são apropriados nos testes, mas a demonstração deve executar o caminho real com dados sintéticos persistidos.

## 9. Estrutura prevista

```text
backend/app/
  api/          # contratos e endpoints
  agents/       # router, knowledge, support, escalation
  orchestration/# estado e grafo
  tools/        # ferramentas de banco e busca
  rag/          # ingestão, extração e recuperação
  db/           # modelos e acesso
  core/         # configuração, autorização e logs
backend/tests/
backend/migrations/
frontend/
data/           # manifestos e seeds sem dados reais
evals/          # casos, rubricas e relatórios
docs/
docker-compose.yml
.env.example
README.md
```

## 10. Decisões pendentes e riscos

- Prazo e disponibilidade diária: determinam profundidade dos bônus, não remoção dos requisitos obrigatórios.
- Provedor e orçamento: confirmar acesso a geração, embeddings e busca. Não compartilhar chaves no chat; configuração local.
- Hospedagem: Docker local é obrigatório e suficiente para o requisito de execução; URL pública é uma entrega adicional a definir.
- Dados: proposta é usar somente clientes sintéticos. Integrações reais exigiriam contratos e acessos ainda inexistentes.
- Conteúdo oficial: páginas podem mudar, bloquear coleta ou não documentar produtos antigos; registrar cobertura e limitações, buscar outras fontes oficiais e conservar proveniência.
- Ambiente: executáveis de Python, Node e Docker encontrados no PATH; funcionamento do daemon, versões e Compose ainda não validados. Git não foi localizado pelo comando de descoberta usado; verificar instalação/PATH na etapa 0.
- Avaliação visual: o desafio contém uma imagem remota de referência; seus detalhes não foram usados como requisitos adicionais neste plano. Revisá-la na etapa de arquitetura se trouxer convenções além do texto.

## 11. Fontes de planejamento

- Requisitos: `knowledge/Desafio.md`.
- Getnet global e link para Brasil: https://www.getnet.net/en/
- LangGraph: https://docs.langchain.com/oss/python/langgraph/overview
- pgvector: https://github.com/pgvector/pgvector

As versões de dependências serão verificadas e fixadas na implementação. Este documento registra decisões propostas, não funcionalidades já construídas.
