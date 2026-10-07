# Política de atendimento e os exemplos do desafio

O atendimento cobre Getnet e consultas de câmbio. Clima e outros assuntos alheios recebem uma recusa educada, sem pesquisa e sem abrir chamado. Esta é uma decisão de produto: o enunciado contém clima como exemplo, mas esse exemplo foi deliberadamente restringido pelo responsável pelo projeto. O enunciado não determina o idioma da documentação; o projeto está documentado em português.

## Interpretação dos dez exemplos

### Prioridade e identificação do RAG

Perguntas Getnet classificadas como Knowledge/Knowledge+Support consultam primeiro a base interna, mesmo se o Router inicialmente sugerir web. O modelo selecionado só complementa a consulta em suporte técnico. A recuperação combina busca vetorial com até dois resultados textuais relevantes de títulos/trechos; ambos excluem documentos pendentes ou em quarentena. O teste de endereço verifica que um cadastro curto entra nas evidências, mesmo com similaridade vetorial baixa.

No chat, “Base interna” identifica trechos indexados, inclusive páginas coletadas do site; “Busca online” identifica consulta web naquele atendimento. Uma URL Getnet não prova navegação ao vivo. Para auditoria, verifique `rag.retrieve`, `llm.compose` e a ausência/presença de `web_search` nos logs.

Revisão de 06/10/2026: os registros das perguntas de Link de Pagamento já mostravam RAG sem busca online. Na pergunta de endereço, a seleção de Get Smart havia contaminado a consulta, provocando fallback web; a regra foi corrigida. A recuperação foi verificada no banco local com vetor previamente armazenado, sem exportar trechos para uma API externa. Não houve alteração nem exclusão de documentos.

Após as alterações: 166 testes backend e 28 testes frontend aprovados; 45 e 20 testes opt-in, respectivamente, ignorados nessa rodada. Ruff e builds passaram. O ambiente local está com `DEMO_UNLIMITED_USAGE=true`, retirando tetos diários da demonstração sem remover autenticação, guardrails ou rate limits por minuto; créditos OpenAI continuam necessários.

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

### Câmbio e esclarecimentos

“Qual o valor do câmbio?” sem moeda pede o par. “Dólar para real hoje” responde a esse esclarecimento e faz a consulta USD/BRL, em vez de repetir a pergunta. Uma moeda isolada usa BRL como destino padrão; sem data, consulta a informação mais recente. Datas curtas (“hoje”, “ontem”, dd/mm/aaaa) podem completar a última pergunta de câmbio do cliente, sem reaproveitar histórico de outra conversa nem de um assunto diferente.

Consultas de câmbio não são limitadas a dólar/euro: uma moeda sem destino usa BRL; pares explícitos como USD/EUR preservam o destino. O reconhecimento usa nomes comuns/códigos ISO e os campos estruturados `currency_base`/`currency_quote` do Router para outros nomes. Nomes ambíguos exigem esclarecimento, não uma moeda inventada.

USD, EUR, GBP, JPY, CHF, CAD, AUD, DKK, NOK e SEK para BRL têm consulta pública estruturada à API PTAX do Banco Central. Pares cruzados dessas moedas (incluindo BRL como origem) calculam uma conversão indicativa pela razão das referências de venda de um mesmo fechamento. Datas diferentes nunca são misturadas e essa razão não representa preço de compra/venda executável. Somente parâmetros de moeda/data saem nessa requisição, com endpoint fixo, timeout e sem redirects. Valores ausentes, inválidos ou não positivos não são liberados. Outras moedas, como ARS, e indisponibilidade da API usam busca financeira nos domínios oficiais permitidos (Banco Central/BCE). Isso não garante que todas as moedas tenham cotação publicada nessas fontes. Falha de consulta é informada como falha de fonte, não como falta de contexto, nem substituída por uma resposta sobre o Conversor Getnet. Não há encaminhamento automático a humano por indisponibilidade.

