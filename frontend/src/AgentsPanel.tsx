import {useEffect, useState} from 'react'
import {api, formatApiError} from './api'
import './agents.css'

type Snapshot = {
  read_only: boolean; model: string; embedding_model: string; scope: string; handoff: string; languages: string
  agents: {name: string; description: string; prompt: string}[]
  guardrails: {name: string; description: string; source: string}[]
  limits: {tool_timeout_seconds: number; chat_requests_per_minute: number}
}

export function AgentsPanel() {
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'agents' | 'guardrails'>('agents')
  const load = () => {
    setError('')
    api<Snapshot>('/admin/agents').then(setData).catch(reason => setError(formatApiError(reason)))
  }
  useEffect(load, [])
  if (error) return <section className="admin-panel"><p role="alert">{error}</p><button onClick={load}>Tentar novamente</button></section>
  if (!data) return <section className="admin-panel" role="status">Carregando agentes e segurança…</section>
  return <section className="admin-panel agent-inspection">
    <div className="panel-actions"><div><h2>Agentes e segurança</h2><p>Configuração em execução · somente leitura · acesso administrativo</p></div></div>
    <div className="agent-policy-grid">
      <article><h3>Escopo do atendimento</h3><p>{data.scope}</p></article>
      <article><h3>Atendimento humano</h3><p>{data.handoff}</p></article>
      <article><h3>Idiomas e modelos</h3><p>{data.languages}</p><p>Modelo: <code>{data.model}</code><br/>Embeddings: <code>{data.embedding_model}</code></p></article>
    </div>
    <ol className="agent-flow" aria-label="Fluxo da orquestração">
      <li>Cliente</li><li>Guardrails de entrada</li><li>Router</li><li>Knowledge + Support ou Escalation</li><li>Validação de saída</li><li>Resposta</li>
    </ol>
    <div className="agent-tabs" role="group" aria-label="Visualização dos agentes">
      <button aria-pressed={tab==='agents'} onClick={()=>setTab('agents')}>Prompts dos agentes</button>
      <button aria-pressed={tab==='guardrails'} onClick={()=>setTab('guardrails')}>Regras de guardrails</button>
    </div>
    {tab==='agents' ? <>
      <p>Estes são os prompts carregados pela API. Para editar, altere <code>backend/app/prompts.py</code> e reconstrua a API. O marcador interno de detecção de vazamento está oculto.</p>
      {data.agents.map(agent=><details key={agent.name} className="agent-source"><summary>{agent.name} — {agent.description}</summary><pre>{agent.prompt}</pre></details>)}
    </> : <>
      <p>Regras do código em execução. Consulte os eventos em <strong>Logs → Guardrails</strong>. Limite: {data.limits.chat_requests_per_minute} mensagens/minuto; timeout por ferramenta: {data.limits.tool_timeout_seconds}s.</p>
      {data.guardrails.map(guard=><details key={guard.name} className="agent-source"><summary>{guard.name} — {guard.description}</summary><pre>{guard.source}</pre></details>)}
    </>}
  </section>
}
