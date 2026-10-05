import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa contra o Docker real da Fase 16')

async function login(page:any,username:string,password:string){
  await page.goto('/login')
  await page.getByLabel('Usuário').fill(username)
  await page.getByLabel('Senha').fill(password)
  await page.getByRole('button',{name:'Entrar'}).click()
}

test('tela de atendimento técnico e isolamento do cliente',async({browser})=>{
  const technicianContext=await browser.newContext(),technician=await technicianContext.newPage()
  await login(technician,'Tecnico','Tecnico')
  await expect(technician).toHaveURL(/\/tecnico\/atendimento/)
  await expect(technician.getByRole('heading',{name:'Atendimentos aguardando um técnico'})).toBeVisible()
  await technician.evaluate(async()=>{
    const payload=await fetch('/api/tech/handoffs/mine').then(r=>r.json())
    const mine=Array.isArray(payload)?payload:(payload.items||[])
    for(const item of mine){
      await fetch(`/api/tech/handoffs/${item.id}/close`,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({resolution_note:'Limpeza controlada do cenário E2E',close_category:'outro'})
      })
    }
  })
  await technician.reload()
  await technician.getByLabel('Disponibilidade').selectOption('online')
  await expect(technician.locator('body')).not.toContainText('[object Object]')

  const customerContext=await browser.newContext(),customer=await customerContext.newPage()
  await login(customer,'cliente1988','123')
  await expect(customer).toHaveURL(/\/$/)
  await customer.getByLabel('Sua mensagem').fill('Quero falar com um técnico, por favor.')
  await customer.getByLabel('Enviar mensagem').click()
  await expect(customer.locator('.public-message.system')).toContainText(/direcionando|fila|transferindo/i,{timeout:150000})
  await expect(technician.getByRole('button',{name:/Fila/})).toContainText(/[1-9]/,{timeout:15000})
  await technician.getByRole('button',{name:'Ver chat'}).first().click()
  await expect(technician.locator('.preview-modal')).toBeVisible()
  await expect(technician.locator('.preview-modal').getByText(/Quero falar com um técnico/i).first()).toBeVisible()
  await technician.getByRole('button',{name:'Assumir atendimento'}).click()
  await expect(technician.getByLabel('Mensagem ao cliente')).toBeVisible()
  await expect(customer.locator('.public-message.system').last()).toContainText(/assumiu seu atendimento/i,{timeout:15000})
  await technician.evaluate(()=>window.scrollTo(0,0))
  await technician.screenshot({path:'../docs/evidence/fase16/atendimento-assumido.png',fullPage:true})
  await customer.goto('/tecnico/atendimento')
  await expect(customer).toHaveURL(/\/$/)
  await expect(customer.locator('body')).not.toContainText('Central de Atendimento')
  await expect(customer.locator('body')).not.toContainText('[object Object]')
  await customer.screenshot({path:'../docs/evidence/fase16/cliente-isolado.png',fullPage:true})
  await technicianContext.close();await customerContext.close()
})

test('dois técnicos: assumir, puxar, nota interna e encerrar',async({browser})=>{
  const adminContext=await browser.newContext(),admin=await adminContext.newPage()
  await login(admin,'Admin','Admin');await expect(admin).toHaveURL(/\/admin/)
  await admin.evaluate(async()=>{
    const users=await fetch('/api/admin/users').then(r=>r.json())
    const existing=users.find((user:any)=>user.username.toLowerCase()==='tecnico2')
    if(existing)await fetch(`/api/admin/users/${existing.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:'Tecnico2!',is_active:true})})
    else await fetch('/api/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'Tecnico2',password:'Tecnico2!',role:'tecnico',display_name:'Tecnico2'})})
  })
  await adminContext.close()
  const firstContext=await browser.newContext(),secondContext=await browser.newContext(),customerContext=await browser.newContext()
  const first=await firstContext.newPage(),second=await secondContext.newPage(),customer=await customerContext.newPage()
  await login(first,'Tecnico','Tecnico');await login(second,'Tecnico2','Tecnico2!')
  await expect(first).toHaveURL(/\/tecnico\/atendimento/);await expect(second).toHaveURL(/\/tecnico\/atendimento/)
  await first.evaluate(async()=>{const mine=await fetch('/api/tech/handoffs/mine').then(r=>r.json());for(const item of mine)await fetch(`/api/tech/handoffs/${item.id}/close`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resolution_note:'Limpeza E2E',close_category:'outro'})})})
  await second.evaluate(async()=>{const mine=await fetch('/api/tech/handoffs/mine').then(r=>r.json());for(const item of mine)await fetch(`/api/tech/handoffs/${item.id}/close`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resolution_note:'Limpeza E2E',close_category:'outro'})})})
  await first.reload();await first.getByLabel('Disponibilidade').selectOption('online');await second.getByLabel('Disponibilidade').selectOption('online')
  await login(customer,'cliente2026','123');await customer.getByLabel('Sua mensagem').fill('Quero falar com um técnico agora.');await customer.getByLabel('Enviar mensagem').click()
  await expect(first.getByRole('button',{name:/Fila/})).toContainText(/[1-9]/,{timeout:15000});await expect(second.getByRole('button',{name:/Fila/})).toContainText(/[1-9]/,{timeout:15000})
  await first.getByRole('button',{name:'Assumir'}).click();await expect(first.getByLabel('Mensagem ao cliente')).toBeVisible()
  await second.getByRole('button',{name:/Com outros técnicos/}).click();await second.getByRole('button',{name:/Mercado Horizonte/}).click();await second.getByRole('button',{name:'Puxar atendimento'}).click();await second.getByLabel(/Motivo/).fill('Redistribuição necessária para validar o fluxo');await second.getByRole('button',{name:'Confirmar'}).click()
  await expect(second.getByLabel('Mensagem ao cliente')).toBeVisible();await expect(first.getByRole('alert')).toContainText(/puxado por outro técnico/i,{timeout:15000})
  await second.getByLabel('Nota interna').fill('Nota reservada da equipe');await second.getByRole('button',{name:'Salvar nota'}).click();await expect(second.locator('.tech-messages p').filter({hasText:'Nota reservada da equipe'}).first()).toBeVisible();await expect(customer.locator('body')).not.toContainText('Nota reservada da equipe')
  await second.getByRole('button',{name:'Encerrar'}).click();await second.getByLabel('Nota',{exact:true}).fill('Resolvido no atendimento técnico');await second.getByRole('button',{name:'Confirmar'}).click();await expect(customer.locator('.public-message.system').last()).toContainText(/encerrado/i,{timeout:15000})
  await second.screenshot({path:'../docs/evidence/fase16/dois-tecnicos.png',fullPage:true})
  await firstContext.close();await secondContext.close();await customerContext.close()
})
