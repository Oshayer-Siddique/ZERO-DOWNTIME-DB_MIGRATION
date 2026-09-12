import { useState, type FormEvent } from 'react'
import { ArrowUpRight, Braces, Check, LockKeyhole, Plus, Users, LoaderCircle, CircleAlert } from 'lucide-react'
import type { LegacyUser, ModernUser, Version } from './api'

interface Props {
  version: Version
  available: boolean
  retired?: boolean
  users: LegacyUser[] | ModernUser[] | null
  error: string | null
  disabled: boolean
  pending: boolean
  onCreate: (version: Version, body: LegacyUser | ModernUser) => Promise<boolean>
}

export default function UserPanel({ version, available, retired, users, error, disabled, pending, onCreate }: Props) {
  const modern = version === 'v2'
  const [name, setName] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [inputError, setInputError] = useState<string | null>(null)
  const locked = disabled || !available
  const label = modern ? 'Modern API' : 'Legacy API'
  const state = retired ? 'Retired' : available ? 'Available' : 'Not ready'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (locked) return
    if (!(modern ? firstName : name).trim()) {
      setInputError(modern ? 'Enter a first name.' : 'Enter a full name.')
      return
    }
    setInputError(null)
    const body = modern ? { first_name: firstName.trim(), last_name: lastName.trim() } : { name: name.trim() }
    if (await onCreate(version, body)) {
      setName(''); setFirstName(''); setLastName('')
    }
  }

  return (
    <section className={`panel user-panel ${modern ? 'modern' : 'legacy'}`} aria-labelledby={`${version}-heading`}>
      <div className="user-panel-heading">
        <div className="panel-identity">
          <span className="api-icon"><Braces size={21} /></span>
          <div><h3 id={`${version}-heading`}>{label} <span className="version-tag">{version}</span></h3><p>{modern ? 'The new name structure' : 'The original name structure'}</p></div>
        </div>
        <span className={`badge ${available ? 'active' : 'muted'}`}><span className="status-dot" />{state}</span>
      </div>
      <div className="endpoint"><span>GET / POST</span><code>/{version}/users</code><ArrowUpRight size={14} /></div>
      <form onSubmit={(event) => void submit(event)} aria-label={`Create ${label.toLowerCase()} user`}>
        <fieldset disabled={locked}>
          <legend className="sr-only">Create a user through {label}</legend>
          <div className={modern ? 'name-fields' : 'single-field'}>
            {modern ? <>
              <label htmlFor="first-name">First name<input id="first-name" value={firstName} onChange={(event) => { setFirstName(event.target.value); setInputError(null) }} placeholder="e.g. Ada" required autoComplete="off" /></label>
              <label htmlFor="last-name">Last name <span className="optional">optional</span><input id="last-name" value={lastName} onChange={(event) => setLastName(event.target.value)} placeholder="e.g. Lovelace" autoComplete="off" /></label>
            </> : <label htmlFor="full-name">Full name<input id="full-name" value={name} onChange={(event) => { setName(event.target.value); setInputError(null) }} placeholder="e.g. John Smith" required autoComplete="off" /></label>}
          </div>
          <button className="button create-button" type="submit">{pending ? <LoaderCircle size={16} className="spin" /> : <Plus size={16} />}{pending ? 'Creating user…' : 'Create user'}</button>
        </fieldset>
        {inputError && <p className="field-error" role="alert">{inputError}</p>}
      </form>
      <div className="users-heading"><span><Users size={14} /> Users <span className="count">{users?.length ?? '—'}</span></span><span className="table-label">{available ? 'Live database' : retired ? 'Legacy access disabled' : 'Awaiting migration'}</span></div>
      {error ? <div className="empty-state error-empty" role="alert"><CircleAlert size={22} /><strong>Could not load users</strong><p>{error}</p></div>
        : !available ? <div className="empty-state"><span className="empty-icon">{retired ? <Check size={22} /> : <LockKeyhole size={20} />}</span><strong>{retired ? 'Legacy API retired' : modern ? 'Ready after synchronization' : 'Your legacy schema starts here'}</strong><p>{retired ? 'Your users are available through the modern API.' : modern ? 'Apply the first three steps to read and write the new fields.' : 'Initialize the database above to create your first user.'}</p></div>
          : users === null ? <div className="empty-state"><LoaderCircle className="spin" size={22} /><p>Loading users…</p></div>
            : users.length === 0 ? <div className="empty-state"><span className="empty-icon"><Users size={21} /></span><strong>No users yet</strong><p>Create a user above to start exploring this API.</p></div>
              : <div className="table-scroll"><table aria-label={`${label} users`}><thead><tr><th scope="col">Row</th>{modern ? <><th scope="col">first_name</th><th scope="col">last_name</th></> : <th scope="col">full_name</th>}</tr></thead><tbody>{users.map((user, index) => <tr key={index}><td className="row-number">{String(index + 1).padStart(2, '0')}</td>{'name' in user ? <td>{user.name}</td> : <><td>{user.first_name}</td><td>{user.last_name || <span className="empty-value">empty</span>}</td></>}</tr>)}</tbody></table></div>}
      <div className="panel-footnote"><span className={`tiny-line ${modern ? 'green' : 'amber'}`} />{modern ? 'Writes first_name + last_name' : 'Writes full_name'}<code>{version}</code></div>
    </section>
  )
}
