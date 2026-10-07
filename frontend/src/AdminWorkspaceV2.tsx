import { FormEvent, useEffect, useState } from 'react'
import { BrandLogo } from './BrandLogo'
import { BookOpen, Boxes, ContactRound, LayoutDashboard, LogOut, Plus, ScrollText, ShieldCheck, Users } from 'lucide-react'
import './admin.css'
import { api, formatApiError } from './api'
import { CustomersPanel } from './CustomersPanel'
import { DashboardPanel } from './DashboardPanel'
import { KnowledgePanel } from './KnowledgePanel'
import { LogsPanel } from './LogsPanel'
import { AgentsPanel } from './AgentsPanel'
import './machine-management.css'

type Role = 'admin' | 'tecnico'
type User = { id:number; username:string; role:Role; display_name:string; is_active:boolean; presence?:string }
type Page<T> = { items:T[]; total:number; page:number; page_size:number }
type Section = 'dashboard'|'users'|'customers'|'machines'|'knowledge'|'logs'|'agents'

const roleLabel:Record<Role,string> = { admin:'Administrador', tecnico:'Técnico' }

export function AdminWorkspaceV2() {
  const [me, setMe] = useState<User|null>(null)
  const [section, setSection] = useState<Section>('dashboard')
  const [error, setError] = useState('')
  const [ragDegraded, setRagDegraded] = useState(false)

  useEffect(() => {
    api<User>('/auth/me').then(user => {
      if (user.role !== 'admin') throw new Error('Acesso restrito a administradores.')
      setMe(user)
    }).catch(() => location.replace('/login'))
  }, [])
  useEffect(() => {
    fetch('/api/health/ready').then(response => response.ok ? response.json() : null)
      .then(status => setRagDegraded(Boolean(status?.degraded))).catch(() => undefined)
  }, [])

  const title:Record<Section,string> = { dashboard:'Dashboard', users:'Usuários', customers:'Clientes', machines:'Máquinas', knowledge:'Base de conhecimento', logs:'Logs', agents:'Agentes e segurança' }
  const logout = async () => { await api('/auth/logout', { method:'POST' }); location.assign('/login') }
  const fail = (value:string) => setError(formatApiError(value))

  return <main className="admin-shell">
    <aside className="admin-nav">
      <BrandLogo className="admin-brand" caption="ADMIN WORKSPACE"/>
      <nav aria-label="Menu administrativo">{[
        {label:'Visão geral',items:[['dashboard',LayoutDashboard,'Dashboard']]},
        {label:'Gestão',items:[['users',Users,'Usuários'],['customers',ContactRound,'Clientes'],['machines',Boxes,'Máquinas']]},
        {label:'Inteligência e controle',items:[['knowledge',BookOpen,'Base de conhecimento'],['agents',ShieldCheck,'Agentes e segurança'],['logs',ScrollText,'Logs']]},
      ].map(group => <div className="admin-nav-group" key={group.label}><p className="admin-nav-group-title">{group.label}</p>{(group.items as [Section, typeof Users, string][]).map(([id,Icon,label]) => <button key={id} aria-current={section===id?'page':undefined} className={section===id?'active':''} onClick={() => { setSection(id); setError('') }}><Icon aria-hidden="true"/><span className="admin-nav-label">{label}</span></button>)}</div>)}</nav>
      <div className="admin-profile"><strong>{me?.display_name}</strong><span>Administrador</span><button onClick={logout}><LogOut/>Sair</button></div>
    </aside>
    <section className="admin-main">
      <header><div><small>ADMINISTRAÇÃO</small><h1>{title[section]}</h1></div></header>
      {ragDegraded && <div className="admin-alert" role="status">Base de conhecimento indisponível ou vazia. <button onClick={() => setSection('knowledge')}>Abrir reindexação</button></div>}
      {error && <div className="admin-alert" role="alert">{error}<button onClick={() => setError('')}>×</button></div>}
      {section==='dashboard' && <DashboardPanel/>}
      {section==='users' && <UsersPanel me={me} fail={fail}/>}
      {section==='customers' && <CustomersPanel fail={fail}/>}
      {section==='machines' && <MachinesPanel fail={fail}/>}
      {section==='knowledge' && <KnowledgePanel fail={fail}/>}
      {section==='logs' && <LogsPanel fail={fail} audit={<AuditPanel fail={fail}/>}/>}
      {section==='agents' && <AgentsPanel/>}
    </section>
  </main>
}

