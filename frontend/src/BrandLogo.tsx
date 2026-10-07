import { getnetLogo } from './assets/getnetLogo'

export function BrandLogo({ className = '', caption }: { className?: string; caption?: string }) {
  return <div className={`getnet-brand ${className}`}><img src={getnetLogo} alt="Getnet" width="887" height="198"/>{caption && <small>{caption}</small>}</div>
}
