import { ArrowRight, Check, CircleCheck, Database, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react'
import type { DemoStatus, Stage } from './api'

export const steps = [
  { stage: 'initial', title: 'Initialize', description: 'Create the original schema', revision: '001' },
  { stage: 'expanded', title: 'Expand', description: 'Add the new name fields', revision: '002' },
  { stage: 'synchronized', title: 'Synchronize', description: 'Sync writes & backfill users', revision: '003' },
  { stage: 'contracted', title: 'Contract', description: 'Remove the legacy field', revision: '004' },
] as const

const actions: Record<Stage, { title: string; description: string; button: string }> = {
  uninitialized: { title: 'Start with the original schema', description: 'Create the users table with a full_name field. Then add a user through the legacy API.', button: 'Initialize database' },
  initial: { title: 'Give your schema room to grow', description: 'Add first_name and last_name while keeping the original field and legacy API available.', button: 'Expand schema' },
  expanded: { title: 'Bring both versions into sync', description: 'Backfill existing names and enable the trigger that keeps both API versions consistent.', button: 'Synchronize names' },
  synchronized: { title: 'Finish the transition', description: 'Remove full_name and the synchronization trigger. Your users stay available through the modern API.', button: 'Contract schema' },
  contracted: { title: 'Migration complete', description: 'The new schema is in place. Keep creating users through the modern API below.', button: 'Migration complete' },
}

interface Props {
  status: DemoStatus | null
  disabled: boolean
  pending: boolean
  onAdvance: () => void
  onRetire: () => void
}

export default function Pipeline({ status, disabled, pending, onAdvance, onRetire }: Props) {
  const applied = status ? steps.findIndex((step) => step.stage === status.stage) + 1 : 0
  const needsRetirement = status?.stage === 'synchronized' && !status.v1_retired
  const action = actions[status?.stage ?? 'uninitialized']
  const completed = status?.stage === 'contracted'

  return <section className="panel pipeline" aria-labelledby="pipeline-heading">
    <div className="section-heading"><div><span className="eyebrow">THE WORKFLOW</span><h2 id="pipeline-heading">One step at a time.</h2></div><span className="progress-count"><span>{applied}</span> / 4 steps applied</span></div>
    <ol className="steps" aria-label="Migration stages">{steps.map((step, index) => {
      const done = index < applied
      const current = index === applied && !completed
      return <li key={step.stage} className={`${done ? 'done' : ''} ${current ? 'current' : ''}`} aria-current={current ? 'step' : undefined}>
        <div className="step-track"><span className="step-number">{done ? <Check size={16} strokeWidth={2.6} /> : String(index + 1).padStart(2, '0')}</span><span className="step-connector" /></div>
        <div className="step-text"><strong>{step.title}</strong><p>{step.description}</p><code>{step.revision}</code></div>
      </li>
    })}</ol>
    <div className={`next-action ${completed ? 'complete' : ''}`}>
      <span className="action-icon">{completed ? <CircleCheck size={23} /> : needsRetirement ? <ShieldCheck size={23} /> : <Database size={22} />}</span>
      <div className="action-copy"><span className="eyebrow">{completed ? 'ALL SET' : needsRetirement ? 'BEFORE YOU CONTRACT' : 'UP NEXT'}</span><h3>{needsRetirement ? 'Ready to retire the legacy API?' : action.title}</h3><p>{needsRetirement ? 'Try both API versions below first. Retire v1 when you’re ready to use only the modern API.' : action.description}</p></div>
      {!completed && <button className={`button ${needsRetirement ? 'retire-button' : 'primary-button'}`} disabled={disabled || !(needsRetirement ? status?.can_retire_v1 : status?.can_migrate)} onClick={needsRetirement ? onRetire : onAdvance}>
        {pending ? <LoaderCircle size={16} className="spin" /> : !status?.controls_enabled && status ? <LockKeyhole size={16} /> : null}
        {pending ? 'Applying change…' : !status ? 'Connecting…' : !status.controls_enabled ? 'Controls disabled' : needsRetirement ? 'Retire legacy API' : action.button}
        {!pending && status?.controls_enabled && <ArrowRight size={16} />}
      </button>}
    </div>
  </section>
}
