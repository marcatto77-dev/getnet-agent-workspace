import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, Clock3, MessageSquare, RefreshCw, Route, ShieldAlert, UsersRound, X } from 'lucide-react'
import './dashboard.css'
import { api, formatApiError, queryString } from './api'

type Data = {
  cards: {
    attendances: number; distinct_customers: number; resolved_by_ai: number; escalated: number
    blocked: number; waiting: number; in_progress: number; average_response_ms: number
    input_tokens: number; output_tokens: number; cost: number
  }
  attendances_by_day: { day: string; total: number }[]
  recent_conversations_by_day?: { day: string; total: number }[]
  routes: { route: string; total: number }[]
  escalation_rate: number
  technicians: { id: number; display_name: string; status: string; connected?: boolean; availability?: string; active_chats: number; attended: number }[]
  connected_customers?: { id: number; display_name: string; last_seen_at: string }[]
}
type DetailKind = 'blocked' | 'conversations' | 'handoffs'
type Detail = { title: string; value?: string; description: string; rows: [string, string][]; scope: string; kind?: DetailKind; period?: string; day?: string }
type Metric = { label: string; value: string; icon: typeof Route; description: string; rows?: [string, string][]; live?: boolean; kind?: DetailKind }
const routeNames: Record<string, string> = {
  knowledge: 'Conhecimento', support: 'Suporte', knowledge_support: 'Conhecimento + suporte',
  escalation: 'Encaminhamento humano', clarify: 'Esclarecimento', blocked: 'Bloqueado',
}
const routeDescriptions: Record<string, string> = {
  knowledge: 'Knowledge: agente de IA que consulta RAG e fontes públicas autorizadas.',
  support: 'Support: agente de IA que consulta ferramentas de leitura do cliente e da máquina. Não é o técnico humano.',
  knowledge_support: 'Knowledge + Support: dois agentes de IA combinam conhecimento e dados de suporte.',
  escalation: 'Escalation: agente de IA que prepara o encaminhamento para a fila. O atendimento depois é feito por um técnico humano.',
  clarify: 'A IA pede esclarecimentos para entender a solicitação.',
  blocked: 'Guardrails recusam solicitações inseguras ou fora do escopo; isso não abre atendimento técnico.',
}
const periods: Record<string, string> = { today: 'Hoje', '7d': 'Últimos 7 dias', '30d': 'Últimos 30 dias' }
const presence: Record<string, string> = { online: 'Online', pausa: 'Em pausa', offline: 'Offline' }
const number = (value: number) => value.toLocaleString('pt-BR')
const dayLabel = (day: string) => new Date(day + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
const todayDate = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const ruleNames: Record<string, string> = { strict_utility_block: 'Clima ou utilidade fora do escopo', prompt_injection_pattern: 'Tentativa de manipular instruções', cross_customer_id: 'Acesso a outro cliente', abusive_language: 'Linguagem abusiva', input_too_long: 'Mensagem acima do limite', output_canary: 'Proteção de instruções internas', internal_value: 'Conteúdo interno na resposta', unverified_action: 'Ação não confirmada', unapproved_url: 'Fonte não autorizada', command_execution_request: 'Tentativa de executar comando', code_content: 'Código ou script enviado', prompt_injection: 'Tentativa de manipular o agente', instruction_override: 'Tentativa de substituir instruções', off_topic: 'Assunto fora do escopo', cross_customer_request: 'Acesso a outro cliente', sensitive_data: 'Dados sensíveis', canary_leak: 'Proteção de instruções internas', abusive: 'Conteúdo abusivo', untrusted_url: 'URL não autorizada' }
const statusNames: Record<string, string> = { ai: 'Com a IA', waiting: 'Na fila de técnicos', with_technician: 'Com técnico humano', assigned: 'Com técnico humano', closed: 'Encerrada' }
type RecordPage = { items: { id: string; rule?: string; layer?: string; severity?: string; sample?: string; created_at?: string; started_at?: string; customer_name?: string; status?: string; handoff_status?: string; technician_name?: string; message_count?: number; reason?: string }[]; total: number; page: number; page_size: number }

function DetailRecords({ detail }: { detail: Detail }) {
  const [day, setDay] = useState(detail.day || '')
  const [page, setPage] = useState(1)
  const [records, setRecords] = useState<RecordPage | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    setRecords(null); setError('')
    api<RecordPage>('/admin/dashboard/details?' + queryString({ kind: detail.kind, period: detail.period || 'today', date: day, page, page_size: 10 }))
      .then(value => { if (active) setRecords(value) })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : formatApiError(cause)) })
    return () => { active = false }
  }, [detail.kind, detail.period, day, page, retry])
  return <section className="dashboard-records">
    <label>Consultar um dia específico<input aria-label="Data dos detalhes" type="date" max={todayDate()} value={day} onChange={event => { setDay(event.target.value); setPage(1) }}/></label>
    <button className="dashboard-text-button" onClick={() => { setDay(''); setPage(1) }}>Usar período base</button>
    <p className="dashboard-detail-note">{day ? 'Registros de ' + dayLabel(day) : 'Registros de ' + periods[detail.period || 'today']} · horários de Brasília · 10 por página.</p>
    {error ? <div role="alert">{error}<button className="dashboard-secondary" onClick={() => setRetry(value => value + 1)}>Tentar novamente</button></div> : !records ? <p role="status">Carregando registros…</p> : <>
      <strong>{records.total} registro(s) encontrado(s)</strong>
      {records.items.map(row => <article key={row.id}>
        <div className="dashboard-record-header"><strong>{row.rule ? ruleNames[row.rule] || row.rule : row.customer_name}</strong><time>{new Date(row.created_at || row.started_at || '').toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' })}</time></div>
        {row.rule ? <><p>Regra: <code>{row.rule}</code> · camada: {row.layer} · severidade: {row.severity}</p>{row.sample && <p className="dashboard-event-sample">Trecho registrado (dados sensíveis mascarados): {row.sample}</p>}</> : <>
          <p>{statusNames[row.status || ''] || row.status} · {row.message_count} mensagens públicas</p>
          {(row.handoff_status || detail.kind === 'handoffs') && <p><strong>Técnico responsável:</strong> {row.technician_name || (row.handoff_status === 'waiting' ? 'Ainda não atribuído — aguardando na fila' : 'Sem responsável registrado')} · {statusNames[row.handoff_status || ''] || row.handoff_status}</p>}
          <small>Conversa: {row.id}</small>
        </>}
      </article>)}
      {!records.total && <p>Nenhum registro encontrado para essa seleção.</p>}
      <div className="dashboard-record-pagination"><button className="dashboard-secondary" disabled={page === 1} onClick={() => setPage(value => value - 1)}>Anterior</button><span>Página {page} de {Math.max(1, Math.ceil(records.total / records.page_size))}</span><button className="dashboard-secondary" disabled={page * records.page_size >= records.total} onClick={() => setPage(value => value + 1)}>Próxima</button></div>
    </>}
  </section>
}

