import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './CustomerApp'
import { ChangePasswordPage, LoginPage } from './AuthPages'
import { TechnicianWorkspace } from './TechnicianWorkspace'
import { AdminWorkspaceV2 } from './AdminWorkspaceV2'
import './style.css'

const path=window.location.pathname.replace(/\/$/,'')||'/'
const page=path==='/login'?<LoginPage/>:path==='/change-password'?<ChangePasswordPage/>:path==='/admin'?<AdminWorkspaceV2/>:path==='/tecnico'||path==='/tecnico/atendimento'?<TechnicianWorkspace/>:<App/>
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{page}</React.StrictMode>)
