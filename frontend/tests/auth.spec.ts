import {test,expect} from '@playwright/test'

test('admin login redirects to protected area and can logout',async({page})=>{
  await page.route('**/api/auth/login',r=>r.fulfill({json:{id:1,username:'Admin',role:'admin',display_name:'Administrador'}}))
  await page.route('**/api/auth/me',r=>r.fulfill({json:{id:1,username:'Admin',role:'admin',display_name:'Administrador'}}))
  await page.route('**/api/admin',r=>r.fulfill({json:{message:'Área administrativa preparada para a próxima fase.'}}))
  await page.route('**/api/auth/logout',r=>r.fulfill({status:204}))
  await page.goto('/login')
  await page.getByLabel('Usuário').fill('Admin')
  await page.getByLabel('Senha').fill('Admin')
  await page.getByRole('button',{name:'Entrar'}).click()
  await expect(page).toHaveURL(/\/admin$/)
  await expect(page.locator('.admin-profile strong')).toHaveText('Administrador')
  await page.getByRole('button',{name:'Sair'}).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('protected page redirects anonymous visitor to login',async({page})=>{
  await page.route('**/api/auth/me',r=>r.fulfill({status:401,json:{detail:'Autenticação necessária.'}}))
  await page.route('**/api/admin',r=>r.fulfill({status:401,json:{detail:'Autenticação necessária.'}}))
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/login$/)
})

test('validation errors are rendered as readable text',async({page})=>{
  await page.route('**/api/auth/login',r=>r.fulfill({
    status:422,
    json:{detail:[{loc:['body','username'],msg:'Campo obrigatório',type:'missing'}]},
  }))
  await page.goto('/login')
  await page.getByLabel('Usuário').fill('x')
  await page.getByLabel('Senha').fill('x')
  await page.getByRole('button',{name:'Entrar'}).click()
  await expect(page.getByRole('alert')).toContainText('username: Campo obrigatório')
  await expect(page.getByText('[object Object]',{exact:false})).toHaveCount(0)
})
