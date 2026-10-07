# Interfaces do cliente e do técnico

## Escopo da revisão

- Login interno e do cliente, troca inicial de senha: títulos, campos e ações mais legíveis.
- Cliente: navegação, chat, sugestões, mensagens, fontes, compositor, máquinas e conta.
- Técnico: menu lateral, fila, meus atendimentos, outros técnicos, encerrados, paginação, conversa, contexto, notas internas e modais de prévia/transferência.
- Contexto continua disponível no celular, abaixo da conversa. Chat e listas possuem rolagem própria; campos não ultrapassam a largura da tela.
- Fluxos, autenticação, permissões, envio de mensagens e regras dos agentes não foram alterados nesta revisão visual.

## Refinamento do chat do cliente

Em 06/10/2026, o chat recebeu uma segunda revisão de proporções: janela de até 1440 px, cabeçalho e rodapé compactos, texto de mensagens de 16 px com comprimento de linha limitado, compositor disponível abaixo da área rolável e identificação do assistente agrupada com a frase de ajuda. O menu marca a página atual em vermelho e com `aria-current="page"`, sem depender apenas da cor. A revisão não altera o ciclo de vida das conversas.

Referência de pesquisa: [Nielsen Norman Group — Customer-Service Chat](https://www.nngroup.com/articles/chat-ux/), especialmente diferenciação dos participantes e clareza do estado do atendimento. A largura e a tipografia foram decisões de design deste projeto, verificadas em desktop e celular, não uma cópia de outra interface.

Após esse refinamento: build aprovado, 28 testes frontend aprovados (20 testes reais opt-in não executados nessa rodada) e teste real dos portais aprovado. A resposta longa foi conferida visualmente em 1875 e 390 px; navegação ativa e proporções também possuem asserções automatizadas.

## Origem da marca

O PNG original, sem redesenho, veio de https://site.getnet.com.br/wp-content/uploads/2022/08/LOGO-GETNET.png e está incorporado em `frontend/src/assets/getnetLogo.ts`. O componente `BrandLogo.tsx` é compartilhado pelos portais e pelo Admin. A marca pertence à Getnet; o projeto é uma demonstração não oficial. A imagem não depende de acesso à internet durante a navegação.

## Verificação reproduzível

Na pasta `frontend`, com dependências instaladas:

```powershell
npm run build
npx playwright test tests/portal-readability.spec.ts
npx playwright test
```

O teste dos portais usa respostas de API controladas e verifica larguras de 1440, 1024, 768 e 390 pixels, imagem carregada, legibilidade, ausência de transbordamento horizontal, contexto do técnico, prévia, transferência e histórico encerrado sem compositor. Também verifica login e troca de senha no celular. Não substitui testes de integração com backend.

Capturas em `docs/evidence/portal-readability/` usam dados simulados exclusivamente para inspeção visual. Após instalar esta versão, recarregue abas antigas com Ctrl+F5.

Verificação desta revisão em 06/10/2026: build Docker concluído, 27 testes frontend aprovados e 5 testes contra Docker/banco real aprovados (4 de Dashboard/presença e 1 dos portais). Os testes reais adicionais da suíte permanecem opt-in e não estão incluídos nessa contagem.

Para repetir os cinco testes reais, com a demonstração em execução e as credenciais seed ainda válidas:

```powershell
$env:REAL_E2E='1'
$env:PLAYWRIGHT_BASE_URL='http://localhost:8080'
npx playwright test tests/dashboard-real.spec.ts tests/portal-readability-real.spec.ts --workers=1
```

O teste real dos portais abre chat, máquinas, conta, fila e encerrados sem enviar mensagens, criar usuários ou alterar senhas; realiza login/logout com os usuários de demonstração.
