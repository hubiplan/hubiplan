import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { confirmLeave, useDraftGuard } from '../../components/leaveGuard.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { MusicHeader, MusicEmptyState } from './MusicLayout.tsx'

type Choice = {id:number;name:string}
type Stock = {id:number;title:string;number:string;version:number}
type Equipment = {id:number;item:number;title:string;number:string;version:number;kind:string;instrument:string;size:string;condition:string;condition_note:string;maintenance_due:string|null;maintenance_overdue:boolean;active_loan:number|null;return_location:{location_kind:string}|null;loans:{id:number;name:string;issued_at:string;due_date:string;returned_at:string|null;overdue:boolean;note:string;return_note:string}[];maintenance:{id:number;date:string;next_due:string|null;condition:string;note:string}[]}
type Mode = 'register'|'profile'|'issue'|'return'|'maintenance'
const conditions=()=>[['ready',t('Einsatzbereit')],['limited',t('Eingeschränkt nutzbar')],['defective',t('Defekt')],['retired',t('Ausgesondert')]]
const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Berlin'}).format(new Date())

export function EquipmentPage() {
  const org=useActiveOrg()
  if(!org.modules.includes('material') || !org.permissions.includes('material.view')) return <Alert kind="error">{t('Dafür fehlt dir die Berechtigung.')}</Alert>
  return <EquipmentWorkspace/>
}

function EquipmentWorkspace() {
  const org=useActiveOrg()
  const url=`/api/orgs/${org.id}/music/equipment/`
  const load=useLoad(()=>api.get<{items:Equipment[];available:Stock[];musicians:Choice[]}>(url),[org.id])
  const [editing,setEditing]=useState<{mode:Mode;item?:Equipment}|null>(null)
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  const [search,setSearch]=useState('')
  const [busy,setBusy]=useState(false)
  const canEdit=org.permissions.includes('music.edit') && org.permissions.includes('material.edit')
  const data=load.data
  async function save(values:Record<string,unknown>,key:string) {
    setBusy(true);setError('');setMessage('')
    try {await api.post(url,values,key);setEditing(null);await load.reload();setMessage(t('Musikausstattung wurde gespeichert.'))}
    catch(e){setError(errorMessage(e));throw e}finally{setBusy(false)}
  }
  async function edit(mode:Mode,item?:Equipment) {if(await confirmLeave()){setEditing({mode,item});setError('');setMessage('')}}
  if(load.error)return <Alert kind="error">{load.error}</Alert>
  if(!data)return <p>{t('Lädt …')}</p>
  return <section className="stack music-page">
    <MusicHeader title={t('Instrumente und Uniformen')} description={t('Musikausstattung mit dem bestehenden Materialbestand verbinden, ausgeben, zurücknehmen und warten.')}/>
    {error && <Alert kind="error">{error}</Alert>}{message && <Alert kind="success">{message}</Alert>}
    <div className="music-actions"><Link to="/material">{t('Zur Materialverwaltung')}</Link>{canEdit && <button className="button button-primary" disabled={busy} onClick={()=>void edit('register')}>{t('Material als Musikausstattung verbinden')}</button>}</div>
    <label>{t('Musikausstattung suchen')}<input type="search" value={search} onChange={e=>setSearch(e.target.value)}/></label>
    {editing?.mode==='register' && <EquipmentForm key="register" mode="register" stock={data.available} musicians={data.musicians} busy={busy} onSave={save}/>}
    {!data.items.length && <MusicEmptyState/>}
    {data.items.filter(x=>[x.title,x.number,x.instrument,x.size].join(' ').toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())).map(item=><article className="card stack music-record" key={item.id} id={`material-${item.item}`}>
      <h2>{item.title}</h2><p>{item.number} · {item.kind==='uniform'?t('Uniform'):t('Instrument')} · {item.instrument} {item.size}</p>
      <p>{conditions().find(x=>x[0]===item.condition)?.[1]} · {item.condition_note}</p>
      {item.maintenance_due && <p className={item.maintenance_overdue?'music-status music-status-conflict':''}>{t('Nächste Wartung')}: {item.maintenance_due}</p>}
      <Link to={`/material/${item.item}`}>{t('Materialakte öffnen')}</Link>
      {item.loans.filter(x=>!x.returned_at).map(loan=><p className={loan.overdue?'music-status music-status-conflict':''} key={loan.id}>{t('Ausgegeben an {name}',{name:loan.name})} · {t('Rückgabe bis')}: {loan.due_date}{loan.overdue?` · ${t('Überfällig')}`:''}</p>)}
      {canEdit && <div className="music-actions">{(['profile',...(item.active_loan?['return']:['issue']),'maintenance'] as Mode[]).map(mode=><button className="button button-ghost" key={mode} disabled={busy || (mode==='issue' && !['ready','limited'].includes(item.condition))} onClick={()=>void edit(mode,item)}>{{profile:t('Ausstattungsdaten bearbeiten'),issue:t('Ausstattung ausgeben'),return:t('Ausstattung zurücknehmen'),maintenance:t('Wartung dokumentieren'),register:''}[mode]}</button>)}</div>}
      {editing?.item?.id===item.id && <EquipmentForm key={`${item.id}-${item.version}-${editing.mode}`} mode={editing.mode} item={item} stock={data.available} musicians={data.musicians} busy={busy} onSave={save}/>}
      <details><summary>{t('Letzte 100 Ausgaben und Wartungen')}</summary>
        {item.loans.map(loan=><p key={loan.id}>{loan.name} · {formatDateTime(loan.issued_at)} · {loan.returned_at?`${t('Zurückgegeben')}: ${formatDateTime(loan.returned_at)}`:t('Ausgegeben')} · {loan.note} {loan.return_note}</p>)}
        {item.maintenance.map(row=><p key={row.id}>{row.date} · {conditions().find(x=>x[0]===row.condition)?.[1]} · {row.note}</p>)}
      </details>
    </article>)}
    {editing && <button className="button button-ghost" disabled={busy} onClick={async()=>{if(await confirmLeave())setEditing(null)}}>{t('Bearbeitung schließen')}</button>}
  </section>
}

