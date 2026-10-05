import { FormEvent, useEffect, useState } from 'react'
import { Plus, Search, Unlink } from 'lucide-react'
import { api, formatApiError, queryString } from './api'
import './customers.css'
import './customer-edit.css'

type Terminal = { id:string; serial_number:string; apelido?:string|null; model_name:string; model_id:number; status:string; installed_at?:string }
type Customer = { id:string; username:string; nome:string; email?:string|null; telefone?:string|null; is_active:boolean; must_change_password:boolean; terminal_count:number; terminals?:Terminal[] }
type Page<T> = { items:T[]; total:number; page:number; page_size:number }
type Modal = 'details'|'create'|'edit'|'reset'|'link'|''

export function CustomersPanel({ fail }:{ fail:(message:string)=>void }) {
  const [data,setData] = useState<Page<Customer>>({items:[],total:0,page:1,page_size:20})
  const [search,setSearch] = useState('')
  const [selected,setSelected] = useState<Customer|null>(null)
  const [modal,setModal] = useState<Modal>('')
  const [models,setModels] = useState<any[]>([])
  const [saving,setSaving] = useState(false)

  const load = async () => {
    try { setData(await api<Page<Customer>>(`/admin/customers?${queryString({search,page_size:50})}`)) }
    catch (error) { fail(formatApiError(error)) }
  }
  const open = async (id:string, nextModal:Modal = '') => {
    try {
      setSelected(await api<Customer>(`/admin/customers/${id}`))
      setModal(nextModal)
    }
    catch (error) { fail(formatApiError(error)) }
  }
  useEffect(() => { void load() }, [search])
  useEffect(() => {
    api<Page<any>>('/admin/machines?kind=model&page=1&page_size=100').then(result=>setModels(result.items)).catch(error=>fail(formatApiError(error)))
  }, [])

  async function save(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<string,string>
    try {
      setSaving(true)
      if (modal==='create') await api('/admin/customers',{method:'POST',body:JSON.stringify(values)})
      else if (modal==='reset'&&selected) await api(`/admin/customers/${selected.id}/reset-password`,{method:'POST'})
      else if (modal==='edit'&&selected) await api(`/admin/customers/${selected.id}`,{method:'PATCH',body:JSON.stringify({...values,is_active:values.is_active==='true'})})
      setModal(''); await load(); if(selected) await open(selected.id)
    } catch (error) { fail(formatApiError(error)) }
    finally { setSaving(false) }
  }

  async function deactivate() {
    if(!selected||!confirm(`Desativar ${selected.nome}?`)) return
    try { await api(`/admin/customers/${selected.id}`,{method:'DELETE'}); setSelected(null); await load() }
    catch(error) { fail(formatApiError(error)) }
  }

  async function link(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if(!selected) return
    const values = Object.fromEntries(new FormData(event.currentTarget)) as Record<string,string>
    try {
      setSaving(true)
      await api(`/admin/customers/${selected.id}/terminals`,{method:'POST',body:JSON.stringify({
        serial_number:values.serial_number.trim().toUpperCase(),
        model_id:values.model_id?Number(values.model_id):undefined,
        apelido:values.apelido.trim()||undefined,
        status:values.status||undefined,
      })})
      setModal('edit'); await open(selected.id, 'edit'); await load()
    } catch(error) { fail(formatApiError(error)) }
    finally { setSaving(false) }
  }

  async function unlink(terminal:Terminal) {
    if(!selected||!confirm(`Desvincular ${terminal.serial_number}?`)) return
    try { await api(`/admin/customers/${selected.id}/terminals/${terminal.id}`,{method:'DELETE'}); await open(selected.id, modal||'details'); await load() }
    catch(error) { fail(formatApiError(error)) }
  }

  return <div className="admin-panel customers-panel">
    <div className="panel-actions"><div><h2>Clientes</h2><p>Cadastros, acessos e máquinas vinculadas.</p></div><button className="primary" onClick={()=>setModal('create')}><Plus/>Novo cliente</button></div>
    <div className="machine-tools"><form onSubmit={event=>{event.preventDefault();void load()}}><Search/><input aria-label="Buscar clientes" value={search} onChange={event=>setSearch(event.target.value)} placeholder="Nome, login ou e-mail"/></form></div>
    <div className="admin-table"><table><thead><tr><th>Cliente</th><th>Login</th><th>Contato</th><th>Máquinas</th><th>Status</th><th/></tr></thead><tbody>
      {data.items.map(customer=><tr key={customer.id}><td><strong>{customer.nome}</strong></td><td>{customer.username||customer.id}</td><td>{customer.email||customer.telefone||'—'}</td><td>{customer.terminal_count}</td><td><span className={'pill '+(customer.is_active?'success':'muted')}>{customer.is_active?'Ativo':'Inativo'}</span></td><td><button onClick={()=>void open(customer.id,'details')}>Detalhes</button></td></tr>)}
      {!data.items.length&&<tr><td colSpan={6} className="machine-empty">Nenhum cliente encontrado.</td></tr>}
    </tbody></table></div>
    {modal&&<div className="admin-modal" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)setModal('')}}>
      {modal==='details'&&selected?<section className="machine-modal customer-modal customer-edit-modal customer-details-modal" role="dialog" aria-modal="true" aria-labelledby="customer-details-title">
        <button type="button" className="modal-x" aria-label="Fechar" onClick={()=>setModal('')}>×</button>
        <small className="modal-eyebrow">CADASTRO DO CLIENTE</small><h2 id="customer-details-title">{selected.nome}</h2>
        <div className="customer-details-contact"><span><strong>Login</strong>{selected.username}</span><span><strong>E-mail</strong>{selected.email||'Não informado'}</span><span><strong>Telefone</strong>{selected.telefone||'Não informado'}</span><span><strong>Status</strong><em className={'pill '+(selected.is_active?'success':'muted')}>{selected.is_active?'Ativo':'Inativo'}</em></span></div>
        <div className="customer-modal-toolbar"><button type="button" onClick={()=>setModal('edit')}>Editar dados</button><button type="button" onClick={()=>setModal('reset')}>Resetar senha</button><button type="button" onClick={()=>void deactivate()} disabled={!selected.is_active}>{selected.is_active?'Desativar':'Cliente inativo'}</button></div>
        <div className="customer-modal-machines"><div className="customer-machines-heading"><div><h3>Máquinas vinculadas</h3><p>{selected.terminals?.length||0} equipamento(s) cadastrado(s)</p></div><button className="primary" type="button" onClick={()=>setModal('link')}><Plus/>Vincular máquina</button></div><TerminalList terminals={selected.terminals||[]} unlink={unlink}/></div>
      </section>:modal==='link'?<form className="machine-modal customer-modal link-modal" onSubmit={link}>
        <button type="button" className="modal-x" aria-label="Fechar" onClick={()=>setModal('edit')}>×</button><small className="modal-eyebrow">MÁQUINAS DO CLIENTE</small><h2>Vincular máquina</h2><p className="modal-description">Informe o serial. Se ele já estiver cadastrado, o terminal será transferido para este cliente.</p>
        <label>Serial da máquina<input name="serial_number" required minLength={2} maxLength={120} pattern="[A-Za-z0-9-]+" placeholder="Ex.: A1B2C3" autoCapitalize="characters"/></label>
        <label>Apelido <span>(opcional)</span><input name="apelido" placeholder="Ex.: Caixa principal"/></label>
        <label>Modelo<select name="model_id" defaultValue=""><option value="">Selecione se for um novo terminal</option>{models.filter(model=>model.is_active).map(model=><option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
        <label>Status<select name="status" defaultValue=""><option value="">Manter status atual (ou Offline para novo)</option><option value="offline">Offline</option><option value="online">Online</option></select></label>
        <div className="modal-actions"><button type="button" className="secondary" onClick={()=>setModal('edit')}>Voltar</button><button className="primary" disabled={saving}>{saving?'Vinculando…':'Vincular máquina'}</button></div>
      </form>:<form className={`machine-modal customer-modal ${modal==='edit'?'customer-edit-modal':''}`} onSubmit={save}>
        <button type="button" className="modal-x" aria-label="Fechar" onClick={()=>setModal('')}>×</button>
        <small className="modal-eyebrow">GESTÃO DE CLIENTES</small><h2>{modal==='create'?'Novo cliente':modal==='reset'?'Resetar senha':'Editar cliente'}</h2>
        {modal==='reset'?<><p className="modal-description">A senha de {selected?.nome} voltará ao padrão e todas as sessões serão revogadas.</p><div className="modal-actions"><button type="button" className="secondary" onClick={()=>setModal('')}>Cancelar</button><button className="primary" disabled={saving}>{saving?'Processando…':'Confirmar reset'}</button></div></>:<>
          <p className="modal-description">Atualize os dados do cadastro e confira os equipamentos vinculados.</p>
          {modal==='create'&&<label>Identificador de login<input name="username" required minLength={3} placeholder="Ex.: loja123"/></label>}
          <label>Nome do cliente<input name="nome" required minLength={2} defaultValue={modal==='edit'?selected?.nome:''} placeholder="Nome da empresa"/></label>
          {modal==='edit'&&<label>Usuário de login<input value={selected?.username||selected?.id||''} readOnly/></label>}
          <div className="customer-form-grid"><label>E-mail<input name="email" type="email" defaultValue={modal==='edit'?selected?.email||'':''} placeholder="contato@empresa.com"/></label><label>Telefone<input name="telefone" defaultValue={modal==='edit'?selected?.telefone||'':''} placeholder="(00) 00000-0000"/></label></div>
          {modal==='edit'&&<>
            <label>Status do cadastro<select name="is_active" defaultValue={String(selected?.is_active??true)}><option value="true">Ativo</option><option value="false">Inativo</option></select></label>
            <div className="customer-modal-machines"><div className="customer-machines-heading"><div><h3>Máquinas vinculadas</h3><p>{selected?.terminals?.length||0} equipamento(s)</p></div></div><TerminalList terminals={selected?.terminals||[]} unlink={unlink}/></div>
            <div className="customer-modal-footer"><button type="button" className="secondary" onClick={()=>setModal('link')}><Plus/>Vincular máquina</button><div className="customer-edit-actions"><button type="button" className="secondary" onClick={()=>setModal('')}>Cancelar</button><button className="primary" disabled={saving}>{saving?'Salvando…':'Salvar alterações'}</button></div></div>
          </>}
          {modal==='create'&&<div className="modal-actions"><button type="button" className="secondary" onClick={()=>setModal('')}>Cancelar</button><button className="primary" disabled={saving}>{saving?'Criando…':'Criar cliente'}</button></div>}
        </>}
      </form>}
    </div>}
  </div>
}

function TerminalList({terminals,unlink}:{terminals:Terminal[];unlink:(terminal:Terminal)=>void}){
  if(!terminals.length)return <div className="customer-no-machines">Nenhuma máquina vinculada a este cliente.</div>
  return <div className="customer-terminal-list">{terminals.map(terminal=><article key={terminal.id}><div className="terminal-icon">{terminal.model_name?.slice(0,1)||'M'}</div><div className="terminal-info"><strong>{terminal.apelido||terminal.model_name}</strong><span>{terminal.model_name} · Serial {terminal.serial_number}</span></div><span className={'pill '+(terminal.status==='online'?'success':'muted')}>{terminal.status==='online'?'Online':'Offline'}</span><button type="button" aria-label={`Desvincular ${terminal.serial_number}`} onClick={()=>unlink(terminal)}><Unlink/>Desvincular</button></article>)}</div>
}
