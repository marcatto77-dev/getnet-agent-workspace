import {expect, test} from '@playwright/test'

test('admin apresenta prompts e regras como texto e navega por teclado', async ({page}) => {
  await page.route('**/api/auth/me', route=>route.fulfill({json:{id:1,username:'Admin',role:'admin',display_name:'Administrador'}}))
  await page.route('**/api/health/ready', route=>route.fulfill({json:{degraded:false}}))
  await page.route('**/api/admin/users', route=>route.fulfill({json:[]}))
  await page.route('**/api/admin/agents', route=>route.fulfill({json:{
    read_only:true,model:'gpt-4.1-mini',embedding_model:'text-embedding-3-small',scope:'Getnet e câmbio. Clima recusado.',handoff:'Após três respostas, oferta com aceite.',languages:'Português, inglês e espanhol.',
    agents:[{name:'ROUTER',description:'Decide a rota',prompt:'Texto do prompt <script>window.executed=true</script>'}],
    guardrails:[{name:'Entrada',description:'Verifica a mensagem',source:'def inspect_input(): pass'}],limits:{tool_timeout_seconds:8,chat_requests_per_minute:20},
  }}))
  await page.goto('/admin')
  await page.getByRole('button',{name:'Agentes e segurança',exact:true}).click()
  await expect(page.getByText('Configuração em execução', {exact:false})).toBeVisible()
  const summary=page.locator('summary').filter({hasText:'ROUTER'})
  await summary.focus();await page.keyboard.press('Enter')
  await expect(page.locator('.agent-source pre')).toContainText('<script>window.executed=true</script>')
  expect(await page.evaluate(()=>Boolean((window as any).executed))).toBe(false)
  await page.getByRole('button',{name:'Regras de guardrails'}).click()
  await page.locator('summary').filter({hasText:'Entrada'}).click()
  await expect(page.locator('.agent-source pre')).toContainText('def inspect_input')
})

test('admin inspector trata erro e permite tentar novamente', async ({page}) => {
  await page.route('**/api/auth/me', route=>route.fulfill({json:{id:1,role:'admin',display_name:'Administrador'}}))
  await page.route('**/api/admin/users', route=>route.fulfill({json:[]}))
  await page.route('**/api/health/ready', route=>route.fulfill({json:{degraded:false}}))
  await page.route('**/api/admin/agents', route=>route.fulfill({status:503,json:{message:'Configuração indisponível'}}))
  await page.goto('/admin')
  await page.getByRole('button',{name:'Agentes e segurança',exact:true}).click()
  await expect(page.getByRole('alert')).toHaveText('Configuração indisponível')
  await expect(page.getByRole('button',{name:'Tentar novamente'})).toBeVisible()
  await expect(page.locator('body')).not.toContainText('[object Object]')
})