function DetailDialog({ detail, close }: { detail: Detail; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const element = dialog.current!
    const opener = document.activeElement as HTMLElement | null
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    element.showModal()
    return () => { element.close(); document.body.style.overflow = previousOverflow; opener?.focus() }
  }, [])
  return <dialog ref={dialog} className="dashboard-dialog" aria-labelledby="dashboard-detail-title"
    onCancel={close} onClick={event => { if (event.target === event.currentTarget) close() }}
    onKeyDown={event => {
      if (event.key !== 'Tab') return
      const buttons = event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input,select')
      const first = buttons[0], last = buttons[buttons.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }}>
    <div className="dashboard-dialog-content">
      <button className="dashboard-close" aria-label="Fechar detalhes" onClick={close}><X aria-hidden="true"/></button>
      <span className="dashboard-eyebrow">DETALHES DO INDICADOR · {detail.scope}</span>
      <h2 id="dashboard-detail-title">{detail.title}</h2>
      {detail.value && <strong className="dashboard-detail-value">{detail.value}</strong>}
      <p>{detail.description}</p>
      <dl>{detail.rows.map(([label, value], index) => <div key={index}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {detail.kind && <DetailRecords detail={detail}/>}
      <p className="dashboard-detail-note">Resumo no momento da abertura. A lista pode ser filtrada por outra data, sem alterar o resumo acima. Nenhum conteúdo de chat ou nota interna é exibido; trechos de bloqueios são mascarados.</p>
      <button className="dashboard-secondary" onClick={close}>Voltar ao dashboard</button>
    </div>
  </dialog>
}

export function DashboardPanel(_props: { fail?: (message: string) => void }) {
  const [period, setPeriod] = useState('today')
  const [selectedDate, setSelectedDate] = useState('')
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState<Date | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [detail, setDetail] = useState<Detail | null>(null)
  useEffect(() => {
    let active = true
    let loading = false
    setData(null); setError(''); setDetail(null)
    const load = async () => {
      if (loading) return
      loading = true
      try {
        const value = await api<Data>('/admin/dashboard?' + queryString({ period, date: selectedDate }))
        if (active) { setData(value); setUpdated(new Date()); setError('') }
      } catch (cause) {
        if (active) {
          const message = cause instanceof Error ? cause.message : formatApiError(cause)
          setError(message)
        }
      } finally { loading = false }
    }
    void load()
    const timer = setInterval(() => void load(), 30_000)
    return () => { active = false; clearInterval(timer) }
  }, [period, selectedDate, refresh])

  const controls = <div className="dashboard-controls">
    <label>Período<select aria-label="Período do dashboard" value={period} onChange={event => { setSelectedDate(''); setPeriod(event.target.value) }}>
      <option value="today">Hoje</option><option value="7d">Últimos 7 dias</option><option value="30d">Últimos 30 dias</option>
    </select></label>
    <label>Ou escolha um dia<input type="date" aria-label="Dia do dashboard" max={todayDate()} value={selectedDate} onChange={event => setSelectedDate(event.target.value)}/></label>
    <button className="dashboard-secondary" onClick={() => setRefresh(value => value + 1)}><RefreshCw aria-hidden="true"/>Atualizar</button>
  </div>
  if (!data) return <div className="admin-panel dashboard-panel"><div className="dashboard-heading"><h2>Visão do atendimento</h2>{controls}</div>
    <div className="dashboard-state" role={error ? 'alert' : 'status'}>{error || 'Carregando indicadores do atendimento…'}
      {error && <button className="dashboard-secondary" onClick={() => setRefresh(value => value + 1)}>Tentar novamente</button>}</div></div>

  const c = data.cards
  const scope = selectedDate ? dayLabel(selectedDate) : periods[period]
  const recentDays = data.recent_conversations_by_day || data.attendances_by_day
  const maxDay = Math.max(1, ...recentDays.map(row => row.total))
  const displayRoutes = Object.keys(routeNames).map(route => ({ route, total: data.routes.find(row => row.route === route)?.total || 0 }))
  const maxRoute = Math.max(1, ...data.routes.map(row => row.total))
  const cards: Metric[] = [
    { label: 'Conversas iniciadas', value: number(c.attendances), icon: MessageSquare, description: 'Conversas abertas no período selecionado.', rows: data.attendances_by_day.map(row => [dayLabel(row.day), number(row.total)]), kind: 'conversations' },
    { label: 'Clientes com mensagens', value: number(c.distinct_customers), icon: UsersRound, description: 'Clientes distintos que enviaram mensagem. Um cliente pode ter mais de uma conversa.' },
    { label: 'Conversas sem handoff', value: number(c.resolved_by_ai), icon: Route, description: 'Sem encaminhamento humano. Não confirma resolução ou satisfação pela IA.' },
    { label: 'Encaminhadas a técnicos', value: number(c.escalated), icon: UsersRound, description: 'Conversas encaminhadas à fila humana; clique para ver situação e técnico responsável.', rows: [['Taxa de encaminhamento', `${data.escalation_rate}%`], ['Conversas iniciadas', number(c.attendances)]], kind: 'handoffs' },
    { label: 'Eventos bloqueados', value: number(c.blocked), icon: ShieldAlert, description: 'Bloqueios de guardrail. Clique para ver regras, horários e eventos.', kind: 'blocked' },
    { label: 'Em fila agora', value: number(c.waiting), icon: Clock3, description: 'Aguardando um técnico agora, independentemente do período selecionado.', live: true },
    { label: 'Em andamento agora', value: number(c.in_progress), icon: MessageSquare, description: 'Atendimentos humanos ativos agora, independentemente do período.', live: true },
    { label: 'Latência média', value: `${number(Math.round(c.average_response_ms))} ms`, icon: Clock3, description: 'Tempo médio por execução dos agentes. Não é o tempo de espera na fila.' },
    { label: 'Tokens utilizados', value: number(c.input_tokens + c.output_tokens), icon: Route, description: 'Consumo das execuções dos agentes. Clique para ver o custo estimado.', rows: [['Tokens de entrada', number(c.input_tokens)], ['Tokens de saída', number(c.output_tokens)], ['Custo estimado', `R$ ${Number(c.cost).toFixed(4)}`]] },
  ]
  const metric = (card: Metric, hero = false) => <button key={card.label} className={`dashboard-metric${hero ? ' dashboard-hero' : ''}`}
    aria-label={`Ver detalhes: ${card.label}`} onClick={() => setDetail({ title: card.label, value: card.value, description: card.description,
      rows: card.rows || [['Base de cálculo', card.live ? 'Estado atual do atendimento' : scope]], scope: card.live ? 'AGORA' : scope, kind: card.kind, period, day: selectedDate })}>
    <span className="dashboard-metric-top"><card.icon aria-hidden="true"/><span>{card.live ? 'OPERAÇÃO ATUAL' : 'NO PERÍODO'}</span><ArrowUpRight aria-hidden="true"/></span>
    <span className="dashboard-metric-label">{card.label}</span><strong>{card.value}</strong>
    <span className="dashboard-metric-description">{card.description}</span><span className="dashboard-metric-link">Explorar indicador <ArrowUpRight aria-hidden="true"/></span>
  </button>
  const dailyDetail = () => setDetail({title: 'Conversas dos últimos 7 dias', description: 'Cada barra conta novas conversas iniciadas no dia. A lista abaixo reúne todas as conversas dos últimos sete dias, com paginação.', rows: recentDays.map(row => [dayLabel(row.day), number(row.total)]), scope: periods['7d'], kind: 'conversations', period: '7d'})

  return <div className="admin-panel dashboard-panel">
    <div className="dashboard-heading"><div><span className="dashboard-eyebrow">CENTRAL DE INTELIGÊNCIA</span><h2>Visão do atendimento</h2><p>Acompanhe as conversas, a equipe e a segurança dos agentes.</p></div>{controls}</div>
    <div className="dashboard-update" role="status">{error ? `Não foi possível atualizar: ${error}. Exibindo a última leitura.` : `Última leitura às ${updated?.toLocaleTimeString('pt-BR')} · atualização a cada 30 segundos`}<span>Fuso: America/Sao_Paulo</span></div>
    <div className="dashboard-overview">{metric(cards[0], true)}<div className="dashboard-summary">{cards.slice(1, 5).map(card => metric(card))}</div></div>
    <div className="dashboard-operations">{cards.slice(5).map(card => metric(card))}</div>
    <div className="dashboard-charts">
      <section><div className="dashboard-section-heading"><div><h3>Conversas dos últimos 7 dias</h3><p>Cada barra representa novas conversas iniciadas naquele dia, incluindo dias com zero. Este gráfico sempre mostra os últimos 7 dias.</p></div><button className="dashboard-text-button" onClick={dailyDetail}>Ver conversas <ArrowUpRight aria-hidden="true"/></button></div>
        {recentDays.length ? <div className="dashboard-bar-chart">{recentDays.map(row => <button key={row.day} aria-label={`${dayLabel(row.day)}: ${row.total} conversas`} onClick={() => setDetail({title: `Conversas em ${dayLabel(row.day)}`, value: number(row.total), description: 'Conversas iniciadas nesta data. Não é a quantidade de mensagens.', rows: [['Data', row.day]], scope: dayLabel(row.day), kind: 'conversations', period: '7d', day: row.day})}>
          <b>{number(row.total)}</b><span className="dashboard-bar-track"><i style={{ height: `${row.total / maxDay * 100}%` }}/></span><span>{dayLabel(row.day)}</span>
        </button>)}</div> : <p className="dashboard-empty">Nenhuma conversa iniciada no período.</p>}
      </section>
      <section><div className="dashboard-section-heading"><div><h3>Caminhos dos agentes</h3><p>Execuções por rota; não equivale a conversas.</p><p>Conhecimento e Suporte são IA. Encaminhamento humano prepara a fila de técnicos.</p></div></div>
        <div className="dashboard-route-chart">{displayRoutes.map(row => <button key={row.route} aria-label={`Ver rota: ${routeNames[row.route] || row.route}`} onClick={() => setDetail({title: routeNames[row.route] || row.route, value: number(row.total), description: routeDescriptions[row.route] || 'Execuções nesta rota.', rows: [['Rota técnica', row.route]], scope, ...(row.route === 'escalation' ? { kind: 'handoffs' as DetailKind, period, day: selectedDate } : {}) })}>
          <span>{routeNames[row.route] || row.route}</span><span className="dashboard-route-track"><i style={{ width: `${row.total / maxRoute * 100}%` }}/></span><strong>{number(row.total)}</strong>
        </button>)}</div>{!data.routes.length && <p className="dashboard-empty">Nenhuma execução registrada no período.</p>}
        <button className="dashboard-escalation" onClick={() => setDetail({title: 'Encaminhamento a técnicos humanos', value: `${data.escalation_rate}%`, description: 'Conversas encaminhadas à fila humana divididas pelas iniciadas no período. Não significa que todas já foram assumidas.', rows: [['Conversas encaminhadas', number(c.escalated)], ['Conversas iniciadas', number(c.attendances)]], scope, kind: 'handoffs', period, day: selectedDate })}><strong>{data.escalation_rate}%</strong><span>Encaminhamento a técnicos<small>Ver fila, situação e responsável</small></span><ArrowUpRight aria-hidden="true"/></button>
      </section>
    </div>
    <section className="dashboard-technicians"><div className="dashboard-section-heading"><div><h3>Técnicos — atendimento humano</h3><p>Somente equipe técnica. Disponibilidade atual exige uma tela conectada; atendidos considera {scope.toLowerCase()}.</p></div><span className="dashboard-team-count">{data.technicians.filter(tech => tech.status === 'online').length} técnicos disponíveis</span></div>
      {data.technicians.length ? <div className="dashboard-table-scroll"><table><thead><tr><th>Técnico</th><th>Disponibilidade</th><th>Chats ativos agora</th><th>Atendidos no período</th><th><span className="dashboard-sr-only">Ações</span></th></tr></thead>
        <tbody>{data.technicians.map(tech => <tr key={tech.id}><td><strong>{tech.display_name}</strong></td><td><span className={`dashboard-presence ${tech.status}`}>{tech.connected === false ? 'Desconectado' : presence[tech.status] || tech.status}</span></td><td>{number(tech.active_chats)}</td><td>{number(tech.attended)}</td><td><button className="dashboard-text-button" aria-label={`Ver detalhes de ${tech.display_name}`} onClick={() => setDetail({title: tech.display_name, description: 'Resumo operacional do técnico. Disponibilidade e chats ativos são a situação atual.', rows: [['Conexão', tech.connected === false ? 'Desconectado' : 'Conectado'], ['Disponibilidade efetiva', presence[tech.status] || tech.status], ['Chats ativos agora', number(tech.active_chats)], ['Atendidos no período', number(tech.attended)]], scope})}>Detalhes <ArrowUpRight aria-hidden="true"/></button></td></tr>)}</tbody></table></div> : <p className="dashboard-empty">Nenhum técnico cadastrado.</p>}
    </section>
    <section className="dashboard-technicians"><div className="dashboard-section-heading"><div><h3>Clientes conectados agora</h3><p>Clientes não fazem parte da equipe técnica. Presença atualizada a cada 30 segundos e expirada após 90 segundos sem atualização.</p></div><span className="dashboard-team-count">{data.connected_customers?.length || 0} clientes conectados</span></div>
      {data.connected_customers?.length ? <ul className="dashboard-customer-presence">{data.connected_customers.map(customer => <li key={customer.id}><strong>{customer.display_name}</strong><span className="dashboard-presence online">Conectado</span><small>Última atividade: {new Date(customer.last_seen_at).toLocaleTimeString('pt-BR', { timeZone: 'America/Sao_Paulo' })}</small></li>)}</ul> : <p className="dashboard-empty">Nenhum cliente conectado no momento.</p>}
    </section>
    <p className="dashboard-footnote">Conversas, execuções e eventos têm bases diferentes. Clique nos indicadores para entender cada cálculo.</p>
    {detail && <DetailDialog detail={detail} close={() => setDetail(null)}/>}
  </div>
}
