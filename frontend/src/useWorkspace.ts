import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, messageOf, type DemoStatus, type LegacyUser, type ModernUser, type Version } from './api'

export interface Activity {
  id: number
  time: Date
  title: string
  kind: 'success' | 'error'
  endpoint: string
  code: number | null
  detail: unknown
}

interface Snapshot {
  status: DemoStatus
  legacy: LegacyUser[] | null
  modern: ModernUser[] | null
  legacyError: string | null
  modernError: string | null
}

type Pending = Version | 'migration' | 'retirement' | null

export function useWorkspace() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [refreshing, setRefreshing] = useState(true)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [pending, setPending] = useState<Pending>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const refreshingRef = useRef(false)
  const pendingRef = useRef<Pending>(null)
  const mounted = useRef(true)
  const activityId = useRef(0)

  const refresh = useCallback(async () => {
    if (refreshingRef.current) return
    refreshingRef.current = true
    if (mounted.current) setRefreshing(true)
    try {
      const status = await api<DemoStatus>('/demo/status')
      const [legacy, modern] = await Promise.allSettled([
        status.v1_available ? api<LegacyUser[]>('/v1/users') : Promise.resolve(null),
        status.v2_available ? api<ModernUser[]>('/v2/users') : Promise.resolve(null),
      ])
      if (!mounted.current) return
      setSnapshot({
        status,
        legacy: legacy.status === 'fulfilled' ? legacy.value : null,
        modern: modern.status === 'fulfilled' ? modern.value : null,
        legacyError: legacy.status === 'rejected' ? messageOf(legacy.reason) : null,
        modernError: modern.status === 'rejected' ? messageOf(modern.reason) : null,
      })
      setConnectionError(null)
    } catch (error) {
      if (mounted.current) setConnectionError(messageOf(error))
    } finally {
      refreshingRef.current = false
      if (mounted.current) setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    void refresh()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible' && !pendingRef.current) void refresh()
    }, 5000)
    return () => { mounted.current = false; window.clearInterval(timer) }
  }, [refresh])

  const mutate = async (kind: Exclude<Pending, null>, path: string, body: unknown, title: string) => {
    if (pendingRef.current || refreshingRef.current) return false
    pendingRef.current = kind
    setPending(kind)
    setNotice(null)
    let succeeded = false
    try {
      const result = await api(path, body)
      succeeded = true
      if (mounted.current) {
        setNotice({ kind: 'success', text: title })
        setActivities((items) => [{ id: ++activityId.current, time: new Date(), title, kind: 'success', endpoint: `POST ${path}`, code: kind === 'v1' || kind === 'v2' ? 201 : 200, detail: result }, ...items].slice(0, 12) as Activity[])
      }
    } catch (error) {
      if (mounted.current) {
        const text = messageOf(error)
        setNotice({ kind: 'error', text })
        setActivities((items) => [{ id: ++activityId.current, time: new Date(), title: text, kind: 'error', endpoint: `POST ${path}`, code: error instanceof ApiError ? error.status : null, detail: error instanceof ApiError ? error.response ?? { detail: text } : { detail: text } }, ...items].slice(0, 12) as Activity[])
      }
    } finally {
      // Always reconcile with the database, including failed or timed-out writes.
      await refresh()
      pendingRef.current = null
      if (mounted.current) setPending(null)
    }
    return succeeded
  }

  const advance = () => {
    if (!snapshot?.status.can_migrate || connectionError) return Promise.resolve(false)
    const messages: Record<string, string> = {
      uninitialized: 'Database initialized. The legacy API is ready.',
      initial: 'Schema expanded. The legacy API is still available.',
      expanded: 'Names synchronized. Both API versions are ready.',
      synchronized: 'Migration complete. The modern API is ready.',
    }
    return mutate('migration', '/demo/migrations/next', { expected_stage: snapshot.status.stage }, messages[snapshot.status.stage])
  }

  const retire = () => {
    if (!snapshot?.status.can_retire_v1 || connectionError) return Promise.resolve(false)
    return mutate('retirement', '/demo/v1/retire', {}, 'Legacy API retired. You can now contract the schema.')
  }

  const create = (version: Version, body: LegacyUser | ModernUser) => {
    if (!snapshot?.status[version === 'v1' ? 'v1_available' : 'v2_available'] || connectionError) return Promise.resolve(false)
    return mutate(version, `/${version}/users`, body, `User created through API ${version}.`)
  }

  return { snapshot, refreshing, connectionError, pending, activities, notice, refresh, advance, retire, create, dismissNotice: () => setNotice(null) }
}
