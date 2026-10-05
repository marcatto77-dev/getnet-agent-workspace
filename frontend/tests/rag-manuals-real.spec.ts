import {mkdirSync} from 'node:fs'
import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa somente contra Docker real')

test('manuais oficiais aparecem no admin e cliente recebe resposta do RAG',async({browser})=>{
 const evidence='../docs/evidence/rag-manuais'
 mkdirSync(evidence,{recursive:true})
 const unexpected:string[]=[]
 const watch=(page:any)=>page.on('response',(response:any)=>{
  if(response.status()>=400&&!(response.status()===401&&response.url().includes('/api/auth/me'))&&!response.url().includes('favicon'))unexpected.push(`${response.status()} ${response.url()}`)
 })

 const adminContext=await browser.newContext(),admin=await adminContext.newPage();watch(admin)
 await admin.goto('/login')
 await admin.getByLabel('Usuário').fill('Admin')
 await admin.getByLabel('Senha').fill('Admin')
 await admin.getByRole('button',{name:'Entrar'}).click()
 await admin.getByRole('button',{name:'Base de conhecimento'}).click()
 await expect(admin.getByText('Manual oficial Get Smart — Getnet')).toBeVisible()
 await expect(admin.getByText('Manual oficial Get Clássica — Getnet')).toBeVisible()
 await expect(admin.getByText('Manual oficial Get Mini — Getnet')).toBeVisible()
 await expect(admin.getByText('Manual oficial Get Lite — Getnet')).toBeVisible()
 await expect(admin.locator('body')).not.toContainText('[object Object]')
 await admin.screenshot({path:`${evidence}/admin-rag.png`,fullPage:true})

 const customerContext=await browser.newContext(),customer=await customerContext.newPage();watch(customer)
 await customer.goto('/')
 await customer.getByLabel('Usuário').fill('cliente1988')
 await customer.getByLabel('Senha').fill('123')
 await customer.getByRole('button',{name:'Entrar'}).click()
 await customer.getByLabel('Sua mensagem').fill('Como conectar minha Get Smart ao Wi-Fi?')
 await customer.getByRole('button',{name:'Enviar mensagem'}).click()
 await expect(customer.locator('.public-message.ai').last()).toContainText(/Get Smart|Wi-Fi|rede/i,{timeout:30000})
 await expect(customer.locator('body')).not.toContainText('[object Object]')
 await customer.screenshot({path:`${evidence}/cliente-rag.png`,fullPage:true})
 await customer.getByLabel('Sua mensagem').fill('Qual todos os modelos de máquina a Getnet oferece para vender')
 await customer.getByRole('button',{name:'Enviar mensagem'}).click()
 await expect(customer.locator('.public-message.ai').last()).toContainText('Get Clássica [1], Get Lite [2], Get Mini [3], Get Smart [4]',{timeout:30000})
 await expect(customer.locator('.public-message.ai').last()).not.toContainText('Posso buscar no site')
 await expect(customer.getByRole('link',{name:/Manual oficial Get Clássica/})).toBeVisible()
 await customer.screenshot({path:`${evidence}/cliente-catalogo.png`,fullPage:true})
 expect(unexpected).toEqual([])
 await adminContext.close();await customerContext.close()
})
