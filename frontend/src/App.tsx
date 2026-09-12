import { useMemo } from 'react'
import { ArrowUpRight, CircleAlert, CircleCheck, Clock3, Database, ExternalLink, GitBranch, RefreshCw, ShieldCheck, Sparkles, Terminal, Wifi, X } from 'lucide-react'
import Pipeline from './Pipeline'
import UserPanel from './UserPanel'
import { useWorkspace } from './useWorkspace'

function formatTime(value: Date) {
  return value.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function App() {
  const workspace = useWorkspace()
  const status = workspace.snapshot?.status ?? null
  const modernReady = status?.v2_available ?? false
  const legacyReady = status?.v1_available ?? false
  const stageLabel = status?.stage === 'uninitialized' ? 'Not started' : status?.stage === 'contracted' ? 'Complete' : status?.stage ?? 'Connecting'
  const progress = useMemo(() => status?.stage === 'contracted' ? 100 : status?.stage === 'synchronized' ? 75 : status?.stage === 'expanded' ? 50 : status?.stage === 'initial' ? 25 : 0, [status?.stage])

  return <div className="app-shell">
    <header className="topbar">
      <a className="brand" href="/" aria-label="Migration Lab home"><span className="brand-mark"><GitBranch size={17} /></span><span>migration<span className="brand-accent">/</span>lab</span></a>
      <div className="topbar-right"><span className="environment"><span className="live-dot" /> Local environment</span><a href="/docs" target="_blank" rel="noreferrer" className="docs-link">API docs <ExternalLink size={13} /></a><span className="version-chip">MVP <span>0.1</span></span></div>
    </header>

    <main className="content">
      <section className="hero">
        <div className="hero-copy"><div className="kicker"><span className="kicker-line" /> DATABASE MIGRATION WORKSPACE</div><h1>Change the schema.<br /><em>Keep the system alive.</em></h1><p>A hands-on view of the expand → synchronize → contract pattern. Move through each stage and watch the legacy and modern APIs stay compatible.</p></div>
        <div className="hero-aside"><div className="status-card"><div className="status-card-top"><span className="eyebrow">CURRENT STAGE</span><span className={`stage-status ${status ? 'online' : ''}`}><span className="status-dot" />{status ? 'Connected' : 'Connecting'}</span></div><strong>{stageLabel}</strong><div className="progress-track"><span style={{ width: `${progress}%` }} /></div><div className="status-meta"><span>{progress}% complete</span><code>{status?.revision ? `revision ${status.revision}` : 'waiting for database'}</code></div></div><div className="hero-note"><Sparkles size={15} /><span>Built for exploring safely.<br /><b>Nothing happens without your click.</b></span></div></div>
      </section>

      {workspace.connectionError && <div className="connection-banner" role="alert"><CircleAlert size={18} /><div><strong>Backend unavailable</strong><span>{workspace.connectionError}</span></div><button className="icon-button" onClick={() => void workspace.refresh()} aria-label="Retry connection"><RefreshCw size={16} /></button></div>}
      {workspace.notice && <div className={`notice ${workspace.notice.kind}`} role="status"><span className="notice-icon">{workspace.notice.kind === 'success' ? <CircleCheck size={17} /> : <CircleAlert size={17} />}</span><span>{workspace.notice.text}</span><button className="icon-button" onClick={workspace.dismissNotice} aria-label="Dismiss message"><X size={15} /></button></div>}

      <Pipeline status={status} disabled={workspace.pending !== null || workspace.refreshing || Boolean(workspace.connectionError)} pending={workspace.pending === 'migration' || workspace.pending === 'retirement'} onAdvance={() => void workspace.advance()} onRetire={() => void workspace.retire()} />

      <section className="api-section" aria-labelledby="api-heading"><div className="section-heading api-section-heading"><div><span className="eyebrow">LIVE API VERSIONS</span><h2 id="api-heading">Same data. Different shape.</h2></div><button className="refresh-button" disabled={workspace.refreshing} onClick={() => void workspace.refresh()}><RefreshCw size={15} className={workspace.refreshing ? 'spin' : ''} />{workspace.refreshing ? 'Refreshing…' : 'Refresh data'}</button></div><div className="api-callout"><ShieldCheck size={17} /><span><strong>Compatibility is the point.</strong> Create a user through either version and see the trigger keep both representations in sync.</span></div><div className="user-panels"><UserPanel version="v1" available={legacyReady} retired={status?.v1_retired} users={workspace.snapshot?.legacy ?? null} error={workspace.snapshot?.legacyError ?? null} disabled={workspace.pending !== null || workspace.refreshing || Boolean(workspace.connectionError)} pending={workspace.pending === 'v1'} onCreate={workspace.create} /><div className="sync-bridge" aria-hidden="true"><span><Database size={15} /></span><i /><span><ArrowUpRight size={15} /></span></div><UserPanel version="v2" available={modernReady} users={workspace.snapshot?.modern ?? null} error={workspace.snapshot?.modernError ?? null} disabled={workspace.pending !== null || workspace.refreshing || Boolean(workspace.connectionError)} pending={workspace.pending === 'v2'} onCreate={workspace.create} /></div></section>

      <section className="activity-section" aria-labelledby="activity-heading"><div className="section-heading"><div><span className="eyebrow">REQUEST LOG</span><h2 id="activity-heading">What just happened.</h2></div><span className="log-status"><span className="status-dot" /> Live</span></div><div className="activity-log">{workspace.activities.length === 0 ? <div className="log-empty"><Terminal size={18} /><span>Requests you make will appear here.</span></div> : workspace.activities.map((item) => <div className="activity-row" key={item.id}><span className={`activity-symbol ${item.kind}`}>{item.kind === 'success' ? <CheckIcon /> : <CircleAlert size={15} />}</span><div className="activity-main"><strong>{item.title}</strong><span><code>{item.endpoint}</code>{item.code !== null && <span className="http-code">HTTP {item.code}</span>}</span></div><time dateTime={item.time.toISOString()}><Clock3 size={13} />{formatTime(item.time)}</time><details><summary>View</summary><pre>{JSON.stringify(item.detail, null, 2)}</pre></details></div>)}</div></section>
    </main>
    <footer className="footer"><span><span className="footer-mark"><Database size={13} /></span> PostgreSQL 15 · FastAPI · Alembic</span><span className="footer-center">EXPAND <i /> SYNCHRONIZE <i /> CONTRACT</span><span className="footer-health"><Wifi size={13} /> Local only · no data leaves your machine</span></footer>
  </div>
}

function CheckIcon() { return <CircleCheck size={15} /> }
