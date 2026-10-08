import React, {useEffect, useRef, useState} from 'react';
import {Activity, RefreshCw, FileText, Play, Database, CheckCircle2, AlertTriangle, Search, ChevronRight, Download, Upload, Plus, Radio} from 'lucide-react';
import {api, write, rows, response, download} from '../api';
import {RealLiveWorkspace} from './RealLiveWorkspace';

export const panel = 'rounded-xl border border-slate-800 bg-slate-900/60 p-5 space-y-4';
export const input = 'w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100';
export const button = 'inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed';
export const secondary = 'inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800 disabled:opacity-40';
export function Json({value}: {value: any}) {return <pre className="text-xs whitespace-pre-wrap break-words bg-slate-950 p-4 rounded-lg max-h-96 overflow-auto">{JSON.stringify(value, null, 2)}</pre>;}
function Empty({children = 'No persisted results yet.'}: {children?: React.ReactNode}) {return <p className="text-sm text-slate-400 py-5">{children}</p>;}
export function ErrorBox({error}: {error: string}) {return error ? <div role="alert" className="p-3 rounded-lg border border-amber-700 bg-amber-950/40 text-amber-200 text-sm break-words">{error}</div> : null;}
function useRequest() {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function run(fn: () => Promise<void>) {setBusy(true); setError(''); try {await fn();} catch (e) {setError((e as Error).message);} finally {setBusy(false);}}
  return {busy, error, run};
}
function useResource(path: string | null, interval = 0, pauseWhenFinished = false) {
  const [data, setData] = useState<any>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    setData(null); setError(''); if (!path) return;
    let active = true, running = false;
    async function load() {if (running) return; running = true; setLoading(true);
      try {const result = await api(path!); if (active) {setData(result); setError('');
        if (pauseWhenFinished && ['completed','failed','cancelled'].includes(result.status) && !(result.jobs || []).some((j:any)=>['queued','running'].includes(j.status))) {if (timer) clearInterval(timer);}
      }}
      catch (e) {if (active) setError((e as Error).message);} finally {running = false; if (active) setLoading(false);}}
    void load(); const timer = interval ? setInterval(load, interval) : undefined;
    return () => {active = false; if (timer) clearInterval(timer);};
  }, [path, interval, version, pauseWhenFinished]);
  return {data, error, loading, refresh: () => setVersion(v => v+1)};
}
function Remote({path, title}: {key?:string; path: string; title: string}) {
  const state = useResource(path);
  return <section className={panel}><div className="flex justify-between"><h3 className="font-semibold">{title}</h3><button className={secondary} onClick={state.refresh} disabled={state.loading}><RefreshCw size={14}/>Refresh</button></div>
    <ErrorBox error={state.error}/>{state.loading && !state.data ? <Empty>Loading…</Empty> : state.data && <RecordList value={state.data}/>}</section>;
}
function RecordList({value}: {value: any}) {
  const records = rows(value);
  if (Array.isArray(value) || Array.isArray(value?.items) || Array.isArray(value?.results)) return !records.length ? <Empty/> : <div className="space-y-3">{records.map((record, i) => <article key={record.id || record.knowledge_id || record.run_id || i} className="border border-slate-800 rounded-xl p-4 space-y-3">
    <div className="flex justify-between gap-3"><h4 className="font-medium text-sm">{record.title || record.query || record.query_text || record.run_id || record.name || record.id || 'Record'}</h4><span className="text-xs text-indigo-300">{record.status || record.lifecycle_state || record.object_type || ''}</span></div>
    <p className="text-sm whitespace-pre-wrap">{record.answer || record.answer_text || record.translated_text || record.content || record.description || ''}</p>
    <details><summary className="cursor-pointer text-xs text-slate-400">Source, identifiers & provenance</summary><Json value={record}/></details></article>)}</div>;
  return <Json value={value}/>;
}
export function Connection({onConnect, onClose}: {onConnect: (token: string, tenant: string) => Promise<void>; onClose?: () => void}) {
  const [token, setToken] = useState(''), [tenant, setTenant] = useState(''); const request = useRequest();
  const [mode, setMode] = useState('password'), [email, setEmail] = useState(''), [password, setPassword] = useState('');
  return <form className={panel} onSubmit={e => {e.preventDefault(); void request.run(async () => {
    if (mode === 'token') await onConnect(token.trim(), tenant.trim());
    else {const session = await write('/auth/login', {email, password}); await onConnect(session.access_token, '');}
    setPassword(''); setToken('');
  });}}>
    <h2 className="text-xl font-semibold">Connect your workspace</h2><p className="text-sm text-slate-400">Sign in to an enrolled account, or connect with an authorized token and set a password in Account. Your session stays in memory.</p>
    <div className="flex gap-2"><button type="button" className={mode === 'password' ? button : secondary} onClick={() => setMode('password')}>Email & password</button><button type="button" className={mode === 'token' ? button : secondary} onClick={() => setMode('token')}>Bearer token</button></div>
    {mode === 'password' ? <><label className="block text-sm">Email<input className={input} type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)}/></label><label className="block text-sm">Password<input className={input} type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)}/></label></> : <>
    <label className="block text-sm">Bearer token<input className={input} aria-label="Bearer token" type="password" autoComplete="off" required value={token} onChange={e => setToken(e.target.value)}/></label>
    <label className="block text-sm">Tenant ID (if required by your credential)<input className={input} value={tenant} onChange={e => setTenant(e.target.value)}/></label></>}<ErrorBox error={request.error}/>
    <button className={button} disabled={request.busy}>Connect</button>{onClose && <button type="button" className={secondary} onClick={onClose}>Close</button>}
  </form>;
}
export function Profile({auth, onUpdate, onSignOut, onClose}: any) {
  const [name, setName] = useState(auth.user_name); const request = useRequest();
  const [currentPassword, setCurrentPassword] = useState(''), [newPassword, setNewPassword] = useState(''), [passwordSaved, setPasswordSaved] = useState(false);
  return <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-5"><section className={`${panel} bg-slate-900 max-w-lg w-full`}>
    <h2 className="text-lg font-semibold">Account</h2><p>{auth.user_email}</p><p className="text-sm text-slate-400">Role: {auth.role} · Tenant: {auth.tenant_id}</p>
    <form onSubmit={e => {e.preventDefault(); void request.run(async () => {const me = await write('/auth/me', {full_name: name}, 'PATCH'); onUpdate(me);});}}><label>Display name<input className={input} value={name} onChange={e => setName(e.target.value)} required maxLength={255}/></label><button className={`${button} mt-3`} disabled={request.busy}>Save profile</button></form>
    <details><summary className="cursor-pointer">Set or change sign-in password</summary><form className="space-y-3 mt-3" onSubmit={e => {e.preventDefault(); void request.run(async () => {await write('/auth/me/password', {current_password:currentPassword || null, new_password:newPassword}, 'PUT'); setCurrentPassword(''); setNewPassword(''); setPasswordSaved(true);});}}>
      <label className="block text-sm">Current password (leave empty for first setup)<input className={input} type="password" autoComplete="current-password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)}/></label>
      <label className="block text-sm">New password (at least 12 characters)<input className={input} type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={newPassword} onChange={e => {setNewPassword(e.target.value); setPasswordSaved(false);}}/></label>
      <button className={button} disabled={request.busy}>Save password</button>{passwordSaved && <p role="status">Password saved. You can now sign in with your email.</p>}
    </form></details>
    <ErrorBox error={request.error}/><div className="flex gap-3"><button className={secondary} onClick={onSignOut}>Sign out this browser</button><button className={secondary} onClick={onClose}>Close</button></div>
  </section></div>;
}
export function WorkspaceStatus() {
  const state = useResource('/health/system-metrics', 15000);
  return <section className={`${panel} mb-5 !p-3 flex flex-wrap items-center gap-4 text-xs`}><Activity size={16}/><span>API: {state.error ? 'unavailable' : state.data?.status || 'checking'}</span><span>Mode: {state.data?.execution_mode || 'unknown'}</span>
    {Object.entries(state.data?.subsystems_status || {}).filter(([key]) => ['database', 'redis', 'qdrant'].includes(key)).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}<ErrorBox error={state.error}/></section>;
}
type Props = {tab: string; meetings: any[]; meetingId: string; select: (id: string) => void; refresh: () => Promise<void>; auth: any; navigate: (tab: any) => void; hasMoreMeetings:boolean; loadMoreMeetings:()=>Promise<void>};
export function WorkspacePanels(props: Props) {
  const {tab, meetings, meetingId, select, auth} = props;
  const pagination = useRequest();
  const meeting = meetings.find(m => m.id === meetingId);
  const needsMeeting = ['live_stream','intelligence','queries','knowledge','translations','reports'].includes(tab);
  return <div className="space-y-5">
    {props.hasMoreMeetings && <div className="space-y-2"><button className={secondary} disabled={pagination.busy} onClick={() => pagination.run(props.loadMoreMeetings)}>{pagination.busy ? 'Loading meetings…' : 'Load more meetings'}</button><ErrorBox error={pagination.error}/></div>}
    {needsMeeting && <label className="block text-xs text-slate-400">Meeting<select aria-label="Selected meeting" className={`${input} mt-1`} value={meetingId} onChange={e => select(e.target.value)}><option value="">Select a meeting</option>{meetings.map(m => <option key={m.id} value={m.id}>{m.title} · {m.status}</option>)}</select></label>}
    {needsMeeting && !meeting ? <section className={panel}><Empty>Create or select a meeting to continue.</Empty><button className={button} onClick={() => props.navigate('meetings')}>Open meetings</button></section> : <div key={needsMeeting ? meetingId : tab} className="space-y-5">
      {tab === 'meetings' && <Meetings {...props}/>}
      {tab === 'projects' && <Projects meetings={meetings} select={select} navigate={props.navigate}/>}
      {tab === 'live_stream' && <RealLiveWorkspace key={meetingId} embedded={{token: auth.token, tenant: auth.tenant_id, meetingId}}/>}
      {tab === 'intelligence' && <Intelligence id={meetingId}/>}
      {tab === 'queries' && <Queries id={meetingId}/>}
      {tab === 'knowledge' && <Knowledge id={meetingId}/>}
      {tab === 'translations' && <Translations id={meetingId}/>}
      {tab === 'reports' && <Reports id={meetingId}/>}
    </div>}
    {tab === 'benchmarks' && <><Remote path="/benchmarks/runs" title="Persisted benchmark runs"/><Remote path="/benchmarks/datasets" title="Dataset adapters & execution requirements"/><p className="text-sm text-slate-400">Missing accuracy values are unknown. Benchmark execution remains in the existing CLI pending dataset and ground-truth validation.</p></>}
    {tab === 'security' && <><Remote path="/admin/audit" title="Persisted audit events"/><Remote path="/admin/users" title="Users"/><Remote path="/admin/roles" title="Server permissions"/></>}
    {tab === 'api_console' && <ApiConsole meetingId={meetingId}/>}
    {tab === 'system_health' && <HealthDashboard/>}
  </div>;
}
function Projects({meetings, select, navigate}: Pick<Props, 'meetings' | 'select' | 'navigate'>) {
  const [offset, setOffset] = useState(0), [projectId, setProjectId] = useState(''), [name, setName] = useState(''), [description, setDescription] = useState('');
  const state = useResource(`/projects?limit=50&offset=${offset}`), request = useRequest();
  return <><section className={panel}><div className="flex justify-between"><h2 className="text-xl font-semibold">Projects & cross-meeting intelligence</h2><button className={secondary} onClick={state.refresh}>Refresh</button></div>
    <form className="grid gap-3 sm:grid-cols-3" onSubmit={e => {e.preventDefault(); void request.run(async () => {const created = await write('/projects', {name:name.trim(), description}); setName(''); setDescription(''); setOffset(0); state.refresh(); setProjectId(created.id);});}}>
      <input aria-label="Project name" className={input} placeholder="New project name" required maxLength={255} value={name} onChange={e => setName(e.target.value)}/><input aria-label="Project description" className={input} placeholder="Description" value={description} onChange={e => setDescription(e.target.value)}/><button className={button} disabled={request.busy || !name.trim()}>Create project</button>
    </form><ErrorBox error={request.error || state.error}/>
    <div className="grid sm:grid-cols-2 gap-3">{rows(state.data).map(project => <button key={project.id} className={`text-left p-4 rounded-lg border ${projectId === project.id ? 'border-indigo-500 bg-indigo-950' : 'border-slate-700'}`} onClick={() => setProjectId(project.id)}><h3>{project.name}</h3><p className="text-sm text-slate-400">{project.status} · {project.meeting_count} meetings</p><p className="text-sm">{project.description}</p></button>)}</div>
    {!state.loading && !rows(state.data).length && <Empty>No projects in this workspace.</Empty>}<div className="flex gap-3 items-center"><button className={secondary} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset-50))}>Previous</button><span className="text-sm">{state.data?.total ?? '…'} projects</span><button className={secondary} disabled={offset+50 >= (state.data?.total ?? 0)} onClick={() => setOffset(offset+50)}>Next</button></div>
  </section>{projectId && <ProjectDetails key={projectId} id={projectId} meetings={meetings} openMeeting={id => {select(id); navigate('intelligence');}} changed={state.refresh} removed={() => {setProjectId(''); state.refresh();}}/>}</>;
}
function ProjectDetails({id, meetings, openMeeting, changed, removed}: {key?:string; id:string; meetings:any[]; openMeeting:(id:string)=>void; changed:()=>void; removed:()=>void}) {
  const project = useResource(`/projects/${id}`), [offset,setOffset] = useState(0), associations = useResource(`/projects/${id}/meetings?limit=50&offset=${offset}`), request = useRequest();
  const [name, setName] = useState(''), [description,setDescription] = useState(''), [status,setStatus] = useState('active'), [meeting,setMeeting] = useState(''), [view,setView] = useState('summary'), [revision,setRevision] = useState(0);
  useEffect(() => {if (project.data) {setName(project.data.name); setDescription(project.data.description || ''); setStatus(project.data.status);}}, [project.data]);
  const refresh = () => {project.refresh(); associations.refresh(); changed(); setRevision(v => v+1);};
  return <section className={panel}><h3 className="font-semibold">{project.data?.name || 'Project details'}</h3><ErrorBox error={project.error || associations.error || request.error}/>
    <form className="grid gap-3" onSubmit={e => {e.preventDefault(); void request.run(async () => {await write(`/projects/${id}`, {name:name.trim(),description,status}, 'PATCH'); refresh();});}}>
      <label>Name<input className={input} value={name} onChange={e => setName(e.target.value)} required maxLength={255}/></label><label>Description<textarea className={input} value={description} onChange={e => setDescription(e.target.value)}/></label>
      <label>Status<select className={input} value={status} onChange={e => setStatus(e.target.value)}>{['active','archived','completed'].map(s => <option key={s}>{s}</option>)}</select></label><div className="flex gap-3"><button className={button} disabled={request.busy || !name.trim()}>Save project</button><button type="button" className={secondary} disabled={request.busy} onClick={() => {if (window.confirm('Delete this project and its associations? The meetings are retained.')) void request.run(async () => {await api(`/projects/${id}`,{method:'DELETE'}); removed();});}}>Delete project</button></div>
    </form><h4 className="font-semibold">Associated meetings</h4><form className="flex gap-3" onSubmit={e => {e.preventDefault(); void request.run(async () => {await write(`/projects/${id}/meetings`, {meeting_id:meeting}); setMeeting(''); refresh();});}}><select aria-label="Meeting to associate" className={input} required value={meeting} onChange={e => setMeeting(e.target.value)}><option value="">Select a meeting</option>{meetings.map(m => <option key={m.id} value={m.id}>{m.title}</option>)}</select><button className={button} disabled={request.busy || !meeting}>Add meeting</button></form>
    {rows(associations.data).map(link => <article key={link.id} className="flex justify-between gap-3 p-3 border border-slate-800 rounded-lg"><button className="text-left" onClick={() => openMeeting(link.meeting_id)}>{link.meeting_title} · {link.meeting_status}</button><button className={secondary} disabled={request.busy} onClick={() => request.run(async () => {await api(`/projects/${id}/meetings/${link.meeting_id}`,{method:'DELETE'}); refresh();})}>Remove association</button></article>)}
    <div className="flex gap-3"><button className={secondary} disabled={!offset} onClick={() => setOffset(Math.max(0,offset-50))}>Previous meetings</button><button className={secondary} disabled={offset+50 >= (associations.data?.total ?? 0)} onClick={() => setOffset(offset+50)}>Next meetings</button></div>
    <label>Cross-meeting view<select className={input} value={view} onChange={e => setView(e.target.value)}>{[['summary','Overview'],['action-items','Action items'],['decisions','Decisions'],['topics/recurring','Recurring topics'],['insights','Insights'],['historical-context','Timeline']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label><Remote key={`${view}-${revision}`} path={`/projects/${id}/${view}`} title="Persisted project intelligence"/>
    <Queries id={id} scope="project"/>
  </section>;
}
function HealthDashboard() {
  const state = useResource('/health/system-metrics', 15000), infrastructure = useResource('/health', 15000), [selected, setSelected] = useState('fastapi');
  const data = state.data, metric = (value:any, suffix='') => typeof value === 'number' ? `${value.toFixed(1)}${suffix}` : 'Not measured';
  const nodes = Object.entries(data?.subsystems_status || {});
  return <><section className={panel}><div className="flex items-center justify-between"><h2 className="text-xl font-semibold">System health & telemetry</h2><button className={secondary} onClick={() => {state.refresh(); infrastructure.refresh();}}><RefreshCw size={15}/>Probe now</button></div><ErrorBox error={state.error || infrastructure.error}/>
    <div className="grid sm:grid-cols-3 gap-3">{[['CPU',metric(data?.cpu?.total_percent,'%')],['Memory',metric(data?.memory?.used_mb,' MB')],['API uptime',metric(data?.uptime_seconds,' s')]].map(([name,value]) => <article key={name} className="border border-slate-800 rounded-xl p-4"><p className="text-xs text-slate-400">{name}</p><p className="text-2xl font-semibold mt-2">{value}</p></article>)}</div>
    <p className="text-xs text-slate-400">Last measurement: {data?.timestamp || 'not available'} · API host measurements; worker GPU utilization is not inferred.</p></section>
    <section className={panel}><h3 className="font-semibold">Infrastructure nodes</h3><div className="grid sm:grid-cols-3 gap-3">{nodes.map(([name,status]) => <button key={name} className={`p-4 rounded-xl border text-left ${name === selected ? 'border-indigo-500 bg-indigo-500/10' : 'border-slate-800 hover:bg-slate-800'}`} onClick={() => setSelected(name)}><div className="flex gap-2 items-center"><Database size={16}/><span>{name.replace('_',' ')}</span></div><p className={`text-sm mt-2 ${status === 'healthy' ? 'text-emerald-400' : 'text-amber-300'}`}>{String(status)}</p><p className="text-xs text-slate-400 mt-1">{metric(data?.subsystem_latencies?.[`${name}_ms`], ' ms')}</p></button>)}</div>
    <h4 className="font-medium text-sm">{selected} · observed details</h4><Json value={infrastructure.data?.services?.[selected] || {status:data?.subsystems_status?.[selected] || 'not measured'}}/>
    <p className="text-sm text-slate-400">GPU inference and worker progress are recorded in each meeting’s execution nodes. No readiness claim is made for idle workers without a heartbeat.</p></section></>;
}
function Meetings({meetings, meetingId, select, refresh, navigate}: Props) {
  const [showCreate, setCreate] = useState(false), [title, setTitle] = useState(''), [description, setDescription] = useState(''), [language, setLanguage] = useState('en');
  const [file, setFile] = useState<File | null>(null), [filter, setFilter] = useState(''), [audioURL, setAudioURL] = useState('');
  const request = useRequest(), meeting = meetings.find(m => m.id === meetingId), health = useResource('/health/system-metrics', 15000);
  const fixtureMode = health.data?.execution_mode === 'FIXTURE';
  const playbackMeeting = useRef(meetingId);
  playbackMeeting.current = meetingId;
  useEffect(() => {setFile(null); setAudioURL('');}, [meetingId]);
  useEffect(() => () => {if (audioURL) URL.revokeObjectURL(audioURL);}, [audioURL]);
  return <><section className={panel}><div className="flex justify-between items-center"><h2 className="text-xl font-semibold">Meetings & audio intake</h2><div className="flex gap-2"><button className={secondary} disabled={request.busy} onClick={() => request.run(refresh)}><RefreshCw size={16}/>Refresh</button><button className={button} onClick={() => setCreate(v => !v)}><Plus size={16}/>New meeting</button></div></div>
    <ErrorBox error={request.error}/>
    {showCreate && <form className="grid gap-3" onSubmit={e => {e.preventDefault(); void request.run(async () => {const created = await write('/meetings', {title, description, language}); await refresh(); select(created.id); setCreate(false); setTitle('');});}}>
      <label>Title<input aria-label="Meeting title" className={input} required maxLength={255} value={title} onChange={e => setTitle(e.target.value)}/></label>
      <label>Description<textarea className={input} value={description} onChange={e => setDescription(e.target.value)}/></label><label>Language code<input className={input} value={language} onChange={e => setLanguage(e.target.value)} required/></label><button className={button} disabled={request.busy}>Create meeting</button>
    </form>}
    <input aria-label="Filter meetings" className={input} placeholder="Search loaded meetings…" value={filter} onChange={e => setFilter(e.target.value)}/>
    <div className="grid sm:grid-cols-2 gap-3">{meetings.filter(m => `${m.title} ${m.description}`.toLowerCase().includes(filter.toLowerCase())).map(m => <button key={m.id} onClick={() => select(m.id)} className={`text-left p-4 rounded-xl border ${m.id === meetingId ? 'border-indigo-500 bg-indigo-500/10' : 'border-slate-800 hover:bg-slate-800'}`}><p className="font-semibold">{m.title}</p><p className="text-xs text-slate-400 mt-2">{m.status} · {m.language}</p><p className="text-xs mt-2 truncate">{m.id}</p></button>)}</div>{!meetings.length && <Empty>No meetings in this authorized workspace.</Empty>}
    </section>{meeting && <section className={panel}><div className="flex justify-between"><h3 className="font-semibold">{meeting.title}</h3><span className="text-sm text-indigo-300">{meeting.status}</span></div><p className="text-sm text-slate-400">{meeting.description}</p>
      <div className="flex flex-wrap gap-2"><button className={button} onClick={() => navigate('intelligence')}><FileText size={15}/>Transcript & intelligence</button><button className={secondary} onClick={() => navigate('live_stream')}><Radio size={15}/>Live session</button>
      <button className={secondary} disabled={request.busy || !meeting.audio_recordings?.length || ['running','processing_requested','completed'].includes(meeting.status)} onClick={() => request.run(async () => {const result = await write(`/meetings/${meetingId}/${fixtureMode ? 'process' : 'process-async'}`, {}); if (result.status === 'failed') throw new Error(result.message); await refresh();})}><Play size={15}/>Process uploaded audio</button>
      {meeting.status === 'processing_requested' && <button className={secondary} disabled={request.busy} onClick={() => request.run(async () => {await write(`/meetings/${meetingId}/processing/cancel`, {}); await refresh();})}>Cancel queued upload</button>}
      <button className={secondary} disabled={request.busy || ['running','processing_requested'].includes(meeting.status)} onClick={() => {if (window.confirm(`Delete meeting “${meeting.title}” and its records?`)) void request.run(async () => {await api(`/meetings/${meetingId}`, {method: 'DELETE'}); select(''); await refresh();});}}>Delete meeting</button></div>
      <form className="flex flex-wrap gap-3 items-center" onSubmit={e => {e.preventDefault(); if (!file) return; void request.run(async () => {const form = new FormData(); form.set('file', file); form.set('format', file.name.split('.').pop() || 'wav'); await api(`/meetings/${meetingId}/audio`, {method:'POST', body:form}); setFile(null); await refresh();});}}><input aria-label="Audio file" type="file" accept=".wav,.mp3,.flac,.m4a,.ogg,.webm" onChange={e => setFile(e.target.files?.[0] || null)}/><button className={secondary} disabled={!file || request.busy || ['running','processing_requested'].includes(meeting.status)}><Upload size={15}/>Upload audio</button></form>
      {(meeting.audio_recordings || []).map((a: any) => <div key={a.id} className="flex gap-3 items-center text-sm"><span>{a.file_name} · {a.duration_seconds == null ? 'duration unmeasured' : `${a.duration_seconds}s`}</span><button className={secondary} onClick={() => request.run(async () => {const res = await response(`/meetings/${meetingId}/audio/${a.id}/content`); const blob = await res.blob(); if (playbackMeeting.current === meetingId) setAudioURL(URL.createObjectURL(blob));})}>Load playback</button></div>)}{audioURL && <audio aria-label="Meeting audio" controls src={audioURL} className="w-full"/>}
      <MeetingSettings key={meetingId} meeting={meeting} refresh={refresh}/>
      <details><summary className="cursor-pointer text-sm">Meeting metadata & participants</summary><Json value={meeting}/></details>
    </section>}{meeting && <Pipeline id={meetingId}/>}</>;
}
function MeetingSettings({meeting, refresh}: {key?:string; meeting:any; refresh:()=>Promise<void>}) {
  const request = useRequest(), [title,setTitle] = useState(meeting.title), [description,setDescription] = useState(meeting.description || ''), [start,setStart] = useState(''), [duration,setDuration] = useState(meeting.duration_minutes || 60);
  return <details className="border border-slate-800 rounded-lg p-3"><summary className="cursor-pointer text-sm">Edit details & schedule</summary><div className="space-y-4 mt-3"><ErrorBox error={request.error}/>
    <form className="space-y-2" onSubmit={e => {e.preventDefault(); void request.run(async()=>{await write(`/meetings/${meeting.id}`, {title,description}, 'PUT'); await refresh();});}}><label>Title<input className={input} required maxLength={255} value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Description<textarea className={input} value={description} onChange={e=>setDescription(e.target.value)}/></label><button className={secondary} disabled={request.busy}>Save details</button></form>
    <form className="space-y-2" onSubmit={e=>{e.preventDefault(); void request.run(async()=>{await write(`/meetings/${meeting.id}/${meeting.status === 'scheduled' ? 'reschedule' : 'schedule'}`, {scheduled_start:new Date(start).toISOString(),duration_minutes:Number(duration),timezone:Intl.DateTimeFormat().resolvedOptions().timeZone}); await refresh();});}}><label>Start in your local time<input className={input} required type="datetime-local" value={start} onChange={e=>setStart(e.target.value)}/></label><label>Scheduled duration (minutes)<input className={input} type="number" min={1} value={duration} onChange={e=>setDuration(Number(e.target.value))}/></label><button className={secondary} disabled={request.busy || !['created','scheduled','failed'].includes(meeting.status)}>Save schedule</button></form>
  </div></details>;
}
function Pipeline({id}: {id: string}) {
  const state = useResource(`/meetings/${id}/pipeline`, 5000, true), [node, setNode] = useState<any>(null);
  useEffect(() => setNode(null), [id]);
  const tasks = (state.data?.jobs || []).flatMap((job: any) => job.result?.ace_tasks || []);
  return <section className={panel}><div className="flex justify-between"><h3 className="font-semibold">ACE / Blackboard execution</h3><button className={secondary} onClick={state.refresh}><RefreshCw size={14}/>Refresh</button></div><ErrorBox error={state.error}/>
    <p className="text-xs text-slate-400">Observed state: {state.data?.status || 'unknown'} · Canonical transcript: {state.data?.canonical_transcript_id || 'not available'}</p>
    {state.data?.chunk_progress && <p role="status" className="text-sm text-indigo-300">Saved audio chunks: {state.data.chunk_progress.completed_chunks_count ?? 'unknown'} / {state.data.chunk_progress.total_chunks ?? 'unknown'} · {state.data.chunk_progress.overall_status} · checkpoint {state.data.chunk_progress.checkpoint_version ?? 'unavailable'}</p>}
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">{tasks.map((task: any) => <button key={task.id} className="text-left p-3 rounded-lg border border-slate-700 hover:border-indigo-400" onClick={() => setNode(task)}><span className="text-sm font-medium">{task.capability}</span><p className="text-xs text-slate-400 mt-2">{task.status}</p></button>)}</div>
    {!tasks.length && <Empty>No persisted ACE node results for this meeting yet. Pending work is not marked complete.</Empty>}
    {node && <section><div className="flex justify-between"><h4>{node.capability} · actual output</h4><button className={secondary} onClick={() => setNode(null)}>Close</button></div><Json value={node}/></section>}
    {(state.data?.jobs || []).map((job: any) => <details key={job.id} className="border border-slate-800 rounded-lg p-3"><summary className="cursor-pointer text-sm">{job.kind} · {job.status} · {job.id}</summary><Json value={job}/></details>)}
    {state.data?.provenance && <details><summary className="cursor-pointer text-sm">Canonical provenance, speaker mapping & deduplication</summary><Json value={state.data.provenance}/></details>}
  </section>;
}
function Intelligence({id}: {id: string}) {
  const [tab, setTab] = useState('transcript'), [search, setSearch] = useState('');
  const request = useRequest(), provider = useResource('/ai/text-status'), [generation,setGeneration] = useState<any>(null);
  const transcript = useResource(`/meetings/${id}/transcript`);
  const [transcriptPage,setTranscriptPage] = useState(0);
  useEffect(()=>setTranscriptPage(0),[id,search]);
  const filteredSegments = rows(transcript.data).filter(s => `${s.original_text} ${s.speaker_label}`.toLowerCase().includes(search.toLowerCase()));
  const sections = ['transcript','summary','decisions','action-items','topics','facts','hypotheses','insights','analytics','pipeline'];
    return <><section className={panel}><h2 className="text-xl font-semibold">Meeting intelligence</h2><p className="text-sm text-slate-400">Generate summaries, decisions, actions and topics from the saved transcript using Gemini. Text is sent to Google; generated interpretations require review.</p><button className={button} disabled={request.busy || !transcript.data?.length || !provider.data?.configured} onClick={() => request.run(async () => {setGeneration(await write(`/meetings/${id}/intelligence/generate`, {})); setTab('pipeline');})}>Generate intelligence from transcript</button><p className="text-xs text-slate-400">Text provider: {provider.data?.provider || 'checking'} · {provider.data?.model || ''} · credential: {provider.data?.credential || 'unknown'}</p><ErrorBox error={request.error || provider.error}/>{generation && <p role="status" className="text-sm">Job {generation.job_id}: {generation.status}. Progress and saved results appear in execution nodes.</p>}<div className="flex flex-wrap gap-2">{sections.map(key => <button key={key} className={tab === key ? button : secondary} onClick={() => setTab(key)}>{key.replace('-', ' ')}</button>)}</div></section>
    {tab === 'transcript' ? <section className={panel}><div className="flex flex-wrap gap-2"><input aria-label="Search transcript" className={`${input} flex-1`} placeholder="Find in transcript…" value={search} onChange={e => setSearch(e.target.value)}/><button className={secondary} onClick={transcript.refresh}>Refresh</button><button className={secondary} disabled={!transcript.data?.length} onClick={() => download(new Blob([JSON.stringify(transcript.data,null,2)], {type:'application/json'}), `transcript-${id}.json`)}><Download size={15}/>Export JSON</button></div><ErrorBox error={transcript.error}/>
      {filteredSegments.slice(transcriptPage*100,(transcriptPage+1)*100).map(s => <article key={s.segment_id} className="p-4 border border-slate-800 rounded-xl"><div className="text-xs text-indigo-300 mb-2">{(s.start_time_ms/1000).toFixed(2)}–{(s.end_time_ms/1000).toFixed(2)}s · {s.speaker_label || 'Speaker not identified'} · {s.language || 'und'}</div><p>{s.original_text}</p><p className="text-xs text-slate-500 mt-2">Confidence: {s.confidence == null ? 'not provided by model' : s.confidence}</p></article>)}{!rows(transcript.data).length && <Empty>No persisted transcript segments.</Empty>}
      {filteredSegments.length > 100 && <div className="flex items-center gap-3"><button className={secondary} disabled={transcriptPage===0} onClick={()=>setTranscriptPage(p=>p-1)}>Previous segments</button><span className="text-xs text-slate-400">{transcriptPage*100+1}–{Math.min((transcriptPage+1)*100,filteredSegments.length)} of {filteredSegments.length}</span><button className={secondary} disabled={(transcriptPage+1)*100>=filteredSegments.length} onClick={()=>setTranscriptPage(p=>p+1)}>Next segments</button></div>}
    </section> : tab === 'pipeline' ? <Pipeline id={id}/> : tab === 'action-items' ? <Actions id={id}/> : <Remote key={tab} path={`/meetings/${id}/${tab}`} title={tab}/>}</>;
}
function Actions({id}: {id: string}) {
  const [offset,setOffset] = useState(0), [editing,setEditing] = useState<any>(null);
  const state = useResource(`/meetings/${id}/action-items?limit=50&offset=${offset}`), request = useRequest();
  return <section className={panel}><div className="flex justify-between"><h3 className="font-semibold">Action items</h3><button className={button} onClick={() => setEditing({})}>Add action item</button></div><ErrorBox error={state.error || request.error}/>
    {editing && <ActionEditor key={editing.id || 'new'} item={editing} save={async values => {await write(editing.id ? `/action-items/${editing.id}` : `/meetings/${id}/action-items`, values, editing.id ? 'PATCH' : 'POST'); setEditing(null); state.refresh();}} close={() => setEditing(null)}/>}
    {rows(state.data).map(item => <article key={item.id} className="border border-slate-800 p-4 rounded-lg space-y-3"><h4>{item.title}</h4><p>{item.description}</p><p className="text-xs text-slate-400">{item.status} · {item.priority} · {item.assignee || 'Unassigned'} · Due: {item.due_date || 'not set'}</p><div className="flex gap-2"><button className={secondary} onClick={() => setEditing(item)}>Edit</button><button className={secondary} disabled={request.busy || item.status === 'completed'} onClick={() => request.run(async () => {await write(`/action-items/${item.id}/complete`, {}); state.refresh();})}>Mark completed</button><button className={secondary} disabled={request.busy || item.status === 'cancelled'} onClick={() => request.run(async () => {await write(`/action-items/${item.id}/cancel`, {}); state.refresh();})}>Cancel item</button></div><details><summary>Source & change history</summary><Json value={item}/></details></article>)}{!rows(state.data).length && <Empty/>}
    <div className="flex gap-3"><button className={secondary} disabled={!offset} onClick={() => setOffset(Math.max(0,offset-50))}>Previous</button><button className={secondary} disabled={offset+50 >= (state.data?.total ?? 0)} onClick={() => setOffset(offset+50)}>Next</button></div></section>;
}
function ActionEditor({item, save, close}: {key?:string; item:any; save:(values:any)=>Promise<void>; close:()=>void}) {
  const [values,setValues] = useState({title:item.title || '', description:item.description || '', assignee:item.assignee || '', due_date:item.due_date || '', priority:item.priority || 'medium', status:item.status || 'open'});
  const request=useRequest();
  return <form className="border border-indigo-700 rounded-lg p-4 space-y-3" onSubmit={e => {e.preventDefault(); void request.run(() => save({...values, title:values.title.trim(), assignee:values.assignee || null, due_date:values.due_date || null}));}}>
    <p className="text-xs text-slate-400">Changes are recorded as user input with your identity and timestamp.</p>
    {(['title','description','assignee','due_date'] as const).map(field => <label key={field} className="block text-sm">{field.replace('_',' ')}<input className={input} value={values[field]} required={field === 'title'} maxLength={field === 'title' ? 255 : field === 'assignee' ? 150 : undefined} onChange={e => setValues({...values,[field]:e.target.value})}/></label>)}
    <label className="block text-sm">Priority<select className={input} value={values.priority} onChange={e => setValues({...values,priority:e.target.value})}>{['low','medium','high','critical'].map(s => <option key={s}>{s}</option>)}</select></label>
    <label className="block text-sm">Status<select className={input} value={values.status} onChange={e => setValues({...values,status:e.target.value})}>{['open','in_progress','completed','cancelled'].map(s => <option key={s}>{s}</option>)}</select></label>
    <ErrorBox error={request.error}/><div className="flex gap-3"><button className={button} disabled={request.busy || !values.title.trim()}>Save action item</button><button type="button" className={secondary} onClick={close}>Close editor</button></div>
  </form>;
}
function Queries({id, scope = 'meeting'}: {id: string; scope?: 'meeting' | 'project'}) {
  const [query, setQuery] = useState(''), [result, setResult] = useState<any>(null), [mode,setMode] = useState('hybrid'), [offset,setOffset] = useState(0);
  const request = useRequest(), history = useResource(`/queries?${scope}_id=${id}&limit=20&offset=${offset}`);
  useEffect(() => {setResult(null); setQuery(''); setOffset(0);}, [id, scope]);
  async function ask() {
    const answer = await write('/queries', {query, [`${scope}_id`]:id, scope, retrieval_mode:mode});
    setResult(answer); setOffset(0); history.refresh();
    if (answer.status === 'failed') throw new Error('Answer generation failed. The saved failure remains in query history.');
  }
  return <><form className={panel} onSubmit={e => {e.preventDefault(); void request.run(ask);}}>
    <h2 className="text-xl font-semibold">Ask ABCI-MI · {scope}</h2>
    <textarea aria-label={`${scope} question`} className={input} placeholder={`Ask about this ${scope}’s recorded knowledge…`} value={query} onChange={e => setQuery(e.target.value)} required maxLength={2000}/>
    <label>Retrieval<select aria-label="Query retrieval mode" className={input} value={mode} onChange={e => setMode(e.target.value)}>{[['hybrid','Text and semantic search'],['structured','Text search'],['semantic','Semantic search']].map(([value,label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <button className={button} disabled={request.busy || !query.trim()}><Search size={15}/>{request.busy ? 'Generating answer…' : `Ask ${scope}`}</button><ErrorBox error={request.error}/>
    {result && <article className="space-y-3" aria-live="polite"><p className="text-xs text-amber-300">{result.status.replaceAll('_',' ')} · Confidence: {result.confidence ?? 'not measured'}</p><p className="text-sm whitespace-pre-wrap">{result.answer}</p>
      {(result.sources || []).map((source:any) => <details key={source.knowledge_id} className="border border-slate-700 rounded-lg p-3"><summary className="cursor-pointer text-sm">Source: {source.title || source.object_type} · {source.meeting_title}</summary><p className="text-sm whitespace-pre-wrap mt-2">{source.content}</p><p className="text-xs text-slate-400 mt-2">{source.knowledge_id} · Version {source.version}</p></details>)}
      <details><summary>Generation & source provenance</summary><Json value={result}/></details></article>}
  </form><section className={panel}><div className="flex justify-between"><h3>Persisted query history</h3><button className={secondary} onClick={history.refresh}>Refresh</button></div><ErrorBox error={history.error}/>
    {rows(history.data).map(item => <article key={item.query_id} className="border border-slate-800 rounded-lg p-3 space-y-2"><button className="text-left text-sm text-indigo-300" onClick={() => setResult(item)}>{item.query}</button><p className="text-xs text-slate-400">{item.status} · {new Date(item.created_at).toLocaleString()}</p><button className={secondary} disabled={request.busy} onClick={() => {if (window.confirm('Generate a new answer from the current saved knowledge?')) void request.run(async () => {const answer = await write(`/queries/${item.query_id}/regenerate`,{}); setResult(answer); history.refresh(); if (answer.status === 'failed') throw new Error('Answer regeneration failed.');});}}>Regenerate answer</button></article>)}
    {!history.loading && !rows(history.data).length && <Empty>No saved questions in this {scope}.</Empty>}<div className="flex gap-3"><button className={secondary} disabled={!offset} onClick={() => setOffset(Math.max(0,offset-20))}>Previous questions</button><button className={secondary} disabled={offset+20 >= (history.data?.total ?? 0)} onClick={() => setOffset(offset+20)}>Next questions</button></div>
  </section></>;
}
function Knowledge({id}: {id: string}) {
  const state = useResource(`/knowledge/meeting/${id}`), request = useRequest(); const [query, setQuery] = useState(''), [results, setResults] = useState<any>(null);
  return <section className={panel}><h2 className="text-xl font-semibold">Knowledge warehouse</h2><form className="flex gap-2" onSubmit={e => {e.preventDefault(); void request.run(async () => setResults(await write('/knowledge/search', {query, meeting_id:id, limit:20})));}}><input className={input} aria-label="Knowledge search" placeholder="Semantic search in this meeting" required value={query} onChange={e => setQuery(e.target.value)}/><button className={button} disabled={request.busy}>Search</button><button type="button" className={secondary} onClick={() => {setResults(null); setQuery(''); state.refresh();}}>Reset</button></form><ErrorBox error={state.error || request.error}/><RecordList value={results ?? state.data}/></section>;
}
function Translations({id}: {id: string}) {
  const [language, setLanguage] = useState('hi'), [representation,setRepresentation] = useState('transcript'), [offset,setOffset] = useState(0);
  const state = useResource(`/meetings/${id}/translations?limit=50&offset=${offset}`), request = useRequest();
  return <section className={panel}><h2 className="text-xl font-semibold">Derived translations</h2><p className="text-sm text-slate-400">Gemini translates saved source text. Originals stay unchanged; translations require review. Existing translations are reused.</p><form className="flex flex-wrap gap-3" onSubmit={e => {e.preventDefault(); void request.run(async () => {await write(`/meetings/${id}/translations`, {target_language: language, representation_types:[representation]}); setOffset(0); state.refresh();});}}>
    <label>Target language<select aria-label="Translation language" className={input} value={language} onChange={e => setLanguage(e.target.value)}>{[['en','English'],['hi','Hindi'],['ta','Tamil'],['te','Telugu'],['kn','Kannada'],['ml','Malayalam'],['bn','Bengali'],['mr','Marathi'],['gu','Gujarati'],['pa','Punjabi'],['zh','Chinese'],['ja','Japanese'],['fr','French'],['es','Spanish'],['de','German'],['ru','Russian'],['ar','Arabic']].map(([code,label]) => <option key={code} value={code}>{label}</option>)}</select></label>
    <label>Source<select className={input} value={representation} onChange={e => setRepresentation(e.target.value)}>{['transcript','summary','decision','action_item','topic','fact','hypothesis'].map(s => <option key={s}>{s}</option>)}</select></label><button className={button} disabled={request.busy}>{request.busy ? 'Translating…' : 'Translate saved text'}</button></form><ErrorBox error={state.error || request.error}/>
    {rows(state.data).map(t => <article key={t.id} className="border border-slate-800 rounded-lg p-4 space-y-3"><p className="text-xs text-indigo-300">{t.representation_type} · {t.source_language} → {t.target_language} · Version {t.version}</p><p className="text-sm text-slate-400">{t.original_text}</p><p lang={t.target_language} dir="auto">{t.translated_text}</p><p className="text-xs text-amber-300">{t.requires_verification ? 'Needs review' : 'Review status recorded'} · Confidence: {t.confidence ?? 'not measured'}</p><button className={secondary} disabled={request.busy} onClick={() => {if (window.confirm('Request a new Gemini translation of this source?')) void request.run(async () => {await write(`/translations/${t.id}/regenerate`,{}); state.refresh();});}}>Regenerate</button><details><summary>Source & generation history</summary><Json value={t}/></details></article>)}
    {!rows(state.data).length && <Empty>No translations saved yet.</Empty>}<div className="flex gap-3"><button className={secondary} disabled={!offset} onClick={() => setOffset(Math.max(0,offset-50))}>Previous</button><button className={secondary} disabled={offset+50 >= (state.data?.total ?? 0)} onClick={() => setOffset(offset+50)}>Next</button></div></section>;
}
function Reports({id}: {id: string}) {
  const state = useResource(`/meetings/${id}/reports`), request = useRequest(); const [format, setFormat] = useState('markdown');
  return <section className={panel}><h2 className="text-xl font-semibold">Reports & exports</h2><form className="flex gap-3" onSubmit={e => {e.preventDefault(); void request.run(async () => {await write(`/meetings/${id}/reports`, {format, report_type:'comprehensive'}); state.refresh();});}}><select className={input} aria-label="Report format" value={format} onChange={e => setFormat(e.target.value)}>{['html','json','markdown','txt','pdf'].map(f => <option key={f} value={f}>{f === 'html' ? 'Printable HTML (all languages)' : f}</option>)}</select><button className={button} disabled={request.busy}>Generate report</button></form><ErrorBox error={state.error || request.error}/>
    {rows(state.data).map(report => <article key={report.id} className="p-4 border border-slate-800 rounded-lg space-y-3"><p>{report.report_type} · {report.format} · {report.status}</p><button className={secondary} disabled={request.busy} onClick={() => request.run(async () => {const exported = await write(`/reports/${report.id}/export`, {format:report.format}); const path = exported.download_url.replace(/^\/api\/v1/, ''); const res = await response(path); download(await res.blob(), exported.filename);})}><Download size={15}/>Download</button><details><summary>Report sections & provenance</summary><Json value={report}/></details></article>)}{!rows(state.data).length && <Empty/>}</section>;
}
function ApiConsole({meetingId}: {meetingId: string}) {
  const schema = useResource('/openapi.json'), request = useRequest(); const [filter, setFilter] = useState(''), [selected, setSelected] = useState<any>(null), [path, setPath] = useState(''), [body, setBody] = useState('{}'), [result, setResult] = useState<any>(null);
  const endpoints = Object.entries(schema.data?.paths || {}).flatMap(([path, methods]: any) => Object.entries(methods).filter(([method]) => ['get','post','put','patch','delete'].includes(method)).map(([method, spec]: any) => ({path, method:method.toUpperCase(), spec})));
  return <section className={panel}><h2 className="text-xl font-semibold">API console · {endpoints.length} actual operations</h2><ErrorBox error={schema.error || request.error}/><input className={input} aria-label="Filter endpoints" placeholder="Filter endpoint or description…" value={filter} onChange={e => setFilter(e.target.value)}/><div className="grid lg:grid-cols-2 gap-4"><div className="max-h-[600px] overflow-auto space-y-1">{endpoints.filter(e => `${e.method} ${e.path} ${e.spec.summary}`.toLowerCase().includes(filter.toLowerCase())).map(e => <button key={`${e.method}${e.path}`} className={`text-left p-3 w-full rounded-lg text-xs ${selected?.path === e.path && selected?.method === e.method ? 'bg-indigo-950' : 'hover:bg-slate-800'}`} onClick={() => {setSelected(e); setPath(e.path.replace('/api/v1','').replace('{meeting_id}',meetingId)); setResult(null); setBody('{}');}}><span className="text-indigo-300 font-mono">{e.method}</span> {e.path}<p className="text-slate-400 mt-1">{e.spec.summary}</p></button>)}</div>{selected && <form className="space-y-3" onSubmit={e => {e.preventDefault(); if (path.includes('{')) return; if (selected.method !== 'GET' && !window.confirm(`Execute ${selected.method} ${path}? This changes real application state.`)) return; void request.run(async () => {const start=performance.now(); const res=await response(path,{method:selected.method,...(selected.method === 'GET' ? {} : {body:JSON.stringify(JSON.parse(body))})}); const text=await res.text(); let payload:any=text; try{payload=JSON.parse(text);}catch{} setResult({http_status:res.status,elapsed_ms:performance.now()-start,body:payload});});}}><label className="text-sm">Path and query parameters<input aria-label="Request path" className={input} value={path} onChange={e => setPath(e.target.value)}/></label><p className="text-xs text-slate-400">Authentication uses the connected session. Fill path parameters and required fields from the schema below. Use Meetings for file uploads.</p>{selected.method !== 'GET' && <textarea aria-label="Request JSON" className={`${input} font-mono h-44`} value={body} onChange={e => setBody(e.target.value)}/>}<button className={button} disabled={request.busy || path.includes('{')}>Execute {selected.method}</button><details><summary>Operation schema</summary><Json value={selected.spec}/><Json value={schema.data?.components?.schemas}/></details>{result && <Json value={result}/>}</form>}</div></section>;
}
