import { FormEvent, useEffect, useState } from 'react'
import { FileText, Globe2, Plus, RefreshCw, Search } from 'lucide-react'
import './knowledge.css'
import { api, queryString } from './api'

type Document = {
  id: number
  source: string
  title: string
  content: string
  origin: 'crawler' | 'manual'
  status_embedding: string
  updated_at: string
  chunk_count: number
  review_required: boolean
  poisoning_flags: string[]
  review_decision: 'approved' | 'rejected' | null
  review_reason: string | null
}
type Page = { items: Document[]; total: number; page: number; page_size: number }
type Modal = 'manual' | 'url' | 'edit' | 'review' | ''

export function KnowledgePanel({ fail }: { fail: (message: string) => void }) {
  const [data, setData] = useState<Page>({ items: [], total: 0, page: 1, page_size: 10 })
  const [search, setSearch] = useState('')
  const [origin, setOrigin] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState<Modal>('')
  const [editing, setEditing] = useState<Document | null>(null)
  const [reason, setReason] = useState('')
  const [job, setJob] = useState<{ status: string; processed: number; total: number; error?: string } | null>(null)
  const load = () => api<Page>(`/admin/rag/documents?${queryString({ search, origin, status, page, page_size: 10 })}`)
    .then(setData).catch((error: Error) => fail(error.message))

  useEffect(() => { void load() }, [origin, status, page])
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.status)) return
    const timer = setInterval(() => {
      api<typeof job>('/admin/rag/reindex').then((result) => {
        setJob(result)
        if (result?.status === 'completed') void load()
      }).catch((error: Error) => fail(error.message))
    }, 700)
    return () => clearInterval(timer)
  }, [job])

  const closeModal = () => { setModal(''); setEditing(null); setReason('') }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    try {
      if (modal === 'url') {
        await api('/admin/rag/ingest-url', { method: 'POST', body: JSON.stringify({ url: values.url }) })
      } else if (modal === 'edit' && editing) {
        await api(`/admin/rag/documents/${editing.id}`, { method: 'PUT', body: JSON.stringify({ title: values.title, content: values.content }) })
      } else {
        await api('/admin/rag/documents', { method: 'POST', body: JSON.stringify({ title: values.title, content: values.content }) })
      }
      closeModal()
      void load()
    } catch (error) { fail((error as Error).message) }
  }
  const review = async (decision: 'approved' | 'rejected') => {
    if (!editing || reason.trim().length < 10) { fail('Informe um motivo de pelo menos 10 caracteres.'); return }
    try {
      await api(`/admin/rag/documents/${editing.id}/review`, {
        method: 'POST', body: JSON.stringify({ decision, reason: reason.trim() }),
      })
      closeModal()
      void load()
    } catch (error) { fail((error as Error).message) }
  }
  const remove = async (document: Document) => {
    if (!confirm(`Remover “${document.title}” e todos os vetores?`)) return
    try {
      await api(`/admin/rag/documents/${document.id}`, { method: 'DELETE' })
      void load()
    } catch (error) { fail((error as Error).message) }
  }
  const reindex = async () => {
    try { setJob(await api('/admin/rag/reindex', { method: 'POST' })) }
    catch (error) { fail((error as Error).message) }
  }
  const progress = job?.total ? Math.round(job.processed / job.total * 100) : 0

  return <div className="admin-panel knowledge-panel">
    <div className="panel-actions">
      <div><h2>Documentos e embeddings</h2><p>Conteúdo atual usado pelo Knowledge Agent. Documentos suspeitos exigem revisão.</p></div>
      <div className="knowledge-actions">
        <button onClick={reindex} disabled={!!job && ['queued', 'running'].includes(job.status)}><RefreshCw />Reindexar aprovados</button>
        <button onClick={() => setModal('url')}><Globe2 />Adicionar URL</button>
        <button className="primary" onClick={() => setModal('manual')}><Plus />Adicionar texto</button>
      </div>
    </div>
    {job && <div className={'reindex-status ' + job.status}>
      <div><strong>Reindexação: {job.status}</strong><span>{job.processed || 0} de {job.total || 0} documentos aprovados</span></div>
      <progress max="100" value={progress} />
      {job.error && <small>{job.error}</small>}
    </div>}
    <div className="knowledge-filters">
      <form onSubmit={event => { event.preventDefault(); setPage(1); void load() }}>
        <Search /><input aria-label="Buscar documentos" value={search} onChange={event => setSearch(event.target.value)} placeholder="Buscar por título, fonte ou conteúdo" />
      </form>
      <select aria-label="Filtrar origem" value={origin} onChange={event => { setOrigin(event.target.value); setPage(1) }}>
        <option value="">Todas as origens</option><option value="crawler">Crawler</option><option value="manual">Manual</option>
      </select>
      <select aria-label="Filtrar embedding" value={status} onChange={event => { setStatus(event.target.value); setPage(1) }}>
        <option value="">Todos os status</option><option value="pending">Pendente de revisão</option>
        <option value="indexed">Indexado</option><option value="failed">Falhou / rejeitado</option>
      </select>
    </div>
    <div className="rag-table"><table>
      <thead><tr><th>Documento</th><th>Origem</th><th>Prévia</th><th>Atualizado</th><th>Embedding</th><th>Ações</th></tr></thead>
      <tbody>{data.items.map(document => <tr key={document.id}>
        <td><div className="document-title"><FileText /><span><strong>{document.title}</strong><small>{document.source}</small></span></div></td>
        <td><span className="pill">{document.origin}</span></td>
        <td><p>{document.content.slice(0, 130)}{document.content.length > 130 ? '…' : ''}</p><small>{document.chunk_count} trechos</small></td>
        <td>{new Date(document.updated_at).toLocaleDateString('pt-BR')}</td>
        <td><span className={'pill ' + (document.status_embedding === 'indexed' && !document.review_required ? 'success' : '')}>
          {document.review_required ? (document.review_decision === 'rejected' ? 'Rejeitado' : 'Revisão pendente') : document.status_embedding}
        </span></td>
        <td>{document.review_required && document.status_embedding === 'pending' && <button onClick={() => { setEditing(document); setModal('review') }}>Revisar</button>}
          <button onClick={() => { setEditing(document); setModal('edit') }}>Editar</button>
          <button onClick={() => remove(document)}>Remover</button></td>
      </tr>)}</tbody>
    </table></div>
    <div className="pagination"><span>{data.total} documentos</span><button disabled={page === 1} onClick={() => setPage(page - 1)}>Anterior</button><button disabled={page * 10 >= data.total} onClick={() => setPage(page + 1)}>Próxima</button></div>
    {modal && <div className="admin-modal">
      {modal === 'review' && editing ? <section className="review-dialog" role="dialog" aria-modal="true" aria-label="Revisar documento">
        <button type="button" className="modal-x" onClick={closeModal} aria-label="Fechar">×</button>
        <h2>Revisar documento</h2><p><strong>{editing.title}</strong></p>
        <p>Origem: {editing.source}</p>
        <p>Sinais detectados: {editing.poisoning_flags.length ? editing.poisoning_flags.join(', ') : 'Revisão anterior pendente'}</p>
        <label>Conteúdo completo <textarea readOnly value={editing.content} rows={12} /></label>
        <label>Motivo da decisão <textarea value={reason} onChange={event => setReason(event.target.value)} minLength={10} maxLength={1000} rows={3} /></label>
        <div className="review-actions">
          <button type="button" onClick={() => review('rejected')}>Rejeitar e manter fora do RAG</button>
          <button type="button" className="primary" onClick={() => review('approved')}>Aprovar e indexar</button>
        </div>
      </section> : <form onSubmit={submit}>
        <button type="button" className="modal-x" onClick={closeModal} aria-label="Fechar">×</button>
        <h2>{modal === 'url' ? 'Ingerir URL' : modal === 'edit' ? 'Editar documento' : 'Adicionar texto manual'}</h2>
        {modal === 'url' ? <label>URL oficial<input name="url" type="url" placeholder="https://site.getnet.com.br/..." required /></label> : <>
          <label>Título<input name="title" defaultValue={editing?.title} required minLength={2} /></label>
          <label>Conteúdo<textarea name="content" defaultValue={editing?.content} required minLength={20} rows={10} /></label>
          <small>Conteúdo suspeito fica pendente até uma aprovação explícita.</small>
        </>}
        <button className="primary">{modal === 'url' ? 'Ingerir URL' : modal === 'edit' ? 'Salvar e recalcular' : 'Salvar documento'}</button>
      </form>}
    </div>}
  </div>
}
