import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './CustomerApp'
import { ChangePasswordPage, LoginPage } from './AuthPages'
import { TechnicianWorkspace } from './TechnicianWorkspace'
import { AdminWorkspaceV2 } from './AdminWorkspaceV2'
import './style.css'
import { PresenceHeartbeat } from './PresenceHeartbeat'
import './admin-readability.css'
import './portal-readability.css'

const path=window.location.pathname.replace(/\/$/,'')||'/'
const page=path==='/login'?<LoginPage/>:path==='/change-password'?<ChangePasswordPage/>:path==='/admin'?<AdminWorkspaceV2/>:path==='/tecnico'||path==='/tecnico/atendimento'?<TechnicianWorkspace/>:<App/>
const internalArea=path==='/admin'||path==='/tecnico'||path==='/tecnico/atendimento'
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{internalArea&&<PresenceHeartbeat/>}{page}</React.StrictMode>)