function EquipmentForm({mode,item,stock,musicians,busy,onSave}:{mode:Mode;item?:Equipment;stock:Stock[];musicians:Choice[];busy:boolean;onSave:(values:Record<string,unknown>,key:string)=>Promise<void>}) {
  const [values,setValues]=useState<Record<string,string>>({item:'',kind:item?.kind || 'instrument',instrument:item?.instrument || '',size:item?.size || '',maintenance_due:item?.maintenance_due || '',musician:'',due_date:'',date:today(),next_due:'',condition:item?.condition || 'ready',condition_note:'',note:'',street:'',postal_code:'',city:'',country:'DE'})
  const [restore,setRestore]=useState(!!item?.return_location && item.return_location.location_kind!=='unknown')
  const [key,setKey]=useState(newRequestKey)
  const [dirty,setDirty]=useState(false)
  useDraftGuard(dirty)
  function change(field:string,value:string){setValues({...values,[field]:value});setKey(newRequestKey());setDirty(true)}
  function input(field:string,label:string,type='text',required=false,maxLength=100) {return <label key={field}>{label}<input type={type} required={required} maxLength={maxLength} value={values[field]} onChange={e=>change(field,e.target.value)}/></label>}
  function select(field:string,label:string,options:string[][]){return <label>{label}<select required value={values[field]} onChange={e=>change(field,e.target.value)}>{options.map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></label>}
  return <form className="stack" onSubmit={async e=>{e.preventDefault();const source=stock.find(x=>x.id===Number(values.item));let payload:Record<string,unknown>={action:mode,item:item?.item || source?.id,version:item?.version || source?.version}
    if(mode==='register' || mode==='profile')payload={...payload,kind:values.kind,instrument:values.instrument,size:values.size,maintenance_due:values.maintenance_due || null}
    else if(mode==='issue')payload={...payload,musician:Number(values.musician),due_date:values.due_date,note:values.note}
    else if(mode==='return')payload={...payload,loan:item?.active_loan,restore_location:restore,address:{street:values.street,postal_code:values.postal_code,city:values.city,country:values.country},condition:values.condition,condition_note:values.condition_note,note:values.note}
    else payload={...payload,date:values.date,next_due:values.next_due || null,condition:values.condition,note:values.note}
    try{await onSave(payload,key);setDirty(false)}catch{/* Parent keeps the entered values and displays the error. */}
  }}><fieldset className="stack" disabled={busy}>
    {mode==='register' && select('item',t('Vorhandenes Material'),[['',t('Bitte wählen')],...stock.map(x=>[String(x.id),`${x.number} · ${x.title}`])])}
    {(mode==='register' || mode==='profile') && <>{select('kind',t('Art'),[['instrument',t('Instrument')],['uniform',t('Uniform')]])}<div className="music-form-fields">{input('instrument',t('Instrument'))}{input('size',t('Größe / Ausführung'))}{input('maintenance_due',t('Nächste Wartung'),'date')}</div></>}
    {mode==='issue' && <>{select('musician',t('Musiker'),[['',t('Bitte wählen')],...musicians.map(x=>[String(x.id),x.name])])}{input('due_date',t('Rückgabe bis'),'date',true)}</>}
    {mode==='return' && <><label><input type="checkbox" checked={restore} disabled={!item?.return_location || item.return_location.location_kind==='unknown'} onChange={e=>{setRestore(e.target.checked);setKey(newRequestKey());setDirty(true)}}/>{t('Bisherigen Lagerort bei Rückgabe wiederherstellen')}</label>{!restore && <div className="music-form-fields">{input('street',t('Straße und Hausnummer'),'text',true,300)}{input('postal_code',t('Postleitzahl'),'text',true,300)}{input('city',t('Ort'),'text',true,300)}{input('country',t('Land'),'text',true,300)}</div>}{input('condition_note',t('Zustandshinweis'),'text',false,500)}</>}
    {mode==='maintenance' && <div className="music-form-fields">{input('date',t('Wartungsdatum'),'date',true)}{input('next_due',t('Nächste Wartung'),'date')}</div>}
    {(mode==='return' || mode==='maintenance') && select('condition',t('Zustand'),conditions())}
    {!['register','profile'].includes(mode) && <label>{t('Übergabe- / Wartungsvermerk')}<textarea maxLength={1000} value={values.note} onChange={e=>change('note',e.target.value)}/></label>}
    <button className="button button-primary">{t('Speichern')}</button>
  </fieldset></form>
}
