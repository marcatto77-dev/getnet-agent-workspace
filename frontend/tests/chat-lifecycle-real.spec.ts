import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa contra o Docker real com cliente de demonstração')

test('cada visita à IA abre outro histórico e o cliente pode encerrar',async({page})=>{
 const errors:string[]=[]
 page.on('response',response=>{if(response.status()>=500)errors.push(`${response.status()} ${response.url()}`)})
 await page.goto('/')
 await page.getByLabel('Usuário').fill(process.env.E2E_CUSTOMER_USER||'cliente1988')
 await page.getByLabel('Senha').fill(process.env.E2E_CUSTOMER_PASSWORD||'123')
 await page.getByRole('button',{name:'Entrar'}).click()
 await expect(page.getByLabel('Sua mensagem')).toBeVisible()
 const send=async()=>{
  await page.getByLabel('Sua mensagem').fill('ok')
  const response=page.waitForResponse(item=>item.url().endsWith('/api/chat')&&item.request().method()==='POST')
  await page.getByRole('button',{name:'Enviar mensagem'}).click()
  const result=await response
  expect(result.status()).toBe(200)
  return (await result.json()).conversation_id as string
 }
 const first=await send()
 await page.reload()
 await expect(page.getByText('Como podemos ajudar?')).toBeVisible()
 const second=await send()
 expect(second).not.toBe(first)
 page.once('dialog',dialog=>dialog.accept())
 await page.getByRole('button',{name:'Encerrar conversa'}).click()
 await expect(page.getByText('Você encerrou este atendimento.')).toHaveCount(1)
 await page.reload()
 await expect(page.getByText('Como podemos ajudar?')).toBeVisible()
 await page.screenshot({path:'../docs/evidence/chat-lifecycle/cliente-nova-conversa.png',fullPage:true})
 expect(errors).toEqual([])
})

test('fila é restaurada ao cliente e desistência chega aos encerrados do técnico',async({browser})=>{
 test.setTimeout(180_000)
 const clientContext=await browser.newContext(),customer=await clientContext.newPage()
 await customer.goto('/')
 await customer.getByLabel('Usuário').fill(process.env.E2E_CUSTOMER_USER||'cliente1988')
 await customer.getByLabel('Senha').fill(process.env.E2E_CUSTOMER_PASSWORD||'123')
 await customer.getByRole('button',{name:'Entrar'}).click()
 await expect(customer.getByLabel('Sua mensagem')).toBeVisible()
 await customer.getByLabel('Sua mensagem').fill('Quero falar com um técnico')
 const reply=customer.waitForResponse(response=>response.url().endsWith('/api/chat')&&response.request().method()==='POST',{timeout:150_000})
 await customer.getByRole('button',{name:'Enviar mensagem'}).click()
 const result=await reply
 expect(result.status()).toBe(200)
 const conversation=(await result.json()).conversation_id as string
 await customer.reload()
 await expect(customer.getByText('Quero falar com um técnico',{exact:true})).toBeVisible()
 await expect(customer.getByRole('button',{name:'Encerrar conversa'})).toBeVisible()
 customer.once('dialog',dialog=>dialog.accept())
 await customer.getByRole('button',{name:'Encerrar conversa'}).click()
 await expect(customer.getByText('Você encerrou este atendimento.')).toHaveCount(1)
 await customer.reload()
 await expect(customer.getByText('Como podemos ajudar?')).toBeVisible()
 await customer.screenshot({path:'../docs/evidence/chat-lifecycle/cliente-apos-desistencia.png',fullPage:true})

 const techContext=await browser.newContext(),technician=await techContext.newPage()
 await technician.goto('/login')
 await technician.getByLabel('Usuário').fill(process.env.E2E_TECH_USER||'Tecnico')
 await technician.getByLabel('Senha').fill(process.env.E2E_TECH_PASSWORD||'Tecnico')
 await technician.getByRole('button',{name:'Entrar'}).click()
 await expect(technician).toHaveURL(/\/tecnico\/atendimento/)
 await technician.getByRole('button',{name:/Encerrados/}).click()
 const closed=await technician.evaluate(async()=>fetch('/api/tech/handoffs/closed?page_size=100').then(response=>response.json()))
 expect(closed.items.some((item:{conversation_id:string})=>item.conversation_id===conversation)).toBe(true)
 const index=closed.items.findIndex((item:{conversation_id:string})=>item.conversation_id===conversation)
 await technician.locator('.center-list button').nth(index).click()
 await expect(technician.locator('.center-main').getByText('Quero falar com um técnico',{exact:true})).toBeVisible()
 await expect(technician.locator('.center-main').getByText('ok',{exact:true})).toHaveCount(0)
 await technician.screenshot({path:'../docs/evidence/chat-lifecycle/tecnico-encerrados.png',fullPage:true})
 await clientContext.close();await techContext.close()
})