function UsersPanel({ me, fail }:{ me:User|null; fail:(message:string)=>void }) {
  const [items, setItems] = useState<User[]>([])
  const [editing, setEditing] = useState<User|null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const load = async () => {
    try {
      setItems(await api<User[]>('/admin/users'))
    } catch (error) { fail(formatApiError(error)) }
  }
  useEffect(() => { void load() }, [])
  const save = async (event:FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<string,string>
    const payload:Record<string,unknown> = { username:values.username.trim(), display_name:values.display_name.trim(), role:values.role, is_active:values.is_active==='true' }
    if (values.password) payload.password = values.password
    try {
      setSaving(true)
      if (editing) await api(`/admin/users/${editing.id}`, { method:'PATCH', body:JSON.stringify(payload) })
      else await api('/admin/users', { method:'POST', body:JSON.stringify({ ...payload, password:values.password }) })
      setEditing(null); setCreating(false); await load()
    } catch (error) { fail(formatApiError(error)) } finally { setSaving(false) }
  }
  const toggle = async (user:User) => {
    const action = user.is_active ? 'desativar' : 'ativar'
    if (!confirm(`Confirma ${action} ${user.display_name}?`)) return
    try { await api(`/admin/users/${user.id}`, { method:'PATCH', body:JSON.stringify({ is_active:!user.is_active }) }); await load() }
    catch (error) { fail(formatApiError(error)) }
  }
  const modal = creating || editing
  return <div className="admin-panel">
    <div className="panel-actions"><div><h2>Equipe interna</h2><p>Administradores e técnicos autorizados. Clientes são gerenciados na aba Clientes.</p></div><button className="primary" onClick={() => setCreating(true)}><Plus/>Novo usuário</button></div>
    <div className="admin-table"><table><thead><tr><th>Nome</th><th>Usuário</th><th>Perfil</th><th>Presença</th><th>Status</th><th/></tr></thead><tbody>
      {items.map(user => <tr key={user.id}><td><strong>{user.display_name}</strong>{user.id===me?.id && <small> Você</small>}</td><td>{user.username}</td><td>{roleLabel[user.role]}</td><td>{user.role==='tecnico' ? user.presence || 'offline' : '—'}</td><td><span className={'pill '+(user.is_active?'success':'muted')}>{user.is_active?'Ativo':'Inativo'}</span></td><td><button onClick={() => setEditing(user)}>Editar</button><button onClick={() => void toggle(user)}>{user.is_active?'Desativar':'Ativar'}</button></td></tr>)}
    </tbody></table></div>
    {modal && <UserModal user={editing} saving={saving} close={() => { setEditing(null); setCreating(false) }} save={save}/>}
  </div>
}

function UserModal({ user, saving, close, save }:{ user:User|null; saving:boolean; close:()=>void; save:(event:FormEvent<HTMLFormElement>)=>void }) {
  const [role, setRole] = useState<Role>(user?.role || 'tecnico')
  return <div className="admin-modal"><form onSubmit={save}>
    <button type="button" className="modal-x" onClick={close}>×</button><h2>{user?'Editar usuário':'Novo usuário'}</h2>
    <label>Nome de exibição<input name="display_name" required minLength={2} defaultValue={user?.display_name}/></label>
    <label>Usuário de login<input name="username" required minLength={3} defaultValue={user?.username}/></label>
    <label>{user?'Nova senha (opcional)':'Senha'}<input name="password" type="password" required={!user} minLength={8} autoComplete="new-password"/></label>
    <label>Perfil<select name="role" value={role} onChange={event => setRole(event.target.value as Role)}><option value="admin">Administrador</option><option value="tecnico">Técnico</option></select></label>
    <label>Status<select name="is_active" defaultValue={String(user?.is_active ?? true)}><option value="true">Ativo</option><option value="false">Inativo</option></select></label>
    <button className="primary" disabled={saving}>{saving?'Salvando…':user?'Salvar alterações':'Criar usuário'}</button>
  </form></div>
}

