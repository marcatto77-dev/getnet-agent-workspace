# Dashboard administrativo

Revisão de interface em 06/10/2026. Os indicadores existentes foram preservados, com detalhes paginados, consulta por data e presença autenticada com expiração.

## Interface

- Admin inicia no Dashboard ao entrar e recarregar. Menu lateral com grupos, nomes legíveis, ícones maiores e aria-current para a seção ativa. A tipografia compartilhada em admin-readability.css amplia também Usuários, Clientes, Máquinas, Base de conhecimento, Logs e Agentes, sem afetar os portais cliente/técnico. Tabelas têm texto de 15 px, formulários de 16 px e ações com alvos de pelo menos 44 px nas áreas revisadas.
- Composição assimétrica: volume de conversas em destaque, quatro indicadores do período ao lado, operação atual abaixo e gráficos em proporção 60/40 no desktop.
- Rótulos de indicadores a partir de 16 px, valores de 28 a 80 px, textos de apoio de 13 a 16 px e alvos de interação de 44 px.
- Cartões, barras por dia, rotas, taxa de escalonamento e técnicos abrem detalhes agregados em modal branco opaco.
- Dialog nativo com foco inicial, contenção do foco, Escape e retorno ao botão de origem. Suporte a movimento reduzido.
- Layout adaptável a desktop, tablet e celular; gráficos e tabela podem rolar internamente sem alargar a página.
- Período, atualização manual, atualização a cada 30 segundos, horário da última leitura, estado vazio, carregamento e erro com nova tentativa.
- Sem novas dependências, mensagens privadas ou dados inventados; custo estimado e sem handoff mantêm suas ressalvas.

## Detalhes e presença

- Visão geral inicia em Hoje. O calendário permite consultar um dia inteiro no fuso America/Sao_Paulo, incluindo o início e excluindo a meia-noite do dia seguinte.
- Gráfico fixo dos últimos sete dias, com datas sem conversas preenchidas com zero. Ver conversas lista todos os registros do intervalo, dez por página; uma barra abre apenas seu dia.
- Eventos bloqueados listam regra, horário, camada, severidade e trecho de entrada mascarado. Conteúdo de saída bloqueada é omitido para não expor instruções ou marcadores internos.
- Encaminhamento humano significa a rota do agente Escalation que prepara a fila; Support continua sendo IA. A lista de encaminhamentos mostra o cliente, a situação e o último responsável, inclusive quando ainda está na fila.
- Clientes conectados e técnicos disponíveis aparecem em seções separadas. A migration 0015 cria leases de presença por usuário e aba, com versão da sessão. O frontend envia heartbeat autenticado a cada 30 segundos e libera a aba com beacon ao sair; a ausência de heartbeat por 90 segundos expira a presença. Não depende de um processo local em memória.
- Logout, troca de senha e desativação invalidam a presença pelo token_version/status do usuário. Fechar uma aba não desconecta outra aba ainda ativa.
- O portal monta o heartbeat somente após validar a sessão de cliente. Não registra presença na tela de login. Foco e retorno à aba renovam a presença; o HTML de entrada no Nginx exige revalidação para evitar manter versões antigas após atualizar a aplicação.
- Disponibilidade salva na tabela technician_presence não prova conexão. O dashboard combina disponibilidade com lease recente. Uma sessão conectada com disponibilidade Pausa ou Offline não conta como técnico disponível.
- O dashboard lê a presença a cada 30 segundos. Sem entrega do beacon, a queda pode levar até 90 segundos, mais o intervalo da próxima leitura, para aparecer. É presença recente da aplicação, não detecção instantânea da rede.
- Endpoint POST /api/auth/presence aceita apenas o ID da aba e active; a identidade vem do cookie. GET /api/admin/dashboard/details aceita kind, period, date, page e page_size e é exclusivo de Admin. Consultas são parametrizadas e não expõem mensagens ou notas internas.

## Pesquisa e referências

Consultamos o [site oficial Getnet Brasil](https://site.getnet.com.br/) e suas seções orientadas a produtos e ações. A interpretação visual adotada é manter identidade vermelha, fundo claro, hierarquia de títulos e ações claras; não é uma reprodução de um dashboard oficial ou de um design system publicado.

A página pública do [Eye Getnet](https://site.getnet.com.br/eye/) foi localizada na pesquisa, mas a tentativa de abertura retornou 403. Não foi utilizado nem reproduzido o painel privado do produto.

Como referência de usabilidade, [NN/g: Dashboards — Making Charts and Graphs Easier to Understand](https://www.nngroup.com/articles/dashboards-preattentive/) fundamenta o agrupamento de indicadores e uso de barras/posição para comparação rápida. Escolhemos barras, em vez de velocímetros e gráficos decorativos, com números legíveis e detalhes sob demanda.

## Validação reproduzível

```powershell
cd frontend
npm run build
npx playwright test tests/dashboard.spec.ts
```

A suíte de interface usa respostas controladas para verificar modal, teclado/foco, significado das métricas, troca de período, atualização manual, erros, estados vazios e larguras de 1440, 1024, 768 e 390 px. As capturas dessa suíte ficam em `docs/evidence/dashboard/` e usam dados de teste, não devem ser interpretadas como métricas reais.

O smoke real, sem interceptar a API, pode ser executado contra o Docker:

```powershell
$env:REAL_E2E='1'
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:8080'
npx playwright test tests/dashboard-real.spec.ts
```

Por padrão usa Admin/Admin do seed demo; para senha já alterada, configure `E2E_ADMIN_USERNAME` e `E2E_ADMIN_PASSWORD` no ambiente, sem gravar senhas em arquivos. Em 06/10/2026, o smoke real passou com métricas do PostgreSQL, abertura de detalhes e período de 30 dias, sem banner de erro ou erro JavaScript.

Resultados desta revisão: build TypeScript/Vite e Ruff aprovados; suíte backend completa com 183 testes aprovados em banco de teste recriado, sem apagar o banco demo; três smokes reais do dashboard/presença executados separadamente e aprovados. A integração testa RBAC, paginação, limites do dia no fuso de Brasília, expiração de presença, múltiplas abas, logout, registros humanos e mascaramento. Inclui atualização automática, manutenção do modal durante a atualização e recuperação após uma falha sem perder a última leitura. O terceiro smoke reproduz técnico → logout → login do cliente pelo portal no mesmo contexto de navegador, com Admin em contexto separado; usa cliente1988/123 por padrão, ou E2E_CUSTOMER_USERNAME/E2E_CUSTOMER_PASSWORD. O cadastro Azul tem teste controlado de presença após validação, sem usar ou redefinir sua senha.

Na revisão de legibilidade de todas as páginas, a suíte frontend passou com 24 testes aprovados e 19 condicionais ignorados. Os quatro smokes de dashboard-real.spec.ts foram executados separadamente contra Docker e passaram, incluindo a navegação real por todas as páginas Admin e recarga inicial no Dashboard. A saída via botão Sair é validada deterministicamente; fechamento de aba por beacon continua sendo melhor esforço, sujeito ao TTL de 90 segundos. admin-readability.spec.ts valida 1440, 1024, 768 e 390 px, tamanhos computados de fonte, formulário de usuário e conteúdo expandido dos logs/agentes. Capturas em docs/evidence/admin-readability/ usam dados controlados, exceto as prefixadas real-.