Referência técnica: [BCB — documentação da API de boletins PTAX](https://www.bcb.gov.br/conteudo/dadosabertos/BCBDepin/gnastportal-dados-abertostaxas-de-cambio---todos-os-boletins-diarios.pdf). As cotações têm data efetiva e caráter de referência, não são taxas da Getnet ou cotações em tempo real de uma corretora.

1. Pedido explícito de técnico/humano abre atendimento, mesmo na primeira mensagem.
2. RAG insuficiente tenta o site oficial; Support consulta ferramentas do próprio cliente. Ausência de evidência não cria chamado automaticamente.
3. Após três respostas de assistência na mesma conversa, uma manifestação de insatisfação provoca a pergunta “Gostaria de atendimento com um técnico humano?”. Uma quarta pergunta normal não dispara a oferta.
4. O aceite a uma oferta pendente abre o chamado. A recusa continua com a IA. “Sim” sem oferta pendente não cria chamado.

A contagem e a oferta pendente são reconstruídas de `agent_runs` no banco; não são aceitas do navegador. Cumprimentos, erros técnicos e recusas de segurança não contam como respostas de assistência. A classificação semântica de insatisfação é feita pelo Router; o limiar e a criação do chamado são controlados em código. O fluxo humano permanece na fila e no atendimento até o encerramento/desistência.

## Idiomas e apresentação

### Respostas diretas, com evidência

A política compartilhada `ANSWER_STYLE` em `backend/app/prompts.py` orienta Knowledge, Support e busca web a começar pela resposta sustentada pela fonte, com citação. Uma fonte pertinente pode ser suficiente: não é necessário acrescentar dúvidas genéricas ou alegar que faltou confirmação em outros documentos.

Isso não aumenta a certeza artificialmente. Divergências, dados individuais ausentes, previsões, regras por plano/país e informações desatualizadas para perguntas atuais continuam explícitos. O backend mantém a validação de IDs de fontes e os guardrails; não remove ressalvas por substituição de texto.

Conteúdo `kind=manual` é texto cadastrado administrativamente, não necessariamente um manual oficial. Deve receber atribuição breve à base, sem inventar procedência oficial. Exemplo de formato: “O endereço cadastrado na nossa base é [endereço informado] [1]”. A qualidade factual desse conteúdo depende da revisão do cadastro; o estilo da resposta não certifica sua autenticidade.

Informações institucionais, incluindo endereço e a relação Getnet–Santander, pertencem ao escopo Getnet. Uma exceção determinística estreita corrige classificações `off_topic` de perguntas diretas sobre essa relação; não libera instruções adicionais, ataques ou suporte bancário genérico. O marcador de evidência não confiável proíbe executar instruções dos documentos, não exige duvidar de todos os fatos.

O fluxo consulta o RAG primeiro. Ausência de trechos, evidência insuficiente ou uma resposta pública explicitamente não verificada acionam busca oficial automaticamente, sem pedir autorização. Citações válidas por si só não provam que o trecho responde à pergunta: o prompt exige sinalizar cobertura insuficiente. A detecção adicional de ressalvas é uma proteção complementar, não uma prova completa de veracidade. Se a busca também não fornecer evidência, o sistema informa a limitação sem inventar respostas nem criar chamado automaticamente.

Knowledge, Support e Router recebem instruções para usar o idioma do cliente. Há mensagens de política em português, inglês e espanhol; dados e citações continuam sujeitos às mesmas validações em todos os idiomas. Isso não altera idioma, disponibilidade de produtos ou regras regionais das fontes. A interface administrativa e os eventos operacionais continuam em português.

Em **Admin → Agentes e segurança**, mostre os quatro prompts, a política, o modelo em execução e o código das camadas de guardrail. É uma visualização somente leitura, restrita ao administrador, com o canário interno oculto. Para editar prompts, altere `backend/app/prompts.py`, revise os testes e execute `docker compose up -d --build api`. Em **Logs → Guardrails**, mostre os eventos concretos de bloqueio; em **Logs → Execuções dos agentes**, mostre rotas e chamadas de ferramentas.
