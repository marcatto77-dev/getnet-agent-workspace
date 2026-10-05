import {expect,test} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa contra Docker real da Fase 15')

test('central backend: técnico entra, cliente não acessa tela técnica',async({browser})=>{
 const techContext=await browser.newContext(),tech=await techContext.newPage()
 await tech.goto('/login'); await tech.getByLabel('Usuário').fill('Tecnico'); await tech.getByLabel('Senha').fill('Tecnico'); await tech.getByRole('button',{name:'Entrar'}).click()
 await expect(tech).toHaveURL(/\/tecnico/); await expect(tech.locator('body')).not.toContainText('[object Object]')
 await tech.screenshot({path:'../docs/evidence/fase15/tecnico.png',fullPage:true})
 const customerContext=await browser.newContext(),customer=await customerContext.newPage()
 await customer.goto('/login'); await customer.getByLabel('Usuário').fill('cliente1988'); await customer.getByLabel('Senha').fill('123'); await customer.getByRole('button',{name:'Entrar'}).click()
 await customer.goto('/tecnico'); await expect(customer).not.toHaveURL(/\/tecnico/)
 await customer.screenshot({path:'../docs/evidence/fase15/cliente-barrado.png',fullPage:true})
 await techContext.close(); await customerContext.close()
})
