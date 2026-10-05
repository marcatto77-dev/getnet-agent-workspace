import {test,expect,Page} from '@playwright/test'

const customer={id:3,username:'cliente1988',role:'cliente',display_name:'Café Aurora',customer_id:'cliente1988',must_change_password:false}

async function openAuthenticatedChat(page:Page){
  await page.route('**/api/auth/me',route=>route.fulfill({json:customer}))
  await page.goto('/')
}

test('authenticated customer sends message and sees a clean answer with sources',async({page})=>{
  await page.route('**/api/chat',r=>r.fulfill({json:{request_id:'test-123',conversation_id:'conv-123',answer:'Resposta fundamentada [1].',route:'knowledge',agents_used:['Router','Knowledge'],sources:[{id:1,title:'Getnet oficial',url:'https://site.getnet.com.br/',kind:'rag',retrieved_at:'2026-09-20'}],steps:[{agent:'Router',action:'Rota knowledge',duration_ms:10}],status:'ok',latency_ms:20}}))
  await openAuthenticatedChat(page)
  await page.getByLabel('Sua mensagem').fill('Qual produto combina comigo?')
  const response=page.waitForResponse('**/api/chat')
  await page.getByRole('button',{name:'Enviar mensagem'}).click()
  expect((await response).status()).toBe(200)
  await expect(page.locator('.public-message.ai').last()).toContainText('Resposta fundamentada')
  await expect(page.getByRole('link',{name:/Site Getnet/})).toHaveAttribute('href','https://site.getnet.com.br/')
  await expect(page.getByText('Por trás da resposta')).toHaveCount(0)
  await expect(page.getByText('Atividade dos agentes')).toHaveCount(0)
  await expect(page.getByText('Base de conhecimento')).toHaveCount(0)
})

test('API error is friendly and another message can be attempted',async({page})=>{
  await page.route('**/api/chat',r=>r.fulfill({status:404,json:{code:'not_found',message:'Cliente não localizado no cadastro.',request_id:'req-1'}}))
  await openAuthenticatedChat(page)
  await page.getByLabel('Sua mensagem').fill('Olá')
  const response=page.waitForResponse('**/api/chat')
  await page.getByRole('button',{name:'Enviar mensagem'}).click()
  expect((await response).status()).toBe(404)
  await expect(page.locator('.public-message.ai').last()).toContainText('Cliente não localizado no cadastro')
  await expect(page.getByLabel('Sua mensagem')).toBeEnabled()
})

test('mobile login-only page fits viewport and exposes internal access',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({status:401,json:{code:'unauthorized',message:'Autenticação necessária.',request_id:'req'}}))
  await page.setViewportSize({width:390,height:844})
  await page.goto('/')
  await expect(page.getByRole('heading',{name:'Entre para ser atendido'})).toBeVisible()
  await expect(page.getByRole('link',{name:'Acesso interno'})).toHaveAttribute('href','/login')
  await expect(page.getByLabel('Usuário')).toBeVisible()
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})
