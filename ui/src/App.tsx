import { useAppApi, useNavBadge, useNotify } from '@kirocrew/app-sdk'
import { Badge, Btn, Card, CardTitle, Input, PageHeader, SegmentedControl, StatCard } from '@kirocrew/app-sdk/ui'
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { credits, plural, when } from './format'
import { ReplayView } from './Replay'
import type { Cap, HistoryEvent, Label, PageAction, Session, State } from './types'

const BASE = '/api/apps/breaker'
const POLL_MS = 5000

const HOLDS: Record<Label, { text: string; variant: 'ok' | 'warn' | 'muted'; help: string }> = {
  unattended: {
    text: 'Holds with no page open',
    variant: 'ok',
    help: 'Breaker started this work and owns its session, so it removes the loop itself.',
  },
  while_open: {
    text: 'Holds while this page is open',
    variant: 'warn',
    help: 'You started this loop, so only you may pause it. An open Breaker page does it for you.',
  },
  watch: {
    text: 'Watch only',
    variant: 'muted',
    help: 'Nothing here can be stopped without refusing a message you typed. Breaker records the trip.',
  },
}

const cell: CSSProperties = { padding: '10px 10px', verticalAlign: 'top', fontSize: 13 }
const num: CSSProperties = { ...cell, textAlign: 'right', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
const head: CSSProperties = { padding: '6px 10px', fontSize: 11, fontWeight: 500, color: 'var(--muted)', textAlign: 'left', whiteSpace: 'nowrap' }
const muted: CSSProperties = { color: 'var(--muted)', fontSize: 12 }
const mono: CSSProperties = { fontFamily: 'var(--mono, monospace)', fontSize: 11, color: 'var(--muted)' }

function message(err: unknown): string {
  const text = err instanceof Error ? err.message : String(err)
  const body = (err as { body?: string } | null)?.body
  if (body) {
    try {
      const parsed = JSON.parse(body) as { error?: string }
      if (parsed.error) return parsed.error
    } catch {
      /* not JSON: fall through to the message */
    }
  }
  return text
}

export default function Breaker() {
  const api = useAppApi()
  const notify = useNotify()
  const setBadge = useNavBadge()
  const [state, setState] = useState<State | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('sessions')
  const attempted = useRef(new Set<string>())

  const refresh = useCallback(async () => {
    try {
      setState(await api.get<State>(`${BASE}/state`))
      setError('')
    } catch (err) {
      setError(message(err))
    }
  }, [api])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), POLL_MS)
    return () => window.clearInterval(timer)
  }, [refresh])

  // A stop that needs the owner's authority: this page holds it, the backend does not.
  const carryOut = useCallback(
    async (action: PageAction) => {
      let ok = true
      let detail = 'loop paused from the Breaker page; a turn already running is left to finish'
      try {
        if (action.kind !== 'pause_loop') throw new Error(`unknown action ${action.kind}`)
        await api.patch(`/api/autonudge/${encodeURIComponent(action.loop_id)}`, { active: false })
      } catch (err) {
        ok = false
        detail = `the page could not pause the loop: ${message(err)}`
      }
      try {
        await api.post(`${BASE}/page-actions/${encodeURIComponent(action.id)}/done`, { ok, detail })
      } catch {
        /* the backend keeps the action and this page tries again after a reload */
      }
      notify(ok ? 'Breaker paused a loop that reached its credit limit.' : detail, { type: ok ? 'success' : 'error' })
      void refresh()
    },
    [api, notify, refresh],
  )

  useEffect(() => {
    for (const action of state?.page_actions ?? []) {
      if (attempted.current.has(action.id)) continue
      attempted.current.add(action.id)
      void carryOut(action)
    }
  }, [state, carryOut])

  const sessions = state?.sessions ?? []
  const capped = sessions.filter(s => s.cap && s.cap.limit > 0)
  const tripped = capped.filter(s => s.cap?.state === 'tripped')
  const enforcedTrips = tripped.filter(s => s.cap?.mode === 'enforce').length

  useEffect(() => {
    setBadge(enforcedTrips)
  }, [enforcedTrips, setBadge])

  return (
    <>
      <PageHeader title="Breaker" subtitle="A circuit breaker for credits: a session is counted with the subagents it started" />
      <div style={{ padding: '0 24px 32px', overflowY: 'auto', flex: 1, minHeight: 0 }}>
        {error && <Notice tone="danger">Breaker's backend did not answer: {error}</Notice>}
        {state && !state.meter.ok && (
          <Notice tone="danger">
            The usage log can't be read ({state.meter.note}). Nothing trips while the meter is unreadable.
          </Notice>
        )}
        {state && state.meter.ok && !state.meter.live_ok && (
          <Notice tone="warn">
            Breaker can't see the subagents running right now ({state.meter.live_note}). Totals count finished turns
            only, and a subagent that finishes may not be tied to its session.
          </Notice>
        )}
        <div style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', margin: '4px 0 18px' }}>
          <StatCard label="Credits counted" value={state ? credits(state.grand_total) : null} accent />
          <StatCard label="Sessions" value={state ? sessions.length : null} />
          <StatCard
            label="Subagent credits tied to a session"
            value={state ? credits(state.coverage.linked_credits) : null}
            title={state ? `${plural(state.coverage.linked_runs, 'subagent run')} tied to the session that started it` : undefined}
          />
          <StatCard label="Caps set" value={state ? capped.length : null} />
          <StatCard label="Tripped" value={state ? tripped.length : null} />
        </div>
        <div style={{ marginBottom: 14 }}>
          <SegmentedControl
            ariaLabel="Breaker views"
            layoutId="breaker-tabs"
            value={tab}
            onChange={setTab}
            segments={[
              { key: 'sessions', label: 'Sessions' },
              { key: 'start', label: 'Start under a breaker' },
              { key: 'replay', label: 'Replay' },
              { key: 'history', label: 'History' },
              { key: 'limits', label: "What it can't do" },
            ]}
          />
        </div>
        {tab === 'sessions' && <Sessions state={state} onChanged={refresh} />}
        {tab === 'start' && <StartRun state={state} onStarted={() => { setTab('sessions'); void refresh() }} />}
        {tab === 'replay' && <ReplayView />}
        {tab === 'history' && <History state={state} />}
        {tab === 'limits' && <Limits />}
      </div>
    </>
  )
}

