import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa somente contra Docker real da Fase 13')

test('hardening real: sessão, texto XSS, admin e técnico sem erros',async({browser})=>{
 const unexpected:string[]=[]
 const watch=(page:any)=>page.on('response',(r:any)=>{if(r.status()>=400&&!(r.status()===401&&r.url().includes('/api/auth/me'))&&!r.url().includes('favicon'))unexpected.push(`${r.status()} ${r.url()}`)})

 const techContext=await browser.newContext(),tech=await techContext.newPage();watch(tech)
 await tech.goto('/login');await tech.getByLabel('Usuário').fill('Tecnico');await tech.getByLabel('Senha').fill('Tecnico');await tech.getByRole('button',{name:'Entrar'}).click()
 await expect(tech).toHaveURL(/\/tecnico/)
 await expect(tech.locator('body')).not.toContainText('[object Object]')
 await tech.screenshot({path:'../docs/evidence/fase13/tecnico.png',fullPage:true})

 const customerContext=await browser.newContext(),customer=await customerContext.newPage();watch(customer)
 await customer.goto('/');await customer.getByLabel('Usuário').fill('cliente1988');await customer.getByLabel('Senha').fill('123');await customer.getByRole('button',{name:'Entrar'}).click()
 const payload='<img src=x onerror=window.__xss=1> quero falar com um técnico'
 await customer.getByLabel('Sua mensagem').fill(payload);await customer.getByLabel('Enviar mensagem').click()
 await expect(customer.getByText(payload,{exact:true})).toBeVisible()
 expect(await customer.evaluate(()=>Boolean((window as any).__xss))).toBeFalsy()
 await expect(customer.locator('body')).not.toContainText('[object Object]')
 await customer.screenshot({path:'../docs/evidence/fase13/chat-xss-texto.png',fullPage:true})

 const adminContext=await browser.newContext(),admin=await adminContext.newPage();watch(admin)
 await admin.goto('/login');await admin.getByLabel('Usuário').fill('Admin');await admin.getByLabel('Senha').fill('Admin');await admin.getByRole('button',{name:'Entrar'}).click()
 await expect(admin).toHaveURL(/\/admin/)
 for(const name of ['Dashboard','Usuários','Clientes','Máquinas','Base de conhecimento','Logs']){
   await admin.getByRole('button',{name}).click();await expect(admin.locator('body')).not.toContainText('[object Object]')
 }
 await admin.screenshot({path:'../docs/evidence/fase13/admin-logs.png',fullPage:true})
 expect(unexpected).toEqual([])
 await customerContext.close();await techContext.close();await adminContext.close()
})
