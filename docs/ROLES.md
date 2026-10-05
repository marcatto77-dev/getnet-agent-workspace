# Papéis e acesso à Central de Atendimento

| Perfil | Telas | Endpoints |
|---|---|---|
| Cliente | Portal e seu próprio chat | Chat, perfil, máquinas e WebSocket da própria conversa. Nunca Central, fila, notas ou dados de outros clientes. |
| Técnico | Tela de Atendimento/Central | `/api/tech/service-center/*`, fila, seus atendimentos e conversa completa somente após assumir/puxar. |
| Administrador | Administração e visão operacional somente leitura | Sem endpoints operacionais de técnico; a Central é leitura administrativa quando a tela for entregue. |

Identidades vêm do cookie de sessão validado no backend. A fila apresenta apenas resumo operacional; conteúdo de conversa e notas internas exigem ser o técnico responsável.
