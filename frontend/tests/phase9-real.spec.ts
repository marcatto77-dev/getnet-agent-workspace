import {expect,test,Page} from '@playwright/test'

test.skip(!process.env.REAL_E2E,'Executa somente contra o Docker real da Fase 9')
test.describe.configure({mode:'serial'})

const evidence='../docs/evidence/fase9'

async function assertHealthy(page:Page){
 await expect(page.locator('.admin-alert,.auth-error')).toHaveCount(0)
 await expect(page.getByText('[object Object]',{exact:false})).toHaveCount(0)
 await expect(page.getByText('Banco indisponível',{exact:false})).toHaveCount(0)
}

async function login(page:Page,username:string,password:string){
 await page.goto('/login')
 await page.getByLabel('Usuário').fill(username)
 await page.getByLabel('Senha').fill(password)
 await page.getByRole('button',{name:'Entrar'}).click()
}

test('smoke real percorre chat, todas as abas admin e técnico sem erros visuais ou HTTP',async({browser})=>{
 const unexpected:string[]=[]
 const context=await browser.newContext()
 const page=await context.newPage()
 page.on('response',response=>{if(response.status()>=400&&!response.url().includes('/favicon'))unexpected.push(`${response.status()} ${response.url()}`)})

 await page.goto('/')
 await page.getByLabel('Usuário').fill('cliente1988')
 await page.getByLabel('Senha').fill('123')
 await page.getByRole('button',{name:'Entrar'}).click()
 await page.getByLabel('Sua mensagem').fill('Quando recebo o dinheiro das vendas de ontem?')
 await page.getByLabel('Enviar mensagem').click()
 await expect(page.getByText(/20\/09\/2026|20\/09/).last()).toBeVisible({timeout:150000})
 await expect(page.getByText('previsto_demo',{exact:false})).toHaveCount(0)
 await expect(page.getByText('get_receivables',{exact:false})).toHaveCount(0)
 await page.getByLabel('Sua mensagem').fill('ok')
 await page.getByLabel('Enviar mensagem').click()
 await expect(page.getByText(/Por nada!/)).toBeVisible()
 await page.screenshot({path:`${evidence}/chat-recebiveis-ok.png`,fullPage:true})

 await page.getByLabel('Sua mensagem').fill('Quero falar com um técnico')
 await page.getByLabel('Enviar mensagem').click()
 await expect(page.getByText(/Estamos transferindo você para um técnico/)).toBeVisible({timeout:150000})
 await page.waitForTimeout(1500)
 await expect(page.getByText(/fila, posição 1/)).toHaveCount(1)
 await page.screenshot({path:`${evidence}/chat-fila-sem-duplicacao.png`,fullPage:true})

 await login(page,'Admin','Admin')
 await expect(page).toHaveURL(/\/admin/)
 for(const [name,file,visible] of [
  ['Dashboard','admin-dashboard.png','Visão do atendimento'],
  ['Usuários','admin-usuarios.png','Equipe interna'],
  ['Máquinas','admin-maquinas.png','Parque de máquinas'],
  ['Base de conhecimento','admin-rag.png','Documentos e embeddings'],
  ['Logs','admin-logs.png','Execuções dos agentes'],
 ] as const){
  await page.getByRole('button',{name}).click()
  await expect(page.getByText(visible,{exact:false}).first()).toBeVisible()
  if(name==='Usuários') await expect(page.getByText('Admin',{exact:true}).first()).toBeVisible()
  if(name==='Máquinas') await expect(page.getByText('Café Aurora',{exact:true}).first()).toBeVisible()
  if(name==='Base de conhecimento') await expect(page.getByText(/12 documentos/)).toBeVisible()
  await assertHealthy(page)
  await page.screenshot({path:`${evidence}/${file}`,fullPage:true})
 }
 await expect(page.getByText(/execuções/).last()).toBeVisible()
 await page.getByRole('button',{name:'Auditoria administrativa'}).click()
 await expect(page.getByText('Registro de auditoria')).toBeVisible()
 await assertHealthy(page)
 await page.screenshot({path:`${evidence}/admin-auditoria.png`,fullPage:true})
 await page.getByRole('button',{name:/Sair/}).click()

 await login(page,'Tecnico','Tecnico')
 await expect(page).toHaveURL(/\/tecnico/)
 await expect(page.getByText('ATENDIMENTO TÉCNICO')).toBeVisible()
 await assertHealthy(page)
 await page.screenshot({path:`${evidence}/tecnico.png`,fullPage:true})
 expect(unexpected).toEqual([])
 await context.close()
})