function MachinesPanel({ fail }:{ fail:(message:string)=>void }) {
  const [kind, setKind] = useState<'terminal'|'model'>('terminal')
  const [data, setData] = useState<Page<any>>({items:[],total:0,page:1,page_size:20})
  const [customers, setCustomers] = useState<any[]>([])
  const [models, setModels] = useState<any[]>([])
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [dialog, setDialog] = useState(false)
  const [editing, setEditing] = useState<any|null>(null)
  const [saving, setSaving] = useState(false)
  const load = () => api<Page<any>>(`/admin/machines?kind=${kind}&search=${encodeURIComponent(search)}&page=${page}&page_size=20`).then(setData).catch(error => fail(formatApiError(error)))
  useEffect(() => { void load() }, [kind, page, search])
  useEffect(() => {
    api<Page<any>>('/admin/customers?page=1&page_size=100').then(response => setCustomers(response.items)).catch(error => fail(formatApiError(error)))
    api<Page<any>>('/admin/machines?kind=model&page=1&page_size=100').then(response => setModels(response.items)).catch(error => fail(formatApiError(error)))
  }, [])
  const openCreate = () => { setEditing(null); setDialog(true) }
  const openEdit = (item:any) => { setEditing(item); setDialog(true) }
  const save = async (event:FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<string,string>
    try {
      setSaving(true)
      if (kind==='model') {
        const payload = { name:values.name.trim(), is_active:values.is_active==='true' }
        if (editing) await api(`/admin/machines/model/${editing.id}`,{method:'PATCH',body:JSON.stringify(payload)})
        else await api('/admin/machines',{method:'POST',body:JSON.stringify({kind:'model',name:payload.name})})
      } else {
        const payload = { serial_number:values.serial_number.trim().toUpperCase(), customer_id:values.customer_id, model_id:Number(values.model_id), status:values.status, apelido:values.apelido.trim() || null }
        if (editing) await api(`/admin/machines/terminal/${editing.id}`,{method:'PATCH',body:JSON.stringify(payload)})
        else await api('/admin/machines',{method:'POST',body:JSON.stringify({kind:'terminal',...payload})})
      }
      setDialog(false); setEditing(null); await load()
      if (kind==='model') api<Page<any>>('/admin/machines?kind=model&page=1&page_size=100').then(response => setModels(response.items))
    } catch (error) { fail(formatApiError(error)) } finally { setSaving(false) }
  }
  const remove = async (item:any) => { if (!confirm(`Confirma remover ${kind==='model'?item.name:(item.serial_number||item.id)}?`)) return; try { await api(`/admin/machines/${kind}/${item.id}`,{method:'DELETE'}); await load(); if(kind==='model') api<Page<any>>('/admin/machines?kind=model&page=1&page_size=100').then(response=>setModels(response.items)) } catch (error) { fail(formatApiError(error)) } }
  const modelColumns = <><th>Modelo</th><th>Ativo</th><th>Terminais</th></>
  const terminalColumns = <><th>Serial</th><th>Apelido</th><th>Cliente</th><th>Modelo</th><th>Status</th></>
  return <div className="admin-panel machine-management">
    <div className="panel-actions"><div><h2>Parque de máquinas</h2><p>Seriais cadastrados e terminais agrupados por modelo.</p></div><button className="primary" onClick={openCreate}><Plus/>Novo {kind==='model'?'modelo':'terminal'}</button></div>
    <div className="admin-segment"><button className={kind==='terminal'?'active':''} onClick={() => setKind('terminal')}>Terminais</button><button className={kind==='model'?'active':''} onClick={() => setKind('model')}>Modelos</button></div>
    <form className="machine-tools" onSubmit={event=>{event.preventDefault();setPage(1);void load()}}><input aria-label="Buscar máquinas" placeholder="Buscar serial, cliente ou modelo" value={search} onChange={event=>{setSearch(event.target.value);setPage(1)}}/></form>
    <div className="admin-table"><table><thead><tr>{kind==='model' ? modelColumns : terminalColumns}<th/></tr></thead><tbody>
      {data.items.map(item => <tr key={item.id}>
        {kind==='model' ? <><td><strong>{item.name}</strong></td><td><span className={'pill '+(item.is_active?'success':'muted')}>{item.is_active?'Ativo':'Inativo'}</span></td><td>{item.terminal_count}</td></> : <><td><strong>{item.serial_number}</strong></td><td>{item.apelido||'—'}</td><td>{item.customer_name}</td><td>{item.model_name}</td><td><span className="pill">{item.status}</span></td></>}
        <td><button onClick={() => openEdit(item)}>Editar</button><button onClick={() => void remove(item)}>Remover</button></td>
      </tr>)}
      {!data.items.length&&<tr><td colSpan={kind==='model'?4:6} className="machine-empty">Nenhum registro encontrado.</td></tr>}
    </tbody></table></div>
    <div className="pagination"><span>{data.total} registro(s)</span><button disabled={page<=1} onClick={()=>setPage(value=>value-1)}>Anterior</button><button disabled={page*data.page_size>=data.total} onClick={()=>setPage(value=>value+1)}>Próxima</button></div>
    {dialog&&<div className="admin-modal"><form className="machine-modal" onSubmit={save}><button type="button" className="modal-x" aria-label="Fechar" onClick={()=>setDialog(false)}>×</button><small className="modal-eyebrow">PARQUE DE MÁQUINAS</small><h2>{editing?'Editar':'Cadastrar'} {kind==='model'?'modelo':'terminal'}</h2><p className="modal-description">{kind==='model'?'O modelo agrupa os terminais compatíveis.':'Informe o serial e vincule o terminal ao cliente e modelo corretos.'}</p>
      {kind==='model'?<><label>Nome do modelo<input name="name" required minLength={2} defaultValue={editing?.name} placeholder="Ex.: Get Smart"/></label>{editing&&<label>Status<select name="is_active" defaultValue={String(editing.is_active)}><option value="true">Ativo</option><option value="false">Inativo</option></select></label>}</>:<>
        <label>Serial da máquina<input name="serial_number" required minLength={2} maxLength={120} pattern="[A-Za-z0-9-]+" defaultValue={editing?.serial_number} placeholder="Ex.: A1B2C3" autoCapitalize="characters"/><small className="field-hint">Use letras, números ou hífen. O serial precisa ser único.</small></label>
        <label>Apelido <span>(opcional)</span><input name="apelido" defaultValue={editing?.apelido||''} placeholder="Ex.: Caixa principal"/></label>
        <label>Cliente<select name="customer_id" required defaultValue={editing?.customer_id||''}><option value="">Selecione um cliente</option>{customers.map(customer=><option key={customer.id} value={customer.id}>{customer.nome}</option>)}</select></label>
        <label>Modelo<select name="model_id" required defaultValue={editing?.model_id||''}><option value="">Selecione um modelo</option>{models.filter(model=>model.is_active||model.id===editing?.model_id).map(model=><option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
        <label>Status<select name="status" required defaultValue={editing?.status||'offline'}><option value="online">Online</option><option value="offline">Offline</option></select></label>
      </>}
      <div className="modal-actions"><button type="button" className="secondary" onClick={()=>setDialog(false)}>Cancelar</button><button className="primary" disabled={saving}>{saving?'Salvando…':'Salvar'}</button></div>
    </form></div>}
  </div>
}

function AuditPanel({ fail }:{ fail:(message:string)=>void }) {
  const [data, setData] = useState<Page<any>>({items:[],total:0,page:1,page_size:20})
  useEffect(() => { api<Page<any>>('/admin/audit?page_size=50').then(setData).catch(error => fail(formatApiError(error))) }, [])
  return <div className="admin-panel"><div className="panel-actions"><div><h2>Registro de auditoria</h2><p>Alterações administrativas sem credenciais ou segredos.</p></div></div><div className="audit-list">{data.items.map(row => <article key={row.id}><span>{new Date(row.created_at).toLocaleString('pt-BR')}</span><strong>{row.action}</strong><p>{row.actor_name||'Sistema'} · {row.entity} #{row.entity_id}</p><code>{JSON.stringify(row.diff)}</code></article>)}</div></div>
}
