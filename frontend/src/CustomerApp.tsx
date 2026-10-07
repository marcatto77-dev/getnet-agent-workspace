import {FormEvent,useEffect,useRef,useState} from 'react'
import { BrandLogo } from './BrandLogo'
import {ArrowUp,ArrowUpRight,Bot,Sparkles,UserRound} from 'lucide-react'
import './public.css'
import './portal.css'
import {api} from './api'
import {isRoutineDeliveryNotice} from './chatMessages'
import {PresenceHeartbeat} from './PresenceHeartbeat'

type Source={id:number;title:string;url:string|null;kind:string;retrieved_at:string}
type Answer={request_id:string;conversation_id:string;answer:string;route:string;agents_used:string[];sources:Source[];steps:unknown[];status:string;latency_ms:number;event_id?:string|null;quick_replies?:string[]}
type Entry={id?:string;role:'customer'|'ai'|'technician'|'system';text:string;result?:Answer;error?:boolean;name?:string}
type Customer={id:number;username:string;role:string;display_name:string;must_change_password:boolean}
type Terminal={id:string;model:string;apelido?:string;serial_number:string;connection_status:string;updated_at?:string}
const suggestions=['Quando recebo o dinheiro das vendas de ontem?','Qual a diferença entre a Get Clássica e a Get Smart?','Minha maquininha não conecta à internet. O que faço?']
async function sendChat(message:string,terminal_id?:string,conversation_id?:string):Promise<Answer>{return api<Answer>('/chat',{method:'POST',body:JSON.stringify({message,terminal_id,conversation_id}),signal:AbortSignal.timeout(150000)})}

export default function App(){
 const [customer,setCustomer]=useState<Customer|null|undefined>(undefined)
 useEffect(()=>{api<Customer>('/auth/me').then(user=>{if(user.role!=='cliente'){setCustomer(null);return}if(user.must_change_password){location.assign('/change-password');return}setCustomer(user)}).catch(()=>setCustomer(null))},[])
 if(customer===undefined)return <div className="auth-page">Carregando…</div>
 if(!customer)return <CustomerLogin/>
 const path=location.pathname.replace(/\/$/,'')||'/'
 const logout=async()=>{await api('/auth/logout',{method:'POST'});setCustomer(null);history.replaceState({},'', '/');location.reload()}
 const page=path==='/minhas-maquinas'?<Machines customer={customer} logout={logout}/>:path==='/conta'?<Account customer={customer} logout={logout}/>:<Chat customer={customer} logout={logout}/>
 // Start the client's lease only after /auth/me has confirmed the current login.
 return <><PresenceHeartbeat key={customer.id}/>{page}</>
}

