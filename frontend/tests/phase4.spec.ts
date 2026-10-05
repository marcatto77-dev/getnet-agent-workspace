import {test,expect} from '@playwright/test'

const installSocketMock=async(page:any)=>page.addInitScript(()=>{
  const sockets:any[]=[]
  class MockSocket{
    static OPEN=1;readyState=1;url:string;onopen:any;onmessage:any;onclose:any
    constructor(url:string){this.url=url;sockets.push(this);setTimeout(()=>this.onopen?.({}),0)}
    send(){} close(){this.onclose?.({})}
  }
  ;(window as any).WebSocket=MockSocket
  ;(window as any).__wsEmit=(fragment:string,event:any)=>sockets.filter(s=>s.url.includes(fragment)).forEach(s=>s.onmessage?.({data:JSON.stringify(event)}))
})

test('cliente e técnico trocam mensagens em tempo real em contextos separados',async({browser})=>{
  const customerContext=await browser.newContext(),technicianContext=await browser.newContext()
  const customer=await customerContext.newPage(),technician=await technicianContext.newPage()
  await installSocketMock(customer);await installSocketMock(technician)
  await customer.route('**/api/auth/me',route=>route.fulfill({json:{id:3,username:'cliente1988',role:'cliente',display_name:'Café Aurora',customer_id:'cliente1988',must_change_password:false}}))
  await customer.route('**/api/chat',route=>route.fulfill({json:{request_id:'r1',conversation_id:'conv-1',answer:'Seu atendimento foi encaminhado automaticamente para um técnico.',route:'escalate',agents_used:['Router','Escalation'],sources:[],steps:[],status:'with_technician',latency_ms:10}}))
  await technician.route('**/api/auth/me',route=>route.fulfill({json:{id:2,username:'Tecnico',role:'tecnico',display_name:'Técnico'}}))
  await technician.route('**/api/tech/service-center/summary',route=>route.fulfill({json:{queue:0,mine:1,others:0,closed:0}}))
  await technician.route('**/api/tech/queue',route=>route.fulfill({json:[]}))
  await technician.route('**/api/tech/handoffs/mine',route=>route.fulfill({json:[{id:'h1',conversation_id:'conv-1',customer_name:'Café Aurora',terminal_name:'Get Smart',reason:'cliente_pediu',summary:'Terminal offline',status:'assigned',assigned_at:'2026-09-20T12:00:00Z'}]}))
  await technician.route('**/api/tech/handoffs/others',route=>route.fulfill({json:[]}))
  await technician.route('**/api/tech/technicians',route=>route.fulfill({json:[]}))
  await technician.route('**/api/tech/handoffs/h1/events',route=>route.fulfill({json:[]}))
  await technician.route('**/api/tech/conversations/conv-1?*',route=>route.fulfill({json:{id:'conv-1',handoff_id:'h1',status:'with_technician',external_id:'cliente1988',nome:'Café Aurora',reason:'cliente_pediu',handoff_status:'assigned',assigned_at:'2026-09-20T12:00:00Z',summary:{problem:'Terminal offline',attempts:['Triagem']},messages:[],customer:{nome:'Café Aurora',contato:'demo'},terminals:[{model:'Get Smart',connection_status:'offline'}],receivables:[{amount:1250.8,status:'previsto'}]}}))
  await technician.route('**/api/tech/conversations/conv-1/messages',route=>route.fulfill({json:{id:'m-tech',sender_type:'technician',content:'Olá, vou ajudar agora.'}}))
  await customer.goto('/');await customer.getByLabel('Sua mensagem').fill('Quero um técnico');await customer.getByRole('button',{name:'Enviar mensagem'}).click()
  await technician.goto('/tecnico');await technician.getByRole('button',{name:/Meus atendimentos/}).click();await technician.getByRole('button',{name:/Café Aurora/}).click();await technician.getByLabel('Mensagem ao cliente').fill('Olá, vou ajudar agora.');await technician.getByRole('button',{name:'Enviar ao cliente'}).click()
  await customer.evaluate(()=>(window as any).__wsEmit('/ws/chat/conv-1',{type:'message',message:{id:'m-tech',sender_type:'technician',sender_name:'Técnico',content:'Olá, vou ajudar agora.'}}))
  await expect(customer.getByText('Olá, vou ajudar agora.')).toBeVisible()
  await customerContext.close();await technicianContext.close()
})

test('dois técnicos visualizam somente suas próprias distribuições',async({browser})=>{
  for(const assigned of [{name:'Técnico 1',customer:'Café Aurora',id:'conv-a'},{name:'Técnico 2',customer:'Mercado Horizonte',id:'conv-b'}]){
    const context=await browser.newContext(),page=await context.newPage();await installSocketMock(page)
    await page.route('**/api/auth/me',route=>route.fulfill({json:{id:assigned.id==='conv-a'?2:3,username:assigned.name,role:'tecnico',display_name:assigned.name}}))
    await page.route('**/api/tech/service-center/summary',route=>route.fulfill({json:{queue:0,mine:1,others:0,closed:0}}))
    await page.route('**/api/tech/queue',route=>route.fulfill({json:[]}))
    await page.route('**/api/tech/handoffs/mine',route=>route.fulfill({json:[{id:`h-${assigned.id}`,conversation_id:assigned.id,customer_name:assigned.customer,terminal_name:'Get Smart',reason:'cliente_pediu',summary:'Resumo',status:'assigned',assigned_at:'2026-09-20T12:00:00Z'}]}))
    await page.route('**/api/tech/handoffs/others',route=>route.fulfill({json:[]}))
    await page.route('**/api/tech/technicians',route=>route.fulfill({json:[]}))
    await page.goto('/tecnico');await page.getByRole('button',{name:/Meus atendimentos/}).click();await expect(page.getByRole('button',{name:new RegExp(assigned.customer)})).toBeVisible();await expect(page.locator('.center-list>button')).toHaveCount(1);await context.close()
  }
})
