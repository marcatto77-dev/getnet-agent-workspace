# Reteste dos achados funcionais — 04/10/2026

Complemento ao [relatório funcional](RELATORIO_TESTE_FUNCIONAL_2026-10-04.md). Nenhum dado de demonstração foi apagado ou alterado para estes ajustes.

| Achado | Correção | Aceite verificado |
|---|---|---|
| UX-01 — página Admin com rolagem horizontal em tablet | Grid com coluna principal `minmax(0,1fr)`, `.admin-main`/`.admin-panel` com `min-width:0`, rolagem horizontal contida em `.admin-table`; sidebar e espaçamentos reduzidos entre 701 e 1000 px | Playwright mediu `document.body.scrollWidth <= innerWidth` em Usuários, Clientes e Máquinas nos viewports 1440, 1024, 768 e 375 px; a tabela mantém rolagem própria quando necessário |
| UX-02 — bases distintas do Dashboard sem explicação | “Atendimentos” virou “Conversas iniciadas”; “Resolvidos pela IA” virou “Sem handoff”, pois a contagem anterior não provava resolução; cards e gráficos agora informam se contam conversas, execuções, eventos de bloqueio ou estado atual. A legenda informa o período em America/Sao_Paulo | Playwright verificou as explicações, inclusive o caso de 3 conversas e 4 execuções bloqueadas, sem sugerir que a soma por rota seja igual à de conversas |

Verificações locais: `npm run build` passou; `npm run test:e2e -- tests/admin.spec.ts` passou com **5 testes**. O frontend Docker foi reconstruído e iniciado sem limpar volumes. Os fluxos reais com handoff e IA pagos, apontados como cobertura pendente no relatório original, não foram executados nesta correção de UI.