function CustomerLogin(){const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState('');async function submit(e:FormEvent){e.preventDefault();try{const user=await api<Customer>('/auth/login',{method:'POST',body:JSON.stringify({username,password})});if(user.role!=='cliente'){await api('/auth/logout',{method:'POST'});throw Error('Use o acesso interno para perfis da equipe.')}location.assign(user.must_change_password?'/change-password':'/')}catch(reason){setError((reason as Error).message)}}return <main className="auth-page"><form className="login-card" onSubmit={submit}><BrandLogo className="auth-brand"/><small>PORTAL DO CLIENTE</small><h1>Entre para ser atendido</h1><p>Acesse seu chat e suas maquininhas.</p><label>Usuário<input aria-label="Usuário" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>Senha<input aria-label="Senha" type="password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>{error&&<div role="alert" className="auth-error">{error}</div>}<button>Entrar</button><a href="/login">Acesso interno</a></form></main>}
function PortalHeader({customer,logout}:{customer:Customer;logout:()=>void}){
 const path=location.pathname.replace(/\/$/,'')||'/'
 const active=path==='/minhas-maquinas'?'/minhas-maquinas':path==='/conta'?'/conta':'/'
 return <header className="public-header"><BrandLogo className="public-brand" caption="ATENDIMENTO GETNET"/><nav className="customer-nav" aria-label="Navegação do cliente"><strong>{customer.display_name}</strong>{[{href:'/',label:'Atendimento'},{href:'/minhas-maquinas',label:'Minhas máquinas'},{href:'/conta',label:'Minha conta'}].map(item=><a key={item.href} href={item.href} aria-current={active===item.href?'page':undefined}>{item.label}</a>)}<button onClick={logout}>Sair</button></nav></header>
}
function Machines({customer,logout}:{customer:Customer;logout:()=>void}){const [items,setItems]=useState<Terminal[]>([]);useEffect(()=>{api<Terminal[]>('/customer/terminals').then(setItems)},[]);return <div className="public-shell"><PortalHeader customer={customer} logout={logout}/><main className="portal-page"><h1>Minhas máquinas</h1><div className="machine-cards">{items.map(t=><article key={t.id}><small>{t.apelido||'Minha maquininha'}</small><h2>{t.model}</h2><p>Série ••••{t.serial_number.slice(-4)}</p><span className={'terminal-status '+t.connection_status}>{t.connection_status}</span><p>Última conexão: {t.updated_at?new Date(t.updated_at).toLocaleString('pt-BR'):'não informada'}</p><a href={`/?terminal_id=${encodeURIComponent(t.id)}`}>Preciso de ajuda com esta máquina</a></article>)}</div></main><PublicFooter/></div>}
function Account({customer,logout}:{customer:Customer;logout:()=>void}){const [profile,setProfile]=useState<any>(null),[current,setCurrent]=useState(''),[next,setNext]=useState(''),[notice,setNotice]=useState('');useEffect(()=>{api('/customer/profile').then(setProfile)},[]);async function change(e:FormEvent){e.preventDefault();try{await api('/auth/change-password',{method:'POST',body:JSON.stringify({current_password:current,new_password:next})});setNotice('Senha alterada com sucesso.');setCurrent('');setNext('')}catch(reason){setNotice((reason as Error).message)}}return <div className="public-shell"><PortalHeader customer={customer} logout={logout}/><main className="portal-page account-page"><h1>Minha conta</h1><section><h2>{profile?.nome||customer.display_name}</h2><p>{profile?.email||'E-mail não cadastrado'}</p><p>{profile?.telefone||'Telefone não cadastrado'}</p></section><form onSubmit={change}><h2>Trocar senha</h2><label>Senha atual<input type="password" value={current} onChange={e=>setCurrent(e.target.value)} required/></label><label>Nova senha<input type="password" minLength={8} value={next} onChange={e=>setNext(e.target.value)} required/></label><button>Alterar senha</button>{notice&&<p>{notice}</p>}</form></main><PublicFooter/></div>}

function Chat({customer,logout}:{customer:Customer;logout:()=>void}){
 const [entries,setEntries]=useState<Entry[]>([]),[input,setInput]=useState(''),[busy,setBusy]=useState(false),[conversationId,setConversationId]=useState(''),[chatStatus,setChatStatus]=useState('new'),[loading,setLoading]=useState(true),[connection,setConnection]=useState<'idle'|'online'|'polling'>('idle')
 const terminalId=new URLSearchParams(location.search).get('terminal_id')||undefined
 const end=useRef<HTMLDivElement>(null),seen=useRef(new Set<string>())
 useEffect(()=>{let active=true;api<{conversation_id:string;status:string;messages:{id:string;sender_type:Entry['role'];content:string}[]} | null>('/chat/current').then(data=>{if(!active||!data)return;setConversationId(data.conversation_id);setChatStatus(data.status);data.messages.forEach(m=>seen.current.add(m.id));setEntries(data.messages.map(m=>({id:m.id,role:m.sender_type,text:m.content}))) }).catch(()=>undefined).finally(()=>{if(active)setLoading(false)});return()=>{active=false}},[])
 useEffect(()=>{end.current?.scrollIntoView({behavior:'smooth'})},[entries,busy])
 useEffect(()=>{if(!conversationId)return;let stopped=false,retry:number|undefined,poll:number|undefined;const add=(event:any)=>{if(event.event_id&&seen.current.has(event.event_id))return;if(event.event_id)seen.current.add(event.event_id);if(event.type==='handoff.closed')setChatStatus('closed');if(['handoff.claimed','handoff.pulled','handoff.transferred'].includes(event.type))setChatStatus('with_technician');if(event.type==='queue.position')setChatStatus('waiting');if(event.type==='message'&&event.message){const m=event.message;if(m.id&&seen.current.has(m.id))return;if(m.id)seen.current.add(m.id);setEntries(v=>[...v,{id:m.id,role:m.sender_type,text:m.content,name:m.sender_name}])}if(event.type==='connection.ready'&&event.status==='waiting')setChatStatus('waiting');if(event.type==='connection.ready'&&event.status==='assigned')setChatStatus('with_technician');if(event.type==='queue.position')setEntries(v=>[...v,{role:'system',text:`Você está na fila, posição ${event.position}.`}]);if(event.type==='technician.joined')setEntries(v=>[...v,{role:'system',text:`Técnico ${event.technician_name} entrou na conversa.`}]);if(['handoff.claimed','handoff.pulled','handoff.transferred','handoff.closed'].includes(event.type)&&event.message){const id=event.message_id;if(id&&seen.current.has(id))return;if(id)seen.current.add(id);setEntries(v=>[...v,{id,role:'system',text:event.message}])}};const startPolling=()=>{if(poll)return;setConnection('polling');poll=window.setInterval(async()=>{try{const data=await api<{status:string;messages:any[]}>(`/chat/conversations/${conversationId}/messages`);setChatStatus(data.status);for(const message of data.messages)add({type:'message',message})}catch{}},3000)};const connect=()=>{if(stopped)return;const protocol=location.protocol==='https:'?'wss':'ws';const ws=new WebSocket(`${protocol}://${location.host}/ws/chat/${conversationId}`);ws.onopen=()=>{setConnection('online');if(poll){clearInterval(poll);poll=undefined}};ws.onmessage=e=>add(JSON.parse(e.data));ws.onclose=()=>{if(stopped)return;startPolling();retry=window.setTimeout(connect,2000)}};connect();return()=>{stopped=true;if(retry)clearTimeout(retry);if(poll)clearInterval(poll)}},[conversationId])
 async function send(message:string){
  if(!message.trim()||busy||loading)return
  const continuing=chatStatus!=='closed'&&conversationId?conversationId:undefined
  if(chatStatus==='closed'){setEntries([]);setConversationId('');seen.current.clear()}
  setInput('');setBusy(true);setEntries(value=>[...value,{role:'customer',text:message.trim()}])
  try{
   const result=await sendChat(message.trim(),terminalId,continuing)
   setConversationId(result.conversation_id)
   setChatStatus(result.status==='waiting'||result.status==='with_technician'?result.status:'ai')
   const eventAlreadySeen=Boolean(result.event_id&&seen.current.has(result.event_id))
   if(result.event_id)seen.current.add(result.event_id)
   if(result.answer.trim())setEntries(value=>{const cleaned=eventAlreadySeen&&result.status==='waiting'?value.filter(entry=>!(entry.role==='system'&&entry.text.startsWith('Você está na fila'))):value;return [...cleaned,{role:result.status==='waiting'||result.status==='with_technician'?'system':'ai',text:result.answer,result}]})
  }catch(error){setEntries(value=>[...value,{role:'ai',text:error instanceof Error?error.message:'Falha de conexão.',error:true}])}
  finally{setBusy(false)}
 }
 async function endConversation(){
  if(!conversationId||busy||!confirm('Encerrar este atendimento?'))return
  setBusy(true)
  try{
   const result=await api<{message_id?:string}>(`/chat/conversations/${conversationId}/close`,{method:'POST'})
   const alreadyShown=Boolean(result.message_id&&seen.current.has(result.message_id))
   if(result.message_id)seen.current.add(result.message_id)
   setChatStatus('closed')
   if(!alreadyShown)setEntries(value=>[...value,{id:result.message_id,role:'system',text:'Você encerrou este atendimento.'}])
  }catch(error){setEntries(value=>[...value,{role:'system',text:error instanceof Error?error.message:'Não foi possível encerrar.',error:true}])}
  finally{setBusy(false)}
 }
 function newConversation(){setEntries([]);setConversationId('');setChatStatus('new');seen.current.clear();setConnection('idle')}
 return <div className="public-shell customer-chat-shell"><PortalHeader customer={customer} logout={logout}/><main className="public-chat"><section className="chat-card"><div className="chat-title"><div className="chat-identity"><div className="chat-assistant-icon" aria-hidden="true"><Bot/></div><div className="chat-heading"><strong>Assistente Getnet</strong><small><span className="online-dot"/>{connection==='polling'?'Reconectando ao atendimento':terminalId?'Ajuda com sua máquina':'Estamos aqui para ajudar'}</small></div></div><div className="chat-actions">{conversationId&&chatStatus!=='closed'&&<button type="button" onClick={endConversation} disabled={busy||loading}>Encerrar conversa</button>}{chatStatus==='closed'&&<button type="button" onClick={newConversation}>Nova conversa</button>}</div></div><div className={'public-messages '+(!entries.length?'empty':'')}>{loading?<div className="public-thinking">Carregando atendimento…</div>:!entries.length?<Welcome busy={busy} send={send}/>:entries.filter(entry=>!isRoutineDeliveryNotice(entry.role,entry.text)).map((entry,index)=><Message entry={entry} send={send} key={entry.id||index}/>)}{busy&&<div className="public-thinking"><Bot/><span>Consultando as informações…</span></div>}<div ref={end}/></div><form className="public-composer" onSubmit={event=>{event.preventDefault();send(input)}}><textarea aria-label="Sua mensagem" placeholder="Digite sua mensagem…" rows={2} maxLength={2000} value={input} disabled={busy||loading} onChange={event=>setInput(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send(input)}}}/><button type="button" onClick={()=>send(input)} aria-label="Enviar mensagem" disabled={busy||loading||!input.trim()}><ArrowUp/></button></form><div className="ai-note">Privacidade: não envie CPF, cartão ou outros dados sensíveis. As mensagens seguem a política de retenção do serviço.</div></section></main><PublicFooter/></div>
}
function Welcome({busy,send}:{busy:boolean;send:(message:string)=>void}){return <div className="public-welcome"><div className="welcome-mark"><Sparkles/></div><div className="public-kicker">BEM-VINDO</div><h1>Como podemos ajudar?</h1><p>Tire dúvidas sobre produtos, recebimentos ou sua maquininha.</p><div className="public-suggestions">{suggestions.map(item=><button type="button" key={item} onClick={()=>send(item)} disabled={busy}>{item}<ArrowUpRight size={15}/></button>)}</div></div>}
function sourceLabel(source:Source){if(source.kind==='customer')return source.title;if(source.kind==='manual')return 'Base interna · '+source.title.replace(/ \(conteúdo manual\)$/,'');if(source.kind==='rag')return 'Base interna · '+source.title;if(source.kind==='web'&&source.url&&new URL(source.url).hostname.endsWith('getnet.com.br'))return 'Busca online · Site Getnet';return 'Consulta externa · '+source.title}
function Message({entry,send}:{entry:Entry;send:(message:string)=>void}){return <article className={'public-message '+entry.role+(entry.error?' error':'')}><div className="public-avatar">{entry.role==='customer'?<UserRound/>:<Bot/>}</div><div><strong>{entry.role==='customer'?'Você':entry.role==='technician'?(entry.name||'Técnico Getnet'):entry.role==='system'?'Atualização do atendimento':'Assistente Getnet'}</strong><p style={{whiteSpace:'pre-wrap'}}>{entry.text}</p>{entry.result?.quick_replies?.length?<div className="public-sources">{entry.result.quick_replies.map(value=><button key={value} onClick={()=>send(value)}>{value}</button>)}</div>:null}{entry.result?.sources.length?<div className="public-sources"><small>Fontes</small>{entry.result.sources.map(source=>source.url?<a key={source.id} href={source.url} target="_blank" rel="noreferrer">{sourceLabel(source)}<ArrowUpRight size={12}/></a>:<span key={source.id}>{sourceLabel(source)}</span>)}</div>:null}</div></article>}
function PublicFooter(){return <footer className="public-footer"><span>Ambiente demonstrativo · Dados fictícios</span><a href="/login">Acesso interno</a></footer>}
