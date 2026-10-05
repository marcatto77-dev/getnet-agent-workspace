export type ApiErrorPayload={code?:string;message?:unknown;detail?:unknown;request_id?:string}

export function formatApiError(value:unknown,fallback='Não foi possível concluir a operação.'):string{
 const payload=value instanceof Response?null:value as ApiErrorPayload|unknown
 if(typeof payload==='string')return payload
 if(Array.isArray(payload)){
  const messages=payload.map(item=>{
   if(typeof item==='string')return item
   if(item&&typeof item==='object'){
    const entry=item as {loc?:unknown[];msg?:unknown;message?:unknown}
    const location=Array.isArray(entry.loc)?entry.loc.filter(part=>part!=='body').join('.'):''
    const message=typeof entry.msg==='string'?entry.msg:typeof entry.message==='string'?entry.message:''
    return [location,message].filter(Boolean).join(': ')
   }
   return ''
  }).filter(Boolean)
  return messages.join('; ')||fallback
 }
 if(payload&&typeof payload==='object'){
  const item=payload as ApiErrorPayload
  const raw=item.message??item.detail
  const message=formatApiError(raw,typeof item.code==='string'?item.code:fallback)
  return item.request_id?`${message} (ID: ${item.request_id})`:message
 }
 return fallback
}

export async function api<T=unknown>(path:string,options?:RequestInit):Promise<T>{
 const response=await fetch('/api'+path,{...options,headers:options?.body?{'Content-Type':'application/json',...options.headers}:options?.headers})
 let data:unknown=null
 if(response.status!==204){try{data=await response.json()}catch{data=await response.text()}}
 if(!response.ok)throw new Error(formatApiError(data,`Falha HTTP ${response.status}.`))
 return data as T
}

export function queryString(values:Record<string,string|number|null|undefined>):string{
 const params=new URLSearchParams()
 for(const [key,value] of Object.entries(values))if(value!==''&&value!=null)params.set(key,String(value))
 return params.toString()
}

export function localDateTimeIso(value:string):string|undefined{
 if(!value)return undefined
 const date=new Date(value)
 return Number.isNaN(date.getTime())?undefined:date.toISOString()
}