function Notice({ tone, children }: { tone: 'danger' | 'warn'; children: ReactNode }) {
  const colour = tone === 'danger' ? 'var(--danger, #b91c1c)' : 'var(--warn, #b45309)'
  return (
    <div role="status" style={{ border: `1px solid ${colour}`, borderLeftWidth: 4, borderRadius: 6, padding: '10px 12px', fontSize: 13, margin: '0 0 12px', lineHeight: 1.5 }}>
      {children}
    </div>
  )
}

function nameOf(session: Session): string {
  return session.title || session.session
}

// ---- sessions --------------------------------------------------------------

function Sessions({ state, onChanged }: { state: State | null; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState<string | null>(null)
  if (!state) return <Card><p style={muted}>Reading the meter…</p></Card>
  if (state.sessions.length === 0) {
    return (
      <Card>
        <CardTitle>No spend yet</CardTitle>
        <p style={{ ...muted, fontSize: 13, lineHeight: 1.5, marginTop: 6 }}>
          Breaker reads Kiro Crew's usage log at <span style={mono}>{state.usage_log}</span>. A session shows up
          here once one of its turns has finished. Sessions on a harness that bills in dollars are listed and not capped.
        </p>
      </Card>
    )
  }
  return (
    <Card>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th style={head}>Session</th>
              <th style={{ ...head, textAlign: 'right' }}>Its own turns</th>
              <th style={{ ...head, textAlign: 'right' }}>Its subagents</th>
              <th style={{ ...head, textAlign: 'right' }}>Total</th>
              <th style={head}>Cap</th>
              <th style={head}>How it holds</th>
              <th style={head} />
            </tr>
          </thead>
          <tbody>
            {state.sessions.map(session => (
              <Fragment key={session.session}>
                <tr style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ ...cell, maxWidth: 320 }}>
                    <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis' }}>{nameOf(session)}</div>
                    {session.title && <div style={mono}>{session.session}</div>}
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                      {session.owned && <Badge variant="aim" title="Started from Breaker; it owns this session">Started from Breaker</Badge>}
                      {session.orphan_run && <Badge variant="muted" title="A subagent whose session Breaker never saw: it started and ended between two looks">Subagent, session unknown</Badge>}
                      {session.bills_in_dollars && <Badge variant="muted" title="This harness bills in dollars. Breaker caps credits only.">Bills in dollars: not capped</Badge>}
                      {session.loop && <Badge variant="muted" title="A goal loop is armed on this session">{session.loop.active ? 'Loop running' : 'Loop paused'}, cycle {session.loop.cycle_count}{session.loop.max_cycles ? ` of ${session.loop.max_cycles}` : ''}</Badge>}
                    </div>
                  </td>
                  <td style={num}>{credits(session.own)}</td>
                  <td style={num}>
                    {credits(session.children)}
                    <div style={muted}>
                      {plural(session.runs, 'run')}
                      {session.running.length > 0 && `, ${session.running.length} running`}
                    </div>
                  </td>
                  <td style={{ ...num, fontWeight: 600 }}>
                    {credits(session.total)}
                    {session.dollars > 0 && <div style={muted}>+ ${session.dollars.toFixed(2)}</div>}
                    <div style={muted}>{when(session.last_spend)}</div>
                  </td>
                  <td style={{ ...cell, minWidth: 190 }}><CapCell session={session} /></td>
                  <td style={cell}>
                    {session.cap && session.cap.limit > 0 ? (
                      session.cap.mode === 'enforce' ? (
                        <Badge variant={HOLDS[session.label].variant} title={HOLDS[session.label].help}>{HOLDS[session.label].text}</Badge>
                      ) : (
                        <Badge variant="muted" title="A shadow cap is measured the same way and stops nothing">Shadow: stops nothing</Badge>
                      )
                    ) : (
                      <span style={muted}>{HOLDS[session.label].text.replace('Holds', 'Would hold')}</span>
                    )}
                  </td>
                  <td style={{ ...cell, whiteSpace: 'nowrap', textAlign: 'right' }}>
                    <RowActions session={session} editing={editing === session.session} onEdit={() => setEditing(editing === session.session ? null : session.session)} onChanged={onChanged} />
                  </td>
                </tr>
                {editing === session.session && (
                  <tr>
                    <td colSpan={7} style={{ padding: '0 10px 14px' }}>
                      <CapEditor session={session} onDone={async () => { setEditing(null); await onChanged() }} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ ...muted, marginTop: 12, lineHeight: 1.5 }}>
        A cap counts a session's own turns plus every subagent it started. When it trips, no new cycle starts and a
        turn or subagent already running finishes. It stays tripped until you restart it; raising the limit restarts
        nothing. A message you type is never refused.
      </p>
    </Card>
  )
}

function CapCell({ session }: { session: Session }) {
  const cap = session.cap
  if (!cap || cap.limit <= 0) return <span style={muted}>No cap</span>
  const share = Math.min(session.total / cap.limit, 1)
  const tripped = cap.state === 'tripped'
  const bar = tripped ? 'var(--danger, #b91c1c)' : cap.state === 'warned' ? 'var(--warn, #b45309)' : 'var(--accent)'
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{credits(cap.limit)}</span>
        {tripped ? <Badge variant="err">Tripped</Badge> : cap.state === 'warned' ? <Badge variant="warn">Past {cap.warn_pct}%</Badge> : <Badge variant="muted">Armed</Badge>}
      </div>
      <div style={{ height: 4, borderRadius: 2, background: 'var(--border)', margin: '6px 0 4px', overflow: 'hidden' }} aria-hidden>
        <div style={{ width: `${share * 100}%`, height: '100%', background: bar }} />
      </div>
      {cap.trip && <TripLine cap={cap} />}
    </div>
  )
}

function TripLine({ cap }: { cap: Cap }) {
  const trip = cap.trip
  if (!trip) return null
  const would = cap.mode === 'shadow' ? 'Would have tripped' : 'Tripped'
  const draining = trip.drained_seq === null
  return (
    <div style={{ ...muted, lineHeight: 1.45 }}>
      {would} at {credits(trip.total)}.{' '}
      {draining
        ? `${plural(trip.running.length, 'subagent')} still running; spend so far ${credits(trip.peak)}.`
        : trip.overshoot > 0
          ? `Spend ran ${credits(trip.overshoot)} past the limit while running work finished.`
          : 'Nothing was running, so nothing more was spent.'}
    </div>
  )
}

function RowActions({ session, editing, onEdit, onChanged }: { session: Session; editing: boolean; onEdit: () => void; onChanged: () => Promise<void> }) {
  const api = useAppApi()
  const notify = useNotify()
  const [busy, setBusy] = useState('')
  const act = async (name: string, path: string, done: (answer: { note?: string }) => string) => {
    setBusy(name)
    try {
      const answer = await api.post<{ note?: string }>(`${BASE}${path}`, { session: session.session })
      notify(done(answer), { type: 'success' })
    } catch (err) {
      notify(message(err), { type: 'error' })
    } finally {
      setBusy('')
      await onChanged()
    }
  }
  const tripped = session.cap?.state === 'tripped'
  const ownLoop = session.owned && session.run && session.run.loop_id
  return (
    <span style={{ display: 'inline-flex', gap: 6 }}>
      {tripped && (
        <Btn busy={busy === 'restart'} onClick={() => void act('restart', '/restart', a => a.note ? `Restarted: ${a.note}.` : 'Restarted. If spend is still over the limit, it trips again at once.')} title="Arm the cap again. Over the limit, it trips again at once.">
          Restart
        </Btn>
      )}
      {ownLoop && !tripped && (
        <Btn busy={busy === 'stop'} onClick={() => void act('stop', '/runs/stop', () => 'Loop removed. A turn already running is left to finish.')}>
          Stop loop
        </Btn>
      )}
      <Btn onClick={onEdit}>{editing ? 'Close' : session.cap && session.cap.limit > 0 ? 'Change cap' : 'Set cap'}</Btn>
    </span>
  )
}

function CapEditor({ session, onDone }: { session: Session; onDone: () => Promise<void> }) {
  const api = useAppApi()
  const notify = useNotify()
  const [limit, setLimit] = useState(session.cap && session.cap.limit > 0 ? String(session.cap.limit) : '')
  const [mode, setMode] = useState<string>(session.cap?.mode ?? 'shadow')
  const [busy, setBusy] = useState(false)
  const value = Number(limit)
  const valid = limit.trim() !== '' && Number.isFinite(value) && value > 0
  const save = async () => {
    setBusy(true)
    try {
      await api.put(`${BASE}/caps`, { session: session.session, limit: value, mode })
      notify(`Cap set at ${credits(value)} credits.`, { type: 'success' })
      await onDone()
    } catch (err) {
      notify(message(err), { type: 'error' })
    } finally {
      setBusy(false)
    }
  }
  const remove = async () => {
    setBusy(true)
    try {
      await api.post(`${BASE}/caps/remove`, { session: session.session })
      notify('Cap removed.', { type: 'success' })
      await onDone()
    } catch (err) {
      notify(message(err), { type: 'error' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 12, display: 'grid', gap: 10, maxWidth: 720 }}>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <label htmlFor={`limit-${session.session}`} style={{ fontSize: 13 }}>Credit limit for this session and its subagents</label>
        <div style={{ width: 140, display: 'flex' }}>
          <Input id={`limit-${session.session}`} type="number" min={1} value={limit} onChange={event => setLimit(event.target.value)} placeholder="e.g. 5000" />
        </div>
        <SegmentedControl
          ariaLabel="Cap mode"
          layoutId={`mode-${session.session}`}
          value={mode}
          onChange={setMode}
          segments={[
            { key: 'shadow', label: 'Shadow' },
            { key: 'enforce', label: 'Enforce' },
          ]}
        />
      </div>
      <p style={{ ...muted, lineHeight: 1.5, margin: 0 }}>
        {mode === 'shadow'
          ? 'Shadow measures the cap and stops nothing. It reports when the limit would have tripped and how far spend ran past it.'
          : `Enforce on this session: ${HOLDS[session.label].text.toLowerCase()}. ${HOLDS[session.label].help}`}
        {session.total > 0 && valid && value <= session.total && ' This session has already spent more than that, so the cap trips as soon as it is saved.'}
      </p>
      <div style={{ display: 'flex', gap: 8 }}>
        <Btn primary busy={busy} disabled={!valid} onClick={() => void save()}>Save cap</Btn>
        {session.cap && <Btn danger busy={busy} onClick={() => void remove()}>Remove cap</Btn>}
      </div>
    </div>
  )
}

// ---- start under a breaker -------------------------------------------------

function StartRun({ state, onStarted }: { state: State | null; onStarted: () => void }) {
  const api = useAppApi()
  const notify = useNotify()
  const [prompt, setPrompt] = useState('')
  const [title, setTitle] = useState('')
  const [limit, setLimit] = useState('500')
  const [cycles, setCycles] = useState('10')
  const [idle, setIdle] = useState('60')
  const [busy, setBusy] = useState(false)
  const available = state?.capabilities.chat_slots ?? true
  const valid = prompt.trim() !== '' && Number(limit) > 0
  const start = async () => {
    setBusy(true)
    try {
      const answer = await api.post<{ session: string; loop_note?: string }>(`${BASE}/runs`, {
        prompt,
        title,
        limit: Number(limit),
        max_cycles: Number(cycles),
        idle_secs: Number(idle),
      })
      notify(answer.loop_note ? `Started, but no loop was armed: ${answer.loop_note}` : 'Started under a breaker. The session is listed under Breaker in the sidebar.', { type: answer.loop_note ? 'error' : 'success' })
      setPrompt('')
      setTitle('')
      onStarted()
    } catch (err) {
      notify(message(err), { type: 'error' })
    } finally {
      setBusy(false)
    }
  }
  const field: CSSProperties = { display: 'grid', gap: 4, fontSize: 13 }
  return (
    <Card>
      <CardTitle>Start work under a breaker</CardTitle>
      <p style={{ ...muted, fontSize: 13, lineHeight: 1.5, margin: '6px 0 14px', maxWidth: 760 }}>
        Breaker opens a session of its own, sends your prompt, and keeps it going with a goal loop. Because Breaker
        owns the session, the cap holds with no page open: when the session and its subagents reach the limit, the
        loop is removed before its next cycle. The turn that is running finishes.
      </p>
      {!available && <Notice tone="warn">This Kiro Crew does not give apps chat sessions of their own, so Breaker can't own work here.</Notice>}
      <div style={{ display: 'grid', gap: 12, maxWidth: 760 }}>
        <label style={field}>
          Goal
          <textarea
            value={prompt}
            onChange={event => setPrompt(event.target.value)}
            rows={5}
            placeholder="What should the session work toward?"
            style={{ background: 'var(--bg-elevated, var(--bg))', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 6, padding: '8px 12px', fontSize: 13, fontFamily: 'inherit', resize: 'vertical' }}
          />
        </label>
        <label style={field}>
          Name (optional)
          <div style={{ display: 'flex' }}><Input value={title} onChange={event => setTitle(event.target.value)} maxLength={80} placeholder="Shown in the sidebar" /></div>
        </label>
        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
          <label style={field}>
            Credit limit
            <div style={{ display: 'flex' }}><Input type="number" min={1} value={limit} onChange={event => setLimit(event.target.value)} /></div>
          </label>
          <label style={field}>
            Most cycles
            <div style={{ display: 'flex' }}><Input type="number" min={0} max={500} value={cycles} onChange={event => setCycles(event.target.value)} /></div>
            <span style={muted}>A second stop, kept by Kiro Crew itself. 0 sends the goal once.</span>
          </label>
          <label style={field}>
            Seconds idle before the next cycle
            <div style={{ display: 'flex' }}><Input type="number" min={30} max={3600} value={idle} onChange={event => setIdle(event.target.value)} /></div>
          </label>
        </div>
        <div><Btn primary busy={busy} disabled={!valid || !available} onClick={() => void start()}>Start under a breaker</Btn></div>
      </div>
    </Card>
  )
}

// ---- history ---------------------------------------------------------------

const KINDS: Record<string, string> = {
  cap_set: 'Cap set',
  cap_removed: 'Cap removed',
  warned: 'Warned',
  tripped: 'Tripped',
  drained: 'Running work finished',
  restarted: 'Restarted',
  stopped: 'Stopped',
  stop_failed: 'Could not stop',
  page_action_queued: 'Waiting for a page',
  run_started: 'Started under a breaker',
}

function History({ state }: { state: State | null }) {
  const api = useAppApi()
  const [events, setEvents] = useState<HistoryEvent[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api
      .get<{ events: HistoryEvent[] }>(`${BASE}/history?limit=200`)
      .then(answer => setEvents(answer.events))
      .catch(err => setError(message(err)))
  }, [api, state?.now])
  const titles = new Map((state?.sessions ?? []).map(s => [s.session, s.title]))
  if (error) return <Notice tone="danger">{error}</Notice>
  if (!events) return <Card><p style={muted}>Loading…</p></Card>
  if (events.length === 0) return <Card><p style={{ ...muted, fontSize: 13 }}>Nothing has happened yet. Caps you set, trips and stops are listed here.</p></Card>
  return (
    <Card>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={head}>When</th>
            <th style={head}>What</th>
            <th style={head}>Session</th>
            <th style={head}>Detail</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event, index) => (
            <tr key={`${event.at}-${index}`} style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ ...cell, whiteSpace: 'nowrap', color: 'var(--muted)' }}>{when(event.at)}</td>
              <td style={{ ...cell, whiteSpace: 'nowrap' }}>{KINDS[event.kind] ?? event.kind}{event.mode === 'shadow' && (event.kind === 'tripped' || event.kind === 'warned') ? ' (shadow)' : ''}</td>
              <td style={cell}>{titles.get(event.session) || <span style={mono}>{event.session}</span>}</td>
              <td style={{ ...cell, color: 'var(--muted)' }}>{describe(event)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function describe(event: HistoryEvent): string {
  const parts: string[] = []
  if (event.kind === 'cap_set' && event.limit !== undefined) parts.push(`${credits(event.limit)} credits, ${event.mode === 'enforce' ? 'enforced' : 'shadow'}`)
  if ((event.kind === 'tripped' || event.kind === 'warned') && event.total !== undefined && event.limit !== undefined) parts.push(`${credits(event.total)} of ${credits(event.limit)}`)
  if (event.kind === 'drained' && event.overshoot !== undefined) parts.push(`${credits(event.overshoot)} past the limit`)
  if (event.kind === 'run_started' && event.limit !== undefined) parts.push(`limit ${credits(event.limit)}`)
  if (event.detail) parts.push(event.detail)
  return parts.join('. ')
}

// ---- limits ----------------------------------------------------------------

function Limits() {
  const item: CSSProperties = { fontSize: 13, lineHeight: 1.55, margin: '0 0 8px' }
  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 820 }}>
      <Card>
        <CardTitle>What Breaker can't do</CardTitle>
        <ul style={{ paddingLeft: 18, margin: '8px 0 0' }}>
          <li style={item}><b>It can't refuse a turn before it starts</b>, except on work it owns. A Kiro Crew app has no hook in front of a turn. So a cap on your own loop is held by pausing the loop, and only while a Breaker page is open.</li>
          <li style={item}><b>It never cuts a running turn or subagent.</b> Spend can run past the limit while they finish. Breaker measures that and shows it.</li>
          <li style={item}><b>A subagent that finishes can still wake its session</b>, and that turn can start more subagents. Breaker stops the loop, not that wake.</li>
          <li style={item}><b>A subagent that starts and ends between two looks</b> (about 20 seconds apart) is counted, and not tied to its session. It is listed as "Subagent, session unknown".</li>
          <li style={item}><b>Credits only.</b> A harness that bills in dollars is listed and never capped.</li>
          <li style={item}><b>It stops nothing you type.</b> A message you send always runs.</li>
        </ul>
      </Card>
      <Card>
        <CardTitle>What an app would need from Kiro Crew to do this properly</CardTitle>
        <ul style={{ paddingLeft: 18, margin: '8px 0 0' }}>
          <li style={item}>The parent session written on each subagent's usage row, so the link doesn't have to be caught while the run is alive.</li>
          <li style={item}>A check an app can answer before a loop's next cycle, so a cap holds on any loop with no page open.</li>
          <li style={item}>A stop reason an app can set on a loop it paused, shown where the loop is shown.</li>
          <li style={item}>The same check before a subagent is spawned, to close the wake gap above.</li>
        </ul>
        <p style={{ ...muted, marginTop: 6, lineHeight: 1.5 }}>
          Breaker is a working prototype of the session cap proposed in KiroCrew#35488, built only from what Kiro Crew
          v0.13.1 gives a third-party app.
        </p>
      </Card>
    </div>
  )
}
