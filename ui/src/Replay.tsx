import { useAppApi, useTheme } from '@kirocrew/app-sdk'
import { Btn, Card, CardTitle, Input, StatCard } from '@kirocrew/app-sdk/ui'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { credits } from './format'
import type { Replay, ReplayStep } from './types'

// Three series in a fixed order. Each pair of colours was checked for
// colour-blind separation on a light and a dark surface.
const SERIES = [
  { key: 'session_only', name: 'Session only', light: '#2a78d6', dark: '#3987e5' },
  { key: 'with_subagents', name: 'With its subagents', light: '#eb6834', dark: '#d95926' },
  { key: 'capped', name: 'With Breaker', light: '#1baf7a', dark: '#199e70' },
] as const

type SeriesKey = (typeof SERIES)[number]['key']

const W = 760
const H = 320
const M = { left: 58, right: 168, top: 14, bottom: 34 }

function niceTop(value: number): number {
  const step = 10 ** Math.floor(Math.log10(Math.max(value, 1)))
  return Math.ceil(value / (step / 2)) * (step / 2)
}

export function ReplayView() {
  const api = useAppApi()
  const [limit, setLimit] = useState('5000')
  const [replay, setReplay] = useState<Replay | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(
    async (value: string) => {
      setBusy(true)
      setError('')
      try {
        setReplay(await api.get<Replay>(`/api/apps/breaker/replay?limit=${encodeURIComponent(value)}`))
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(false)
      }
    },
    [api],
  )

  useEffect(() => {
    void load('5000')
  }, [load])

  const summary = replay?.summary
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Card>
        <CardTitle>A reported overspend, replayed</CardTitle>
        <p style={{ fontSize: 13, color: 'var(--muted)', margin: '6px 0 12px', maxWidth: 760, lineHeight: 1.5 }}>
          A goal loop that carried a 5,000-credit budget in its own notes spent about 31,000 credits, about 85% of
          it in subagents (
          <a href={replay?.source.url ?? 'https://github.com/kirodotdev/KiroCrew/issues/6338'} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
            KiroCrew#6338
          </a>
          ). This runs those totals through the same ledger and cap Breaker uses live. The totals are the
          report's. The split into cycles is made up, so there is something to step through.
        </p>
        <form
          onSubmit={event => {
            event.preventDefault()
            void load(limit)
          }}
          style={{ display: 'flex', gap: 8, alignItems: 'center', maxWidth: 360 }}
        >
          <label htmlFor="replay-limit" style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
            Credit limit
          </label>
          <Input id="replay-limit" type="number" min={0} step="any" value={limit} onChange={event => setLimit(event.target.value)} />
          <Btn type="submit" busy={busy}>
            Replay
          </Btn>
        </form>
        {error && <p style={{ color: 'var(--danger)', fontSize: 13, marginTop: 8 }}>{error}</p>}
      </Card>

      {replay && summary && (
        <>
          <div style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))' }}>
            <StatCard
              label="Counting the session only"
              value={summary.session_only_tripped ? 'Trips' : `${credits(summary.session_only_total)}: never trips`}
              title="What a cap sees when nothing ties a subagent to the session that started it"
            />
            <StatCard label="Counting its subagents, no cap" value={credits(summary.uncapped_total)} />
            <StatCard
              label="With Breaker"
              value={summary.tripped ? `${credits(summary.drained_total)}` : 'Limit not reached'}
              accent
              title="Where spend stopped once the running work had drained"
            />
            <StatCard label="Not spent" value={credits(summary.saved)} />
          </div>
          <Card>
            <CardTitle>Credits spent, cycle by cycle</CardTitle>
            <p style={{ fontSize: 13, color: 'var(--muted)', margin: '6px 0 4px', lineHeight: 1.5 }}>
              {summary.tripped
                ? `The cap trips in cycle ${summary.tripped_cycle} at ${credits(summary.tripped_total ?? 0)}. No new cycle starts, the subagents already running finish, and spend settles at ${credits(summary.drained_total)}, ${credits(summary.overshoot)} past the limit.`
                : 'The limit is above everything this run spent, so the cap never trips.'}
              {!summary.session_only_tripped &&
                ` Counting the session alone, the same limit is never reached: its own turns add up to ${credits(summary.session_only_total)}.`}
            </p>
            <Chart replay={replay} />
          </Card>
        </>
      )}
    </div>
  )
}

