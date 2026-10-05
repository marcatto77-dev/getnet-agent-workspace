import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa contra o Docker real')

async function login(page:any,username:string,password:string){
  await page.goto('/login')
  await page.getByLabel('Usuário').fill(username)
  await page.getByLabel('Senha').fill(password)
  await page.getByRole('button',{name:'Entrar'}).click()
}

test('mensagem do cliente aparece na conversa já aberta do técnico',async({browser})=>{
  const suffix=String(Date.now()).slice(-9)
  const customerName=`realtime${suffix}`
  const technicianName=`techrt${suffix}`
  const technicianPassword=`Tech-${suffix}!`
  const adminContext=await browser.newContext()
  const admin=await adminContext.newPage()
  await login(admin,'Admin','Admin')
  await expect(admin).toHaveURL(/\/admin/)
  const created=await admin.evaluate(async({customerName,technicianName,technicianPassword})=>{
    const customer=await fetch('/api/admin/customers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:customerName,nome:'Cliente Tempo Real'})})
    const technician=await fetch('/api/admin/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:technicianName,password:technicianPassword,role:'tecnico',display_name:'Técnico Tempo Real'})})
    return [customer.status,technician.status]
  },{customerName,technicianName,technicianPassword})
  expect(created).toEqual([201,201])

  const technicianContext=await browser.newContext()
  const technician=await technicianContext.newPage()
  await login(technician,technicianName,technicianPassword)
  await expect(technician).toHaveURL(/\/tecnico\/atendimento/)
  await expect(technician.getByText('Tempo real ativo')).toBeVisible()

  const customerContext=await browser.newContext()
  const customer=await customerContext.newPage()
  await login(customer,customerName,'123')
  await customer.getByLabel('Senha atual').fill('123')
  await customer.getByLabel('Nova senha').fill(`Cliente-${suffix}!`)
  await customer.getByRole('button',{name:'Alterar senha'}).click()
  await expect(customer.getByLabel('Sua mensagem')).toBeVisible()
  await customer.getByLabel('Sua mensagem').fill('Quero falar com um técnico, por favor.')
  await customer.getByLabel('Enviar mensagem').click()
  await expect(technician.getByRole('button',{name:/Fila/})).toContainText(/[1-9]/,{timeout:15000})
  await technician.getByRole('button',{name:'Assumir'}).first().click()
  await expect(technician.getByLabel('Mensagem ao cliente')).toBeVisible()
  await expect(technician.getByText('Tempo real ativo')).toBeVisible()

  const message=`Minha máquina não liga ${suffix}`
  await customer.getByLabel('Sua mensagem').fill(message)
  await customer.getByLabel('Enviar mensagem').click()
  await expect(technician.locator('.tech-messages article.customer p').filter({hasText:message})).toBeVisible({timeout:2500})
  for(let index=0;index<9;index++){
    const followUp=`Complemento ${index} da mensagem ${suffix}`
    await customer.getByLabel('Sua mensagem').fill(followUp)
    await customer.getByLabel('Enviar mensagem').click()
    await expect(technician.locator('.tech-messages article.customer p').filter({hasText:followUp})).toBeVisible({timeout:2500})
  }
  await expect.poll(()=>technician.locator('.tech-messages').evaluate(pane=>pane.scrollTop+pane.clientHeight>=pane.scrollHeight-4)).toBe(true)
  await expect(customer.getByText('Sua mensagem foi registrada e ficará disponível para o técnico responsável.')).toHaveCount(0)
  await expect(technician.getByText('Sua mensagem foi registrada e ficará disponível para o técnico responsável.')).toHaveCount(0)
  await expect(technician.locator('body')).not.toContainText('[object Object]')
  await technician.screenshot({path:'../docs/evidence/chat-realtime/tecnico-mensagem-cliente.png',fullPage:true})

  await technician.getByRole('button',{name:'Encerrar'}).click()
  await technician.getByLabel('Nota',{exact:true}).fill('Teste de atualização em tempo real')
  await technician.getByRole('button',{name:'Confirmar'}).click()
  await customerContext.close()
  await technicianContext.close()
  await adminContext.close()
})
