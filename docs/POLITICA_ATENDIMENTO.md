# Política de atendimento e os exemplos do desafio

O atendimento cobre Getnet e consultas de câmbio. Clima e outros assuntos alheios recebem uma recusa educada, sem pesquisa e sem abrir chamado. Esta é uma decisão de produto: o enunciado contém clima como exemplo, mas esse exemplo foi deliberadamente restringido pelo responsável pelo projeto. O enunciado não determina o idioma da documentação; o projeto está documentado em português.

## Interpretação dos dez exemplos

| Pergunta do enunciado | Decisão | Como responder |
|---|---|---|
| What's the difference between the Get Clássica and the Get Smart? | `knowledge` | Comparar funcionalidades comprovadas pelos manuais/RAG; buscar site oficial se necessário. |
| What's the weather forecast in Porto Alegre tomorrow? | `blocked` | Informar o escopo. Não buscar previsão e não encaminhar a técnico. |
| When will the money from yesterday's sales be deposited? | `support` | Consultar `get_receivables` do cliente autenticado com a data de ontem. Não garantir depósito se o dado for previsão. |
| Do I need a bank account to receive my sales via Pix? | `knowledge` | Responder com regras públicas de Pix Getnet e fontes. |
| My card machine won't connect to the internet, what should I do? | `knowledge_support` | Selecionar a máquina do cliente, consultar status e combinar com orientação oficial do modelo. |
| How does receivables advance (antecipação) work with Getnet? | `knowledge` | Explicar antecipação com fontes; não inventar taxas individuais. |
| What's the euro exchange rate today? | `knowledge`, fonte `web` | Consultar Banco Central/BCE, informar par de moedas, data efetiva e fonte. EUR/BRL é o padrão para euro. Não confundir cotação com taxa Getnet. |
| My card machine is showing a transaction decline error. | `knowledge_support` | Consultar terminal e manuais; pedir detalhes quando necessário. |
| How many installments can I split a sale into with the crediário? | `knowledge` | Recuperar condições oficiais; não inventar número de parcelas. |
| Can I sell through WhatsApp using the Payment Link? | `knowledge` | Recuperar orientações de Link de Pagamento e compartilhar fontes oficiais. |

Outros exemplos fora do escopo: receitas culinárias, futebol, filmes, programação, política e recomendações de investimento. Uma mensagem ambígua, como “não funcionou”, usa o contexto da conversa; não é recusada apenas por não conter a palavra Getnet. O guardrail também não confunde “tempo para receber a venda” com previsão do tempo nem “código de erro da máquina” com programação.

## Encaminhamento humano com consentimento

1. Pedido explícito de técnico/humano abre atendimento, mesmo na primeira mensagem.
2. RAG insuficiente tenta o site oficial; Support consulta ferramentas do próprio cliente. Ausência de evidência não cria chamado automaticamente.
3. Após três respostas de assistência na mesma conversa, uma manifestação de insatisfação provoca a pergunta “Gostaria de atendimento com um técnico humano?”. Uma quarta pergunta normal não dispara a oferta.
4. O aceite a uma oferta pendente abre o chamado. A recusa continua com a IA. “Sim” sem oferta pendente não cria chamado.

A contagem e a oferta pendente são reconstruídas de `agent_runs` no banco; não são aceitas do navegador. Cumprimentos, erros técnicos e recusas de segurança não contam como respostas de assistência. A classificação semântica de insatisfação é feita pelo Router; o limiar e a criação do chamado são controlados em código. O fluxo humano permanece na fila e no atendimento até o encerramento/desistência.

## Idiomas e apresentação

Knowledge, Support e Router recebem instruções para usar o idioma do cliente. Há mensagens de política em português, inglês e espanhol; dados e citações continuam sujeitos às mesmas validações em todos os idiomas. Isso não altera idioma, disponibilidade de produtos ou regras regionais das fontes. A interface administrativa e os eventos operacionais continuam em português.

Em **Admin → Agentes e segurança**, mostre os quatro prompts, a política, o modelo em execução e o código das camadas de guardrail. É uma visualização somente leitura, restrita ao administrador, com o canário interno oculto. Para editar prompts, altere `backend/app/prompts.py`, revise os testes e execute `docker compose up -d --build api`. Em **Logs → Guardrails**, mostre os eventos concretos de bloqueio; em **Logs → Execuções dos agentes**, mostre rotas e chamadas de ferramentas.
