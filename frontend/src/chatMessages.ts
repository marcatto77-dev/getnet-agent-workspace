export function isRoutineDeliveryNotice(senderType:string,content:string):boolean{
  if(senderType!=='system')return false
  return content.startsWith('Sua mensagem foi registrada e ficará disponível para o técnico responsável.')
    || content.startsWith('Sua mensagem foi registrada e permanece na fila para atendimento técnico.')
}
