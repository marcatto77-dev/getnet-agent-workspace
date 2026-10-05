import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa somente contra Docker real da Fase 11')

test('portal cliente: login, chat, máquinas, conta e sair',async({page})=>{
 const suffix=String(Date.now()).slice(-7)
 const username=`cliente${suffix}`
 const terminalId=`terminal-${suffix}`
 const serial=`PORTAL-${suffix}`
 const bad:string[]=[]
 page.on('response',response=>{
  const expectedAnonymousMe=response.status()===401&&response.url().includes('/api/auth/me')
  if(response.status()>=400&&!response.url().includes('favicon')&&!expectedAnonymousMe)bad.push(`${response.status()} ${response.url()}`)
 })

 await page.goto('/login')
 await page.getByLabel('Usuário').fill('Admin')
 await page.getByLabel('Senha').fill('Admin')
 await page.getByRole('button',{name:'Entrar'}).click()
 await expect(page).toHaveURL(/\/admin/)
 const created=await page.evaluate(async username=>fetch('/api/admin/customers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,nome:'Cliente Portal',email:'portal@example.com',telefone:'11920002000'})}).then(r=>r.status),username)
 expect(created).toBe(201)
 const linked=await page.evaluate(async({username,terminalId,serial})=>fetch(`/api/admin/customers/${username}/terminals`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({terminal_id:terminalId,model_id:1,serial_number:serial,apelido:'Caixa principal',status:'online'})}).then(r=>r.status),{username,terminalId,serial})
 expect(linked).toBe(200)

 await page.getByRole('button',{name:/Sair/}).click()
 await page.goto('/')
 await expect(page.getByText('Entre para ser atendido')).toBeVisible()
 await page.getByLabel('Usuário').fill(username)
 await page.getByLabel('Senha').fill('123')
 await page.getByRole('button',{name:'Entrar'}).click()
 await page.getByLabel('Senha atual').fill('123')
 await page.getByLabel('Nova senha').fill(`Portal-Forte-${suffix}`)
 await page.getByRole('button',{name:'Alterar senha'}).click()

 await expect(page.getByText('Cliente Portal')).toBeVisible()
 await page.getByLabel('Sua mensagem').fill('ok')
 await page.getByLabel('Enviar mensagem').click()
 await expect(page.getByText('Por nada!')).toBeVisible()
 await page.screenshot({path:'../docs/evidence/fase11/atendimento.png',fullPage:true})

 await page.getByRole('link',{name:'Minhas máquinas'}).click()
 await expect(page.getByText('Caixa principal')).toBeVisible()
 await expect(page.getByText(`Série ••••${serial.slice(-4)}`)).toBeVisible()
 await page.screenshot({path:'../docs/evidence/fase11/minhas-maquinas.png',fullPage:true})
 await page.getByRole('link',{name:'Preciso de ajuda com esta máquina'}).click()
 await expect(page.getByText('Máquina selecionada')).toBeVisible()

 await page.getByRole('link',{name:'Minha conta'}).click()
 await expect(page.getByText('portal@example.com')).toBeVisible()
 await page.screenshot({path:'../docs/evidence/fase11/minha-conta.png',fullPage:true})
 await page.getByRole('button',{name:'Sair'}).click()
 await expect(page.getByText('Entre para ser atendido')).toBeVisible()
 await page.screenshot({path:'../docs/evidence/fase11/login-cliente.png',fullPage:true})
 expect(bad).toEqual([])
})