function Chart({ replay }: { replay: Replay }) {
  const theme = useTheme()
  const dark = theme?.mode === 'dark'
  const [hover, setHover] = useState<number | null>(null)
  const steps = replay.steps
  const last = steps.length - 1
  const top = useMemo(() => niceTop(Math.max(replay.limit, ...steps.map(s => s.with_subagents))), [replay.limit, steps])
  const x = (index: number) => M.left + (index / Math.max(last, 1)) * (W - M.left - M.right)
  const y = (value: number) => H - M.bottom - (value / top) * (H - M.top - M.bottom)
  const colour = (index: number) => (dark ? SERIES[index].dark : SERIES[index].light)
  const path = (key: SeriesKey) => steps.map((s, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(s[key]).toFixed(1)}`).join('')
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(f => f * top)
  const tripIndex = steps.findIndex(s => s.signals.includes('tripped'))

  // End labels sit to the right of each line, pushed apart so they never overlap.
  const ends = SERIES.map((series, index) => ({ index, name: series.name, value: steps[last][series.key], at: y(steps[last][series.key]) }))
    .sort((a, b) => a.at - b.at)
  for (let i = 1; i < ends.length; i += 1) ends[i].at = Math.max(ends[i].at, ends[i - 1].at + 30)
  const overflow = ends[ends.length - 1].at - (H - M.bottom)
  if (overflow > 0) ends.forEach(end => (end.at -= overflow))

  const shown: ReplayStep | null = hover === null ? null : steps[hover]
  const cycleTicks = [1, 10, 20, 30, 40, 50, 60].filter(c => c <= replay.cycles)
  const firstOfCycle = (cycle: number) => steps.findIndex(s => s.cycle === cycle)

  return (
    <div>
      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', fontSize: 12, margin: '8px 0 2px' }} aria-label="Legend">
        {SERIES.map((series, index) => (
          <span key={series.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 14, height: 3, borderRadius: 2, background: colour(index) }} />
            {series.name}
          </span>
        ))}
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--muted)' }}>
          <span style={{ width: 14, borderTop: '2px dashed currentColor' }} />
          Limit
        </span>
      </div>
      <div style={{ position: 'relative', maxWidth: W }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          role="img"
          aria-label={`Line chart of credits spent over ${replay.cycles} cycles, counted three ways`}
          onMouseLeave={() => setHover(null)}
          onMouseMove={event => {
            const box = event.currentTarget.getBoundingClientRect()
            const px = ((event.clientX - box.left) / box.width) * W
            const index = Math.round(((px - M.left) / (W - M.left - M.right)) * last)
            setHover(index >= 0 && index <= last ? index : null)
          }}
        >
          {ticks.map(tick => (
            <g key={tick}>
              <line x1={M.left} x2={W - M.right} y1={y(tick)} y2={y(tick)} stroke="var(--border)" strokeWidth={1} />
              <text x={M.left - 8} y={y(tick) + 4} textAnchor="end" fontSize={11} fill="var(--muted)">
                {credits(tick)}
              </text>
            </g>
          ))}
          {cycleTicks.map(cycle => (
            <text key={cycle} x={x(Math.max(firstOfCycle(cycle), 0))} y={H - M.bottom + 16} textAnchor="middle" fontSize={11} fill="var(--muted)">
              {cycle}
            </text>
          ))}
          <text x={(M.left + W - M.right) / 2} y={H - 2} textAnchor="middle" fontSize={11} fill="var(--muted)">
            Cycle
          </text>
          <line x1={M.left} x2={W - M.right} y1={y(replay.limit)} y2={y(replay.limit)} stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="5 4" />
          <text x={M.left + 6} y={y(replay.limit) - 6} fontSize={11} fill="var(--muted)">
            Limit {credits(replay.limit)}
          </text>
          {SERIES.map((series, index) => (
            <path key={series.key} d={path(series.key)} fill="none" stroke={colour(index)} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {tripIndex >= 0 && (
            <g>
              <circle cx={x(tripIndex)} cy={y(steps[tripIndex].capped)} r={5} fill={colour(2)} stroke="var(--card, var(--bg))" strokeWidth={2} />
              <text x={x(tripIndex) + 9} y={y(steps[tripIndex].capped) - 9} fontSize={11} fill="var(--text)">
                Trips, cycle {steps[tripIndex].cycle}
              </text>
            </g>
          )}
          {ends.map(end => (
            <g key={end.index}>
              <line x1={W - M.right + 4} x2={W - M.right + 14} y1={end.at} y2={end.at} stroke={colour(end.index)} strokeWidth={3} strokeLinecap="round" />
              <text x={W - M.right + 20} y={end.at - 1} fontSize={11} fill="var(--muted)">
                {end.name}
              </text>
              <text x={W - M.right + 20} y={end.at + 12} fontSize={12} fontWeight={600} fill="var(--text)">
                {credits(end.value)}
              </text>
            </g>
          ))}
          {hover !== null && shown && (
            <g pointerEvents="none">
              <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={H - M.bottom} stroke="var(--muted)" strokeWidth={1} />
              {SERIES.map((series, index) => (
                <circle key={series.key} cx={x(hover)} cy={y(shown[series.key])} r={4} fill={colour(index)} stroke="var(--card, var(--bg))" strokeWidth={2} />
              ))}
            </g>
          )}
        </svg>
        {hover !== null && shown && (
          <div
            style={{
              position: 'absolute',
              top: 8,
              left: `${Math.min((x(hover) / W) * 100 + 2, 62)}%`,
              background: 'var(--bg-elevated, var(--bg))',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '8px 10px',
              fontSize: 12,
              pointerEvents: 'none',
              minWidth: 190,
              boxShadow: 'var(--shadow-md, none)',
            }}
          >
            <div style={{ fontWeight: 600, marginBottom: 4 }}>
              Cycle {shown.cycle}: {shown.what}
            </div>
            {SERIES.map((series, index) => (
              <div key={series.key} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--muted)' }}>
                  <span style={{ width: 10, height: 3, borderRadius: 2, background: colour(index) }} />
                  {series.name}
                </span>
                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{credits(shown[series.key])}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <details style={{ marginTop: 6, fontSize: 12 }}>
        <summary style={{ cursor: 'pointer', color: 'var(--muted)' }}>Show as a table</summary>
        <div style={{ maxHeight: 260, overflow: 'auto', marginTop: 6 }}>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontVariantNumeric: 'tabular-nums' }}>
            <thead>
              <tr style={{ textAlign: 'right', color: 'var(--muted)' }}>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>End of cycle</th>
                {SERIES.map(series => (
                  <th key={series.key} style={{ padding: '4px 8px', fontWeight: 500 }}>
                    {series.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: replay.cycles }, (_, i) => i + 1).map(cycle => {
                const row = [...steps].reverse().find(s => s.cycle === cycle)
                return row ? (
                  <tr key={cycle} style={{ textAlign: 'right', borderTop: '1px solid var(--border)' }}>
                    <td style={{ textAlign: 'left', padding: '4px 8px' }}>{cycle}</td>
                    {SERIES.map(series => (
                      <td key={series.key} style={{ padding: '4px 8px' }}>
                        {credits(row[series.key])}
                      </td>
                    ))}
                  </tr>
                ) : null
              })}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}
