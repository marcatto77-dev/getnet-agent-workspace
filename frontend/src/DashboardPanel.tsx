import { useEffect, useState } from 'react'
import { Clock3, MessageSquare, Route, ShieldAlert, UsersRound } from 'lucide-react'
import './dashboard.css'
import { api } from './api'

type Data = {
  cards: {
    attendances: number; distinct_customers: number; resolved_by_ai: number; escalated: number
    blocked: number; waiting: number; in_progress: number; average_response_ms: number
    input_tokens: number; output_tokens: number; cost: number
  }
  attendances_by_day: { day: string; total: number }[]
  routes: { route: string; total: number }[]
  escalation_rate: number
  technicians: { id: number; display_name: string; status: string; active_chats: number; attended: number }[]
}

const routeNames: Record<string, string> = {
  knowledge: 'Conhecimento', support: 'Suporte', knowledge_support: 'Conhecimento + suporte',
  escalation: 'Escalonamento', clarify: 'Esclarecimento', blocked: 'Bloqueado',
}

export function DashboardPanel({ fail }: { fail: (message: string) => void }) {
  const [period, setPeriod] = useState('today')
  const [data, setData] = useState<Data | null>(null)
  useEffect(() => {
    let active = true
    const load = () => api<Data>(`/admin/dashboard?period=${period}`)
      .then(value => { if (active) setData(value) })
      .catch(error => { if (active) fail(error.message) })
    void load()
    const timer = setInterval(load, 30_000)
    return () => { active = false; clearInterval(timer) }
  }, [period])

  if (!data) return <div className="admin-panel">Carregando indicadores…</div>
  const c = data.cards
  const maxDay = Math.max(1, ...data.attendances_by_day.map(row => row.total))
  const maxRoute = Math.max(1, ...data.routes.map(row => row.total))
  const cards = [
    { label: 'Conversas iniciadas', value: c.attendances, icon: MessageSquare, detail: 'Conversas abertas no período selecionado.' },
    { label: 'Clientes com mensagens', value: c.distinct_customers, icon: UsersRound, detail: 'Clientes distintos que enviaram mensagem no período.' },
    { label: 'Sem handoff', value: c.resolved_by_ai, icon: Route, detail: 'Conversas sem encaminhamento humano; não significa resolução pela IA.' },
    { label: 'Escaladas', value: c.escalated, icon: UsersRound, detail: 'Conversas iniciadas no período que tiveram handoff.' },
    { label: 'Eventos bloqueados', value: c.blocked, icon: ShieldAlert, detail: 'Bloqueios de guardrail no período; pode haver mais de um por conversa.' },
    { label: 'Em fila agora', value: c.waiting, icon: Clock3, detail: 'Estado atual da fila, independente do período selecionado.' },
    { label: 'Em andamento agora', value: c.in_progress, icon: MessageSquare, detail: 'Atendimentos humanos ativos agora, independente do período.' },
    { label: 'Latência média por execução', value: `${Math.round(c.average_response_ms)} ms`, icon: Clock3, detail: 'Média das execuções dos agentes no período.' },
    { label: 'Tokens / custo estimado', value: `${c.input_tokens + c.output_tokens} · R$ ${Number(c.cost).toFixed(4)}`, icon: Route, detail: 'Soma das execuções dos agentes no período.' },
  ]

  return <div className="admin-panel dashboard-panel">
    <div className="panel-actions">
      <div><h2>Visão do atendimento</h2><p>Período em America/Sao_Paulo · atualização a cada 30 segundos. Conversas, execuções e eventos têm bases diferentes.</p></div>
      <select aria-label="Período do dashboard" value={period} onChange={event => setPeriod(event.target.value)}>
        <option value="today">Hoje</option><option value="7d">7 dias</option><option value="30d">30 dias</option>
      </select>
    </div>
    <div className="dashboard-cards">{cards.map(card => <article key={card.label} title={card.detail}>
      <card.icon aria-hidden="true"/><span>{card.label}</span><strong>{card.value}</strong><small>{card.detail}</small>
    </article>)}</div>
    <div className="dashboard-charts">
      <section><h3>Conversas iniciadas por dia</h3><p className="metric-explanation">Uma conversa conta uma vez no dia em que começou.</p>
        <div className="bar-chart">{data.attendances_by_day.map(row => <div key={row.day}>
          <span>{new Date(row.day + 'T12:00:00').toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}</span>
          <i style={{ height: `${Math.max(8, row.total / maxDay * 120)}px` }}/><b>{row.total}</b>
        </div>)}</div>
      </section>
      <section><h3>Execuções por rota (inclui bloqueios)</h3><p className="metric-explanation">Cada mensagem processada pode gerar uma execução; a soma não equivale ao número de conversas.</p>
        <div className="route-chart">{data.routes.map(row => <div key={row.route}>
          <span>{routeNames[row.route] || row.route}</span><i><b style={{ width: `${row.total / maxRoute * 100}%` }}/></i><strong>{row.total}</strong>
        </div>)}</div>
        <div className="escalation-rate"><strong>{data.escalation_rate}%</strong><span>conversas escaladas ÷ conversas iniciadas no período</span></div>
      </section>
    </div>
    <section className="technician-panel"><h3>Técnicos</h3><p className="metric-explanation">Chats ativos são o estado atual; atendidos considera o período selecionado.</p>
      <table><thead><tr><th>Nome</th><th>Status</th><th>Chats ativos agora</th><th>Atendidos no período</th></tr></thead>
        <tbody>{data.technicians.map(tech => <tr key={tech.id}><td><strong>{tech.display_name}</strong></td>
          <td><span className={'presence-dot ' + tech.status}/>{tech.status}</td><td>{tech.active_chats}</td><td>{tech.attended}</td></tr>)}</tbody>
      </table>
    </section>
  </div>
}
