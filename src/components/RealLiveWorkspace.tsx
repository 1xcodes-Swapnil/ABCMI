import React, {useEffect, useRef, useState} from 'react';

type Segment = {segment_id: string; start_time: number; end_time: number; transcript: string; speaker_id?: string};
type Job = {id: string; chunk_id?: string; kind: string; status: string; error?: string;
  result?: {segments?: Segment[]; elapsed_seconds?: number; rtf?: number; canonical_transcript_id?: string}};
type LiveStatus = {session: {id: string; status: string; latest_sequence_number: number};
  pending_jobs: number; failed_jobs: number; chunk_seconds: number; overlap_seconds: number; jobs: Job[]};
type Pending = {sequence: number; start: number; end: number; wav: ArrayBuffer};

function wavPCM(samples: Float32Array, rate: number): ArrayBuffer {
  const data = new ArrayBuffer(44 + samples.length * 2), view = new DataView(data);
  const text = (at: number, s: string) => [...s].forEach((c, i) => view.setUint8(at+i, c.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, data.byteLength-8, true); text(8, 'WAVE'); text(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate*2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, samples.length*2, true);
  samples.forEach((sample, i) => view.setInt16(44+i*2, Math.round(Math.max(-1, Math.min(1, sample))*32767), true));
  return data;
}

export function RealLiveWorkspace({embedded}: {key?:string; embedded?: {token:string; tenant:string; meetingId:string}} = {}) {
  const [token, setToken] = useState(embedded?.token || ''), [tenant, setTenant] = useState(embedded?.tenant || '');
  const [base, setBase] = useState('/api/v1'), [meeting, setMeeting] = useState(embedded?.meetingId || '');
  const [title, setTitle] = useState('Live meeting'), [status, setStatus] = useState<LiveStatus | null>(null);
  const [error, setError] = useState(''), [recording, setRecording] = useState(false);
  const [connected, setConnected] = useState(false), [queued, setQueued] = useState(0);
  const [busy, setBusy] = useState(false), [finalTranscript, setFinalTranscript] = useState('');
  const capture = useRef<{ctx: AudioContext; stream: MediaStream; node: AudioWorkletNode; source: MediaStreamAudioSourceNode} | null>(null);
  const samples = useRef(new Float32Array(0)), offset = useRef(0), sequence = useRef(0);
  const pending = useRef<Pending[]>([]), sending = useRef(false), ending = useRef(false);
  const flushing = useRef<(() => void) | null>(null);
  const statusRef = useRef<LiveStatus | null>(null);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('abci:live-pending', {detail:recording || queued > 0 || ending.current}));
  }, [recording, queued, status]);
  useEffect(() => () => {window.dispatchEvent(new CustomEvent('abci:live-pending', {detail:false}));}, []);
  async function api(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers);
    headers.set('Authorization', `Bearer ${token}`);
    if (tenant) headers.set('X-Tenant-ID', tenant);
    const response = await fetch(base.replace(/\/$/, '') + path, {...init, headers});
    const payload = await response.json();
    if (!response.ok) {
      const err = new Error(payload?.error?.message || payload?.detail || payload?.message || `HTTP ${response.status}`);
      Object.assign(err, {status: response.status}); throw err;
    }
    return payload;
  }
  const livePath = `/meetings/${meeting}/live`;
  async function refresh() {
    const next: LiveStatus = await api(`${livePath}/status`);
    statusRef.current = next; setStatus(next); return next;
  }
  useEffect(() => {
    if (!connected) return;
    let mounted = true;
    const timer = setInterval(() => {refresh().catch(e => {if (mounted) setError(String(e.message));});}, 2000);
    return () => {mounted = false; clearInterval(timer);};
  }, [connected, meeting, base, token, tenant]);
  useEffect(() => () => {
    capture.current?.stream.getTracks().forEach(t => t.stop());
    void capture.current?.ctx.close();
  }, []);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (capture.current || pending.current.length || ending.current) {event.preventDefault(); event.returnValue = '';}
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, []);

  async function connect() {
    setBusy(true); setError('');
    try {await refresh(); setConnected(true);} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function create() {
    setBusy(true); setError('');
    try {
      const data = await api('/meetings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({title})});
      setMeeting(data.id); setStatus(null); setConnected(false);
    } catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function finishWhenUploaded() {
    if (ending.current && !pending.current.length && !sending.current) {
      await api(`${livePath}/stop`, {method: 'POST'});
      ending.current = false;
      await refresh();
    }
  }
  async function drain() {
    if (sending.current) return;
    sending.current = true;
    try {
      while (pending.current.length) {
        const chunk = pending.current[0], form = new FormData();
        const hash = await crypto.subtle.digest('SHA-256', chunk.wav);
        form.set('checksum', Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join(''));
        form.set('sequence_number', String(chunk.sequence)); form.set('timestamp_start_ms', String(chunk.start));
        form.set('timestamp_end_ms', String(chunk.end)); form.set('file', new Blob([chunk.wav], {type:'audio/wav'}), 'chunk.wav');
        await api(`${livePath}/chunks`, {method:'POST', body:form});
        pending.current.shift(); setQueued(pending.current.length);
      }
      setError('');
    } catch (e) {
      setError(`${(e as Error).message}. Audio remains in this tab; stop capture and retry pending uploads.`);
      if (capture.current) await stopCapture(false);
    } finally {sending.current = false;}
    await finishWhenUploaded();
  }
  function enqueue(data: Float32Array, rate: number) {
    pending.current.push({sequence: sequence.current++, start: Math.round(offset.current/rate*1000),
      end: Math.round((offset.current+data.length)/rate*1000), wav: wavPCM(data, rate)});
    setQueued(pending.current.length);
  }
  async function startCapture() {
    setBusy(true); setError('');
    try {
      const before = await refresh();
      if (before.session.status !== 'created') throw new Error('Start a new meeting for a new microphone capture. Existing sessions remain readable.');
      const stream = await navigator.mediaDevices.getUserMedia({audio: {channelCount:1}, video:false});
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      try {
        await ctx.audioWorklet.addModule('/audio-capture.js');
        const node = new AudioWorkletNode(ctx, 'abci-pcm-input');
        capture.current = {ctx, stream, source, node};
        await api(`${livePath}/start`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
        const config = await refresh();
        const windowFrames = Math.round(config.chunk_seconds*ctx.sampleRate);
        const stepFrames = Math.round((config.chunk_seconds-config.overlap_seconds)*ctx.sampleRate);
        samples.current = new Float32Array(0); offset.current = 0; sequence.current = 0; ending.current = false;
        node.port.onmessage = event => {
          if (event.data === 'flushed') {flushing.current?.(); flushing.current = null; return;}
          const next = new Float32Array(samples.current.length+event.data.length);
          next.set(samples.current); next.set(event.data, samples.current.length); samples.current = next;
          while (samples.current.length >= windowFrames) {
            enqueue(samples.current.slice(0, windowFrames), ctx.sampleRate);
            samples.current = samples.current.slice(stepFrames); offset.current += stepFrames;
            void drain().catch(e => setError((e as Error).message));
          }
          if (pending.current.length >= 6 && !flushing.current) {
            setError('Capture stopped because inference/uploads cannot keep up. Pending audio is retained in this tab.');
            void stopCapture(false);
          }
        };
        source.connect(node); const mute = ctx.createGain(); mute.gain.value = 0;
        node.connect(mute); mute.connect(ctx.destination); await ctx.resume(); setRecording(true);
      } catch (e) {stream.getTracks().forEach(t => t.stop()); await ctx.close(); capture.current = null; throw e;}
    } catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function stopCapture(send = true) {
    const active = capture.current;
    if (!active || flushing.current) return;
    setRecording(false); ending.current = true;
    active.source.disconnect(); active.stream.getTracks().forEach(t => t.stop());
    await new Promise<void>(resolve => {flushing.current = resolve; active.node.port.postMessage('flush');});
    await active.ctx.close(); capture.current = null;
    const overlap = Math.round((statusRef.current?.overlap_seconds || 0)*active.ctx.sampleRate);
    if (samples.current.length > (sequence.current ? overlap : 0)) enqueue(samples.current, active.ctx.sampleRate);
    samples.current = new Float32Array(0);
    if (send) await drain();
  }
  async function readTranscript() {
    try {setFinalTranscript(JSON.stringify(await api(`/meetings/${meeting}/transcript`), null, 2));}
    catch (e) {setError((e as Error).message);}
  }
  const captions = (status?.jobs || []).filter(j => j.kind === 'chunk' && j.status === 'completed');
  const locked = connected || recording || queued > 0;
  return <main className={embedded ? 'text-slate-100' : 'min-h-screen bg-slate-950 text-slate-100 p-6 md:p-10'}>
    <div className="max-w-5xl mx-auto space-y-6">
      <header><p className="text-cyan-400 text-sm">ABCI-MI · REAL execution</p><h1 className="text-3xl font-semibold mt-2">Live meeting workspace</h1>
        <p className="text-slate-400 mt-3">Microphone audio is saved as small overlapping chunks. Captions are provisional; speaker reconciliation and meeting intelligence run after capture ends.</p></header>
      {!embedded && <section className="border border-slate-700 rounded-xl p-5 grid sm:grid-cols-2 gap-4">
        <label>API base URL<input className="block w-full bg-slate-800 p-2 rounded mt-1" value={base} disabled={locked} onChange={e=>setBase(e.target.value)}/></label>
        <label>Authorized access token<input type="password" autoComplete="off" className="block w-full bg-slate-800 p-2 rounded mt-1" value={token} disabled={locked} onChange={e=>setToken(e.target.value)}/></label>
        <label>Tenant ID<input className="block w-full bg-slate-800 p-2 rounded mt-1" value={tenant} disabled={locked} onChange={e=>setTenant(e.target.value)}/></label>
        <label>Meeting ID<input className="block w-full bg-slate-800 p-2 rounded mt-1" value={meeting} disabled={locked} onChange={e=>setMeeting(e.target.value)}/></label>
        {!locked && <><label>New meeting title<input className="block w-full bg-slate-800 p-2 rounded mt-1" value={title} onChange={e=>setTitle(e.target.value)}/></label>
          <div className="flex gap-3 items-end"><button className="bg-slate-700 p-2 rounded disabled:opacity-40" disabled={busy || !token || !title} onClick={create}>Create meeting</button>
            <button className="bg-cyan-700 p-2 rounded disabled:opacity-40" disabled={busy || !token || !meeting} onClick={connect}>Connect</button></div></>}
        <p className="text-xs text-slate-400 sm:col-span-2">Credentials stay in memory. Use an existing authorized identity. HTTPS or localhost is required for microphone access.</p>
      </section>}
      {embedded && !connected && <button className="bg-indigo-600 p-3 rounded disabled:opacity-40" disabled={busy} onClick={connect}>Connect live session</button>}
      {error && <p role="alert" className="border border-amber-600 rounded p-4 text-amber-200">{error}</p>}
      {connected && <section className="border border-slate-700 rounded-xl p-5 space-y-4">
        <div className="flex flex-wrap gap-4"><span>Session: {status?.session.status}</span><span>Worker backlog: {status?.pending_jobs ?? 'unknown'}</span><span>Failed jobs: {status?.failed_jobs ?? 'unknown'}</span><span>Unsent chunks: {queued}</span></div>
        <div className="flex flex-wrap gap-3">
          <button className="bg-cyan-700 p-3 rounded disabled:opacity-40" disabled={busy || recording || status?.session.status !== 'created'} onClick={startCapture}>Start microphone</button>
          <button className="bg-slate-700 p-3 rounded disabled:opacity-40" disabled={!recording} onClick={()=>stopCapture().catch(e=>setError(e.message))}>Stop and finalize</button>
          <button className="bg-slate-700 p-3 rounded disabled:opacity-40" disabled={recording || (!queued && !ending.current)} onClick={()=>drain().catch(e=>setError(e.message))}>Retry pending uploads</button>
          <button className="bg-slate-700 p-3 rounded disabled:opacity-40" disabled={status?.session.status !== 'completed'} onClick={readTranscript}>Read persisted transcript</button>
        </div><p className="text-sm text-slate-400">Capture window {status?.chunk_seconds}s · overlap {status?.overlap_seconds}s. Overlapping preview captions may repeat; labels are local to each chunk until finalization.</p>
      </section>}
      <section className="space-y-3"><h2 className="text-xl">Observed captions</h2>
        {!captions.length && <p className="text-slate-400">No real transcript has been returned yet.</p>}
        {captions.map(job => <article key={job.id} className="border border-slate-700 p-4 rounded-xl">
          <p className="text-xs text-slate-400 mb-2">Chunk {job.chunk_id} · processing {job.result?.elapsed_seconds?.toFixed(2) ?? 'unknown'}s · RTF {job.result?.rtf?.toFixed(2) ?? 'unknown'}</p>
          {job.result?.segments?.map(s=><p key={s.segment_id} className="mb-2"><span className="text-cyan-400">{s.start_time.toFixed(2)}–{s.end_time.toFixed(2)}s · {s.speaker_id || 'Speaker unknown'} </span>{s.transcript}</p>)}
        </article>)}
        {status?.jobs.filter(j=>j.status==='failed').map(j=><p key={j.id} className="text-amber-300">{j.kind} failed: {j.error}</p>)}
      </section>
      {finalTranscript && <section><h2 className="text-xl mb-3">Persisted transcript</h2><pre className="whitespace-pre-wrap bg-slate-900 p-4 rounded">{finalTranscript}</pre></section>}
    </div>
  </main>;
}
