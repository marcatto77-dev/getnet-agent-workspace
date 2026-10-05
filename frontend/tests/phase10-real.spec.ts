import {expect,test} from '@playwright/test'
test.skip(!process.env.REAL_E2E,'Executa somente contra Docker real da Fase 10')
test('admin cria cliente e cliente troca a senha obrigatória',async({page})=>{
 const failures:string[]=[];page.on('response',r=>{if(r.status()>=400&&!r.url().includes('favicon'))failures.push(`${r.status()} ${r.url()}`)})
 await page.goto('/login');await page.getByLabel('Usuário').fill('Admin');await page.getByLabel('Senha').fill('Admin');await page.getByRole('button',{name:'Entrar'}).click()
 await page.getByRole('button',{name:'Clientes'}).click();await expect(page.getByText('Café Aurora')).toBeVisible();await page.screenshot({path:'../docs/evidence/fase10/admin-clientes.png',fullPage:true})
 await page.getByRole('button',{name:'Novo cliente'}).click();await page.getByLabel('Identificador de login').fill('cliente9100');await page.getByLabel('Nome de exibição').fill('Cliente Fase Dez');await page.getByLabel('E-mail').fill('fase10@example.com');await page.getByLabel('Telefone').fill('11910001000');await page.getByRole('button',{name:'Salvar'}).click();await expect(page.getByText('Cliente Fase Dez')).toBeVisible()
 await page.getByRole('button',{name:/Sair/}).click();await page.getByLabel('Usuário').fill('cliente9100');await page.getByLabel('Senha').fill('123');await page.getByRole('button',{name:'Entrar'}).click();await expect(page).toHaveURL(/change-password/);await page.screenshot({path:'../docs/evidence/fase10/troca-obrigatoria.png',fullPage:true})
 await page.getByLabel('Senha atual').fill('123');await page.getByLabel('Nova senha').fill('Cliente-Forte-9100');await page.getByRole('button',{name:'Alterar senha'}).click();await expect(page).toHaveURL(/127\.0\.0\.1:8080\/$/);await expect(page.getByText('Como podemos ajudar?')).toBeVisible();await page.screenshot({path:'../docs/evidence/fase10/cliente-logado.png',fullPage:true})
 await expect(page.getByText('[object Object]',{exact:false})).toHaveCount(0);expect(failures).toEqual([])
})
