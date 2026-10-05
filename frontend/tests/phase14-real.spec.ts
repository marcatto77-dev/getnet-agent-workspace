import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa somente contra Docker real da Fase 14')

test('fase 14: cliente, técnico e admin carregam sem regressão visual',async({browser})=>{
 const unexpected:string[]=[]
 const watch=(page:any)=>page.on('response',(response:any)=>{
  if(response.status()>=400&&!response.url().includes('favicon')&&!(response.status()===401&&response.url().includes('/api/auth/me'))) unexpected.push(`${response.status()} ${response.url()}`)
 })
 const customerContext=await browser.newContext(),customer=await customerContext.newPage();watch(customer)
 await customer.goto('/')
 await customer.getByLabel('Usuário').fill('cliente1988')
 await customer.getByLabel('Senha').fill('123')
 await customer.getByRole('button',{name:'Entrar'}).click()
 await expect(customer.getByText('Café Aurora')).toBeVisible()
 await expect(customer.locator('body')).not.toContainText('[object Object]')
 await customer.screenshot({path:'../docs/evidence/fase14/cliente.png',fullPage:true})

 const adminContext=await browser.newContext(),admin=await adminContext.newPage();watch(admin)
 await admin.goto('/login')
 await admin.getByLabel('Usuário').fill('Admin')
 await admin.getByLabel('Senha').fill('Admin')
 await admin.getByRole('button',{name:'Entrar'}).click()
 await expect(admin).toHaveURL(/\/admin/)
 await admin.getByRole('button',{name:'Base de conhecimento'}).click()
 await expect(admin.locator('body')).not.toContainText('[object Object]')
 await admin.screenshot({path:'../docs/evidence/fase14/admin-rag.png',fullPage:true})

 const techContext=await browser.newContext(),tech=await techContext.newPage();watch(tech)
 await tech.goto('/login')
 await tech.getByLabel('Usuário').fill('Tecnico')
 await tech.getByLabel('Senha').fill('Tecnico')
 await tech.getByRole('button',{name:'Entrar'}).click()
 await expect(tech).toHaveURL(/\/tecnico/)
 await expect(tech.locator('body')).not.toContainText('[object Object]')
 await tech.screenshot({path:'../docs/evidence/fase14/tecnico.png',fullPage:true})
 expect(unexpected).toEqual([])
 await customerContext.close();await adminContext.close();await techContext.close()
})
