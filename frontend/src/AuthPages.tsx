import { FormEvent, useEffect, useState } from 'react'
import { LogOut, ShieldCheck } from 'lucide-react'
import {api as request} from './api'

type User = {id:number;username:string;role:'admin'|'tecnico'|'cliente';display_name:string;customer_id?:string;must_change_password?:boolean}

export function LoginPage(){
  const [username,setUsername]=useState('')
  const [password,setPassword]=useState('')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function submit(event:FormEvent){
    event.preventDefault();setBusy(true);setError('')
    try{
      const user=await request<User>('/auth/login',{method:'POST',body:JSON.stringify({username,password})})
      window.location.assign(user.must_change_password?'/change-password':user.role==='admin'?'/admin':user.role==='tecnico'?'/tecnico/atendimento':'/')
    }catch(reason){setError(reason instanceof Error?reason.message:'Falha no login.')}
    finally{setBusy(false)}
  }
  return <main className="auth-page"><form className="login-card" onSubmit={submit}>
    <div className="auth-brand">getnet<span>_</span></div><small>AGENT WORKSPACE</small>
    <h1>Acesso da equipe</h1><p>Entre na área administrativa ou técnica.</p>
    <label>Usuário<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label>
    <label>Senha<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>
    {error&&<div role="alert" className="auth-error">{error}</div>}
    <button disabled={busy}>{busy?'Entrando…':'Entrar'}</button>
    <a href="/">Voltar ao atendimento público</a>
  </form></main>
}

export function ChangePasswordPage(){
 const [current,setCurrent]=useState(''),[next,setNext]=useState(''),[error,setError]=useState('')
 async function submit(event:FormEvent){event.preventDefault();setError('');try{const user=await request<User>('/auth/change-password',{method:'POST',body:JSON.stringify({current_password:current,new_password:next})});location.assign(user.role==='cliente'?'/':user.role==='admin'?'/admin':'/tecnico/atendimento')}catch(e){setError((e as Error).message)}}
 return <main className="auth-page"><form className="login-card" onSubmit={submit}><div className="auth-brand">getnet<span>_</span></div><small>SEGURANÇA</small><h1>Crie uma nova senha</h1><p>Antes de continuar, substitua a senha inicial.</p><label>Senha atual<input aria-label="Senha atual" type="password" value={current} onChange={e=>setCurrent(e.target.value)} required/></label><label>Nova senha<input aria-label="Nova senha" type="password" minLength={8} value={next} onChange={e=>setNext(e.target.value)} required/></label>{error&&<div role="alert" className="auth-error">{error}</div>}<button>Alterar senha</button></form></main>
}

export function ProtectedPlaceholder({area}:{area:'admin'|'tecnico'}){
  const [user,setUser]=useState<User|null>(null)
  const [message,setMessage]=useState('Validando sessão…')
  useEffect(()=>{
    Promise.all([request<User>('/auth/me'),request<{message:string}>(`/${area}`)])
      .then(([current,result])=>{setUser(current);setMessage(result.message)})
      .catch(()=>window.location.replace('/login'))
  },[area])
  async function logout(){try{await request('/auth/logout',{method:'POST'})}finally{window.location.assign('/login')}}
  return <main className="protected-page"><section className="placeholder-card">
    <ShieldCheck size={30}/><div className="auth-brand">getnet<span>_</span></div>
    <div className="area-tag">{area==='admin'?'ADMINISTRADOR':'TÉCNICO'}</div>
    <h1>{user?`Olá, ${user.display_name}`:'Área protegida'}</h1><p>{message}</p>
    <button onClick={logout}><LogOut size={16}/> Sair</button><a href="/">Atendimento público</a>
  </section></main>
}
