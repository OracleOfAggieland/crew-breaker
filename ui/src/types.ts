export interface Trip {
  seq: number
  total: number
  limit: number
  running: string[]
  peak: number
  drained_seq: number | null
  overshoot: number
}

export interface Cap {
  session: string
  limit: number
  mode: 'shadow' | 'enforce'
  warn_pct: number
  state: 'armed' | 'warned' | 'tripped'
  trip: Trip | null
  past_trips: Trip[]
}

export interface Loop {
  id: string
  active: boolean
  cycle_count: number
  max_cycles: number
}

export interface Run {
  title: string
  max_cycles: number
  idle_secs: number
  loop_id: string
  loop_note: string
  cycles_done: number
  stopped: string
  stop_note?: string
  started_at?: string
}

export type Label = 'unattended' | 'while_open' | 'watch'

export interface Session {
  session: string
  title: string
  own: number
  children: number
  total: number
  dollars: number
  runs: number
  running: string[]
  surface: string
  app: string
  orphan_run: boolean
  bills_in_dollars: boolean
  last_spend: string
  owned: boolean
  run: Run | null
  label: Label
  loop: Loop | null
  cap: Cap | null
}

export interface PageAction {
  id: string
  kind: string
  session: string
  loop_id: string
  reason: string
}

export interface State {
  version: string
  now: string
  usage_log: string
  meter: { ok: boolean; note: string; last_read: string; live_ok: boolean; live_note: string }
  capabilities: { chat_slots: boolean; live_runs: boolean; loops: boolean }
  sessions: Session[]
  coverage: {
    linked_runs: number
    linked_credits: number
    orphan_runs: number
    orphan_credits: number
    rows_folded: number
    rows_refused: number
  }
  grand_total: number
  page_actions: PageAction[]
}

export interface HistoryEvent {
  at: string
  kind: string
  session: string
  total?: number
  limit?: number
  overshoot?: number
  mode?: string
  detail?: string
}

export interface ReplayStep {
  cycle: number
  what: string
  session_only: number
  with_subagents: number
  capped: number
  signals: string[]
}

export interface Replay {
  source: { url: string; reported_total: number; reported_budget: number; reported_subagent_share: number; note: string }
  limit: number
  cycles: number
  steps: ReplayStep[]
  summary: {
    uncapped_total: number
    session_only_total: number
    session_only_state: string
    session_only_tripped: boolean
    tripped: boolean
    tripped_cycle: number | null
    tripped_total: number | null
    drained_total: number
    overshoot: number
    saved: number
  }
}
