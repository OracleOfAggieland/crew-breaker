import { jsxs as n, jsx as e, Fragment as J } from "react/jsx-runtime";
import { useAppApi as O, useTheme as Z, useNotify as P, useNavBadge as ee } from "@kirocrew/app-sdk";
import { Card as T, CardTitle as K, Input as F, Btn as H, StatCard as N, PageHeader as te, Badge as I, SegmentedControl as ie } from "@kirocrew/app-sdk/ui";
import { useState as b, useCallback as X, useEffect as j, useMemo as ne, useRef as re, Fragment as ae } from "react";
const oe = new Intl.NumberFormat(void 0, { maximumFractionDigits: 0 }), le = new Intl.NumberFormat(void 0, { maximumFractionDigits: 1 }), se = new Intl.NumberFormat(void 0, { maximumFractionDigits: 2 });
function p(t) {
  if (!Number.isFinite(t)) return "-";
  const a = Math.abs(t);
  return a >= 100 ? oe.format(t) : a >= 10 ? le.format(t) : se.format(t);
}
function Q(t) {
  if (!t) return "";
  const a = new Date(t);
  if (Number.isNaN(a.getTime())) return t;
  const c = a.toDateString() === (/* @__PURE__ */ new Date()).toDateString();
  return a.toLocaleString(void 0, c ? { hour: "2-digit", minute: "2-digit" } : { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function G(t, a, c = `${a}s`) {
  return `${t} ${t === 1 ? a : c}`;
}
const A = [
  { key: "session_only", name: "Session only", light: "#2a78d6", dark: "#3987e5" },
  { key: "with_subagents", name: "With its subagents", light: "#eb6834", dark: "#d95926" },
  { key: "capped", name: "With Breaker", light: "#1baf7a", dark: "#199e70" }
], _ = 760, R = 320, m = { left: 58, right: 168, top: 14, bottom: 34 };
function de(t) {
  const a = 10 ** Math.floor(Math.log10(Math.max(t, 1)));
  return Math.ceil(t / (a / 2)) * (a / 2);
}
function ce() {
  const t = O(), [a, c] = b("5000"), [r, o] = b(null), [u, f] = b(""), [d, g] = b(!1), y = X(
    async (v) => {
      g(!0), f("");
      try {
        o(await t.get(`/api/apps/breaker/replay?limit=${encodeURIComponent(v)}`));
      } catch (k) {
        f(k instanceof Error ? k.message : String(k));
      } finally {
        g(!1);
      }
    },
    [t]
  );
  j(() => {
    y("5000");
  }, [y]);
  const l = r == null ? void 0 : r.summary;
  return /* @__PURE__ */ n("div", { style: { display: "grid", gap: 16 }, children: [
    /* @__PURE__ */ n(T, { children: [
      /* @__PURE__ */ e(K, { children: "A reported overspend, replayed" }),
      /* @__PURE__ */ n("p", { style: { fontSize: 13, color: "var(--muted)", margin: "6px 0 12px", maxWidth: 760, lineHeight: 1.5 }, children: [
        "A goal loop that carried a 5,000-credit budget in its own notes spent about 31,000 credits, about 85% of it in subagents (",
        /* @__PURE__ */ e("a", { href: (r == null ? void 0 : r.source.url) ?? "https://github.com/kirodotdev/KiroCrew/issues/6338", target: "_blank", rel: "noreferrer", style: { color: "var(--accent)" }, children: "KiroCrew#6338" }),
        "). This runs those totals through the same ledger and cap Breaker uses live. The totals are the report's. The split into cycles is made up, so there is something to step through."
      ] }),
      /* @__PURE__ */ n(
        "form",
        {
          onSubmit: (v) => {
            v.preventDefault(), y(a);
          },
          style: { display: "flex", gap: 8, alignItems: "center", maxWidth: 360 },
          children: [
            /* @__PURE__ */ e("label", { htmlFor: "replay-limit", style: { fontSize: 13, whiteSpace: "nowrap" }, children: "Credit limit" }),
            /* @__PURE__ */ e(F, { id: "replay-limit", type: "number", min: 0, step: "any", value: a, onChange: (v) => c(v.target.value) }),
            /* @__PURE__ */ e(H, { type: "submit", busy: d, children: "Replay" })
          ]
        }
      ),
      u && /* @__PURE__ */ e("p", { style: { color: "var(--danger)", fontSize: 13, marginTop: 8 }, children: u })
    ] }),
    r && l && /* @__PURE__ */ n(J, { children: [
      /* @__PURE__ */ n("div", { style: { display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))" }, children: [
        /* @__PURE__ */ e(
          N,
          {
            label: "Counting the session only",
            value: l.session_only_tripped ? "Trips" : `${p(l.session_only_total)}: never trips`,
            title: "What a cap sees when nothing ties a subagent to the session that started it"
          }
        ),
        /* @__PURE__ */ e(N, { label: "Counting its subagents, no cap", value: p(l.uncapped_total) }),
        /* @__PURE__ */ e(
          N,
          {
            label: "With Breaker",
            value: l.tripped ? `${p(l.drained_total)}` : "Limit not reached",
            accent: !0,
            title: "Where spend stopped once the running work had drained"
          }
        ),
        /* @__PURE__ */ e(N, { label: "Not spent", value: p(l.saved) })
      ] }),
      /* @__PURE__ */ n(T, { children: [
        /* @__PURE__ */ e(K, { children: "Credits spent, cycle by cycle" }),
        /* @__PURE__ */ n("p", { style: { fontSize: 13, color: "var(--muted)", margin: "6px 0 4px", lineHeight: 1.5 }, children: [
          l.tripped ? `The cap trips in cycle ${l.tripped_cycle} at ${p(l.tripped_total ?? 0)}. No new cycle starts, the subagents already running finish, and spend settles at ${p(l.drained_total)}, ${p(l.overshoot)} past the limit.` : "The limit is above everything this run spent, so the cap never trips.",
          !l.session_only_tripped && ` Counting the session alone, the same limit is never reached: its own turns add up to ${p(l.session_only_total)}.`
        ] }),
        /* @__PURE__ */ e(he, { replay: r })
      ] })
    ] })
  ] });
}
function he({ replay: t }) {
  const a = Z(), c = (a == null ? void 0 : a.mode) === "dark", [r, o] = b(null), u = t.steps, f = u.length - 1, d = ne(() => de(Math.max(t.limit, ...u.map((i) => i.with_subagents))), [t.limit, u]), g = (i) => m.left + i / Math.max(f, 1) * (_ - m.left - m.right), y = (i) => R - m.bottom - i / d * (R - m.top - m.bottom), l = (i) => c ? A[i].dark : A[i].light, v = (i) => u.map((s, B) => `${B ? "L" : "M"}${g(B).toFixed(1)},${y(s[i]).toFixed(1)}`).join(""), k = [0, 0.25, 0.5, 0.75, 1].map((i) => i * d), w = u.findIndex((i) => i.signals.includes("tripped")), x = A.map((i, s) => ({ index: s, name: i.name, value: u[f][i.key], at: y(u[f][i.key]) })).sort((i, s) => i.at - s.at);
  for (let i = 1; i < x.length; i += 1) x[i].at = Math.max(x[i].at, x[i - 1].at + 30);
  const S = x[x.length - 1].at - (R - m.bottom);
  S > 0 && x.forEach((i) => i.at -= S);
  const h = r === null ? null : u[r], $ = [1, 10, 20, 30, 40, 50, 60].filter((i) => i <= t.cycles), z = (i) => u.findIndex((s) => s.cycle === i);
  return /* @__PURE__ */ n("div", { children: [
    /* @__PURE__ */ n("div", { style: { display: "flex", gap: 18, flexWrap: "wrap", fontSize: 12, margin: "8px 0 2px" }, "aria-label": "Legend", children: [
      A.map((i, s) => /* @__PURE__ */ n("span", { style: { display: "inline-flex", alignItems: "center", gap: 6 }, children: [
        /* @__PURE__ */ e("span", { style: { width: 14, height: 3, borderRadius: 2, background: l(s) } }),
        i.name
      ] }, i.key)),
      /* @__PURE__ */ n("span", { style: { display: "inline-flex", alignItems: "center", gap: 6, color: "var(--muted)" }, children: [
        /* @__PURE__ */ e("span", { style: { width: 14, borderTop: "2px dashed currentColor" } }),
        "Limit"
      ] })
    ] }),
    /* @__PURE__ */ n("div", { style: { position: "relative", maxWidth: _ }, children: [
      /* @__PURE__ */ n(
        "svg",
        {
          viewBox: `0 0 ${_} ${R}`,
          width: "100%",
          role: "img",
          "aria-label": `Line chart of credits spent over ${t.cycles} cycles, counted three ways`,
          onMouseLeave: () => o(null),
          onMouseMove: (i) => {
            const s = i.currentTarget.getBoundingClientRect(), B = (i.clientX - s.left) / s.width * _, U = Math.round((B - m.left) / (_ - m.left - m.right) * f);
            o(U >= 0 && U <= f ? U : null);
          },
          children: [
            k.map((i) => /* @__PURE__ */ n("g", { children: [
              /* @__PURE__ */ e("line", { x1: m.left, x2: _ - m.right, y1: y(i), y2: y(i), stroke: "var(--border)", strokeWidth: 1 }),
              /* @__PURE__ */ e("text", { x: m.left - 8, y: y(i) + 4, textAnchor: "end", fontSize: 11, fill: "var(--muted)", children: p(i) })
            ] }, i)),
            $.map((i) => /* @__PURE__ */ e("text", { x: g(Math.max(z(i), 0)), y: R - m.bottom + 16, textAnchor: "middle", fontSize: 11, fill: "var(--muted)", children: i }, i)),
            /* @__PURE__ */ e("text", { x: (m.left + _ - m.right) / 2, y: R - 2, textAnchor: "middle", fontSize: 11, fill: "var(--muted)", children: "Cycle" }),
            /* @__PURE__ */ e("line", { x1: m.left, x2: _ - m.right, y1: y(t.limit), y2: y(t.limit), stroke: "var(--muted)", strokeWidth: 1.5, strokeDasharray: "5 4" }),
            /* @__PURE__ */ n("text", { x: m.left + 6, y: y(t.limit) - 6, fontSize: 11, fill: "var(--muted)", children: [
              "Limit ",
              p(t.limit)
            ] }),
            A.map((i, s) => /* @__PURE__ */ e("path", { d: v(i.key), fill: "none", stroke: l(s), strokeWidth: 2, strokeLinejoin: "round", strokeLinecap: "round" }, i.key)),
            w >= 0 && /* @__PURE__ */ n("g", { children: [
              /* @__PURE__ */ e("circle", { cx: g(w), cy: y(u[w].capped), r: 5, fill: l(2), stroke: "var(--card, var(--bg))", strokeWidth: 2 }),
              /* @__PURE__ */ n("text", { x: g(w) + 9, y: y(u[w].capped) - 9, fontSize: 11, fill: "var(--text)", children: [
                "Trips, cycle ",
                u[w].cycle
              ] })
            ] }),
            x.map((i) => /* @__PURE__ */ n("g", { children: [
              /* @__PURE__ */ e("line", { x1: _ - m.right + 4, x2: _ - m.right + 14, y1: i.at, y2: i.at, stroke: l(i.index), strokeWidth: 3, strokeLinecap: "round" }),
              /* @__PURE__ */ e("text", { x: _ - m.right + 20, y: i.at - 1, fontSize: 11, fill: "var(--muted)", children: i.name }),
              /* @__PURE__ */ e("text", { x: _ - m.right + 20, y: i.at + 12, fontSize: 12, fontWeight: 600, fill: "var(--text)", children: p(i.value) })
            ] }, i.index)),
            r !== null && h && /* @__PURE__ */ n("g", { pointerEvents: "none", children: [
              /* @__PURE__ */ e("line", { x1: g(r), x2: g(r), y1: m.top, y2: R - m.bottom, stroke: "var(--muted)", strokeWidth: 1 }),
              A.map((i, s) => /* @__PURE__ */ e("circle", { cx: g(r), cy: y(h[i.key]), r: 4, fill: l(s), stroke: "var(--card, var(--bg))", strokeWidth: 2 }, i.key))
            ] })
          ]
        }
      ),
      r !== null && h && /* @__PURE__ */ n(
        "div",
        {
          style: {
            position: "absolute",
            top: 8,
            left: `${Math.min(g(r) / _ * 100 + 2, 62)}%`,
            background: "var(--bg-elevated, var(--bg))",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "8px 10px",
            fontSize: 12,
            pointerEvents: "none",
            minWidth: 190,
            boxShadow: "var(--shadow-md, none)"
          },
          children: [
            /* @__PURE__ */ n("div", { style: { fontWeight: 600, marginBottom: 4 }, children: [
              "Cycle ",
              h.cycle,
              ": ",
              h.what
            ] }),
            A.map((i, s) => /* @__PURE__ */ n("div", { style: { display: "flex", justifyContent: "space-between", gap: 12 }, children: [
              /* @__PURE__ */ n("span", { style: { display: "inline-flex", alignItems: "center", gap: 6, color: "var(--muted)" }, children: [
                /* @__PURE__ */ e("span", { style: { width: 10, height: 3, borderRadius: 2, background: l(s) } }),
                i.name
              ] }),
              /* @__PURE__ */ e("span", { style: { fontVariantNumeric: "tabular-nums" }, children: p(h[i.key]) })
            ] }, i.key))
          ]
        }
      )
    ] }),
    /* @__PURE__ */ n("details", { style: { marginTop: 6, fontSize: 12 }, children: [
      /* @__PURE__ */ e("summary", { style: { cursor: "pointer", color: "var(--muted)" }, children: "Show as a table" }),
      /* @__PURE__ */ e("div", { style: { maxHeight: 260, overflow: "auto", marginTop: 6 }, children: /* @__PURE__ */ n("table", { style: { borderCollapse: "collapse", width: "100%", fontVariantNumeric: "tabular-nums" }, children: [
        /* @__PURE__ */ e("thead", { children: /* @__PURE__ */ n("tr", { style: { textAlign: "right", color: "var(--muted)" }, children: [
          /* @__PURE__ */ e("th", { style: { textAlign: "left", padding: "4px 8px" }, children: "End of cycle" }),
          A.map((i) => /* @__PURE__ */ e("th", { style: { padding: "4px 8px", fontWeight: 500 }, children: i.name }, i.key))
        ] }) }),
        /* @__PURE__ */ e("tbody", { children: Array.from({ length: t.cycles }, (i, s) => s + 1).map((i) => {
          const s = [...u].reverse().find((B) => B.cycle === i);
          return s ? /* @__PURE__ */ n("tr", { style: { textAlign: "right", borderTop: "1px solid var(--border)" }, children: [
            /* @__PURE__ */ e("td", { style: { textAlign: "left", padding: "4px 8px" }, children: i }),
            A.map((B) => /* @__PURE__ */ e("td", { style: { padding: "4px 8px" }, children: p(s[B.key]) }, B.key))
          ] }, i) : null;
        }) })
      ] }) })
    ] })
  ] });
}
const M = "/api/apps/breaker", pe = 5e3, D = {
  unattended: {
    text: "Holds with no page open",
    variant: "ok",
    help: "Breaker started this work and owns its session, so it removes the loop itself."
  },
  while_open: {
    text: "Holds while this page is open",
    variant: "warn",
    help: "You started this loop, so only you may pause it. An open Breaker page does it for you."
  },
  watch: {
    text: "Watch only",
    variant: "muted",
    help: "Nothing here can be stopped without refusing a message you typed. Breaker records the trip."
  }
}, L = { padding: "10px 10px", verticalAlign: "top", fontSize: 13 }, q = { ...L, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }, W = { padding: "6px 10px", fontSize: 11, fontWeight: 500, color: "var(--muted)", textAlign: "left", whiteSpace: "nowrap" }, C = { color: "var(--muted)", fontSize: 12 }, Y = { fontFamily: "var(--mono, monospace)", fontSize: 11, color: "var(--muted)" };
function E(t) {
  const a = t instanceof Error ? t.message : String(t), c = t == null ? void 0 : t.body;
  if (c)
    try {
      const r = JSON.parse(c);
      if (r.error) return r.error;
    } catch {
    }
  return a;
}
function Be() {
  const t = O(), a = P(), c = ee(), [r, o] = b(null), [u, f] = b(""), [d, g] = b("sessions"), y = re(/* @__PURE__ */ new Set()), l = X(async () => {
    try {
      o(await t.get(`${M}/state`)), f("");
    } catch (h) {
      f(E(h));
    }
  }, [t]);
  j(() => {
    l();
    const h = window.setInterval(() => void l(), pe);
    return () => window.clearInterval(h);
  }, [l]);
  const v = X(
    async (h) => {
      let $ = !0, z = "loop paused from the Breaker page; a turn already running is left to finish";
      try {
        if (h.kind !== "pause_loop") throw new Error(`unknown action ${h.kind}`);
        await t.patch(`/api/autonudge/${encodeURIComponent(h.loop_id)}`, { active: !1 });
      } catch (i) {
        $ = !1, z = `the page could not pause the loop: ${E(i)}`;
      }
      try {
        await t.post(`${M}/page-actions/${encodeURIComponent(h.id)}/done`, { ok: $, detail: z });
      } catch {
      }
      a($ ? "Breaker paused a loop that reached its credit limit." : z, { type: $ ? "success" : "error" }), l();
    },
    [t, a, l]
  );
  j(() => {
    for (const h of (r == null ? void 0 : r.page_actions) ?? [])
      y.current.has(h.id) || (y.current.add(h.id), v(h));
  }, [r, v]);
  const k = (r == null ? void 0 : r.sessions) ?? [], w = k.filter((h) => h.cap && h.cap.limit > 0), x = w.filter((h) => {
    var $;
    return (($ = h.cap) == null ? void 0 : $.state) === "tripped";
  }), S = x.filter((h) => {
    var $;
    return (($ = h.cap) == null ? void 0 : $.mode) === "enforce";
  }).length;
  return j(() => {
    c(S);
  }, [S, c]), /* @__PURE__ */ n(J, { children: [
    /* @__PURE__ */ e(te, { title: "Breaker", subtitle: "A circuit breaker for credits: a session is counted with the subagents it started" }),
    /* @__PURE__ */ n("div", { style: { padding: "0 24px 32px", overflowY: "auto", flex: 1, minHeight: 0 }, children: [
      u && /* @__PURE__ */ n(V, { tone: "danger", children: [
        "Breaker's backend did not answer: ",
        u
      ] }),
      r && !r.meter.ok && /* @__PURE__ */ n(V, { tone: "danger", children: [
        "The usage log can't be read (",
        r.meter.note,
        "). Nothing trips while the meter is unreadable."
      ] }),
      r && r.meter.ok && !r.meter.live_ok && /* @__PURE__ */ n(V, { tone: "warn", children: [
        "Breaker can't see the subagents running right now (",
        r.meter.live_note,
        "). Totals count finished turns only, and a subagent that finishes may not be tied to its session."
      ] }),
      /* @__PURE__ */ n("div", { style: { display: "grid", gap: 14, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", margin: "4px 0 18px" }, children: [
        /* @__PURE__ */ e(N, { label: "Credits counted", value: r ? p(r.grand_total) : null, accent: !0 }),
        /* @__PURE__ */ e(N, { label: "Sessions", value: r ? k.length : null }),
        /* @__PURE__ */ e(
          N,
          {
            label: "Subagent credits tied to a session",
            value: r ? p(r.coverage.linked_credits) : null,
            title: r ? `${G(r.coverage.linked_runs, "subagent run")} tied to the session that started it` : void 0
          }
        ),
        /* @__PURE__ */ e(N, { label: "Caps set", value: r ? w.length : null }),
        /* @__PURE__ */ e(N, { label: "Tripped", value: r ? x.length : null })
      ] }),
      /* @__PURE__ */ e("div", { style: { marginBottom: 14 }, children: /* @__PURE__ */ e(
        ue,
        {
          value: d,
          onChange: g,
          tabs: [
            { key: "sessions", label: "Sessions" },
            { key: "start", label: "New run" },
            { key: "replay", label: "Replay" },
            { key: "history", label: "History" },
            { key: "limits", label: "What it can't do" }
          ]
        }
      ) }),
      d === "sessions" && /* @__PURE__ */ e(ge, { state: r, onChanged: l }),
      d === "start" && /* @__PURE__ */ e(we, { state: r, onStarted: () => {
        g("sessions"), l();
      } }),
      d === "replay" && /* @__PURE__ */ e(ce, {}),
      d === "history" && /* @__PURE__ */ e(ke, { state: r }),
      d === "limits" && /* @__PURE__ */ e(Ce, {})
    ] })
  ] });
}
function ue({ value: t, onChange: a, tabs: c }) {
  return /* @__PURE__ */ e("div", { role: "tablist", "aria-label": "Breaker views", style: { display: "inline-flex", flexWrap: "wrap", gap: 2, padding: 3, border: "1px solid var(--border)", borderRadius: 8, background: "var(--card)" }, children: c.map((r) => {
    const o = r.key === t;
    return /* @__PURE__ */ e(
      "button",
      {
        type: "button",
        role: "tab",
        "aria-selected": o,
        onClick: () => a(r.key),
        style: {
          font: "inherit",
          fontSize: 12,
          whiteSpace: "nowrap",
          cursor: "pointer",
          padding: "5px 12px",
          borderRadius: 6,
          border: `1px solid ${o ? "var(--accent)" : "transparent"}`,
          background: o ? "var(--bg-hover, transparent)" : "transparent",
          color: o ? "var(--accent)" : "var(--text)"
        },
        children: r.label
      },
      r.key
    );
  }) });
}
function V({ tone: t, children: a }) {
  return /* @__PURE__ */ e("div", { role: "status", style: { border: `1px solid ${t === "danger" ? "var(--danger, #b91c1c)" : "var(--warn, #b45309)"}`, borderLeftWidth: 4, borderRadius: 6, padding: "10px 12px", fontSize: 13, margin: "0 0 12px", lineHeight: 1.5 }, children: a });
}
function ye(t) {
  return t.title || t.session;
}
function ge({ state: t, onChanged: a }) {
  const [c, r] = b(null);
  return t ? t.sessions.length === 0 ? /* @__PURE__ */ n(T, { children: [
    /* @__PURE__ */ e(K, { children: "No spend yet" }),
    /* @__PURE__ */ n("p", { style: { ...C, fontSize: 13, lineHeight: 1.5, marginTop: 6 }, children: [
      "Breaker reads Kiro Crew's usage log at ",
      /* @__PURE__ */ e("span", { style: Y, children: t.usage_log }),
      ". A session shows up here once one of its turns has finished. Sessions on a harness that bills in dollars are listed and not capped."
    ] })
  ] }) : /* @__PURE__ */ n(T, { children: [
    /* @__PURE__ */ e("div", { style: { overflowX: "auto" }, children: /* @__PURE__ */ n("table", { style: { borderCollapse: "collapse", width: "100%" }, children: [
      /* @__PURE__ */ e("thead", { children: /* @__PURE__ */ n("tr", { children: [
        /* @__PURE__ */ e("th", { style: W, children: "Session" }),
        /* @__PURE__ */ e("th", { style: { ...W, textAlign: "right" }, children: "Its own turns" }),
        /* @__PURE__ */ e("th", { style: { ...W, textAlign: "right" }, children: "Its subagents" }),
        /* @__PURE__ */ e("th", { style: { ...W, textAlign: "right" }, children: "Total" }),
        /* @__PURE__ */ e("th", { style: W, children: "Cap" }),
        /* @__PURE__ */ e("th", { style: W, children: "How it holds" }),
        /* @__PURE__ */ e("th", { style: W })
      ] }) }),
      /* @__PURE__ */ e("tbody", { children: t.sessions.map((o) => /* @__PURE__ */ n(ae, { children: [
        /* @__PURE__ */ n("tr", { style: { borderTop: "1px solid var(--border)" }, children: [
          /* @__PURE__ */ n("td", { style: { ...L, maxWidth: 320 }, children: [
            /* @__PURE__ */ e("div", { style: { fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis" }, children: ye(o) }),
            o.title && /* @__PURE__ */ e("div", { style: Y, children: o.session }),
            /* @__PURE__ */ n("div", { style: { display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }, children: [
              o.owned && /* @__PURE__ */ e(I, { variant: "aim", title: "Started from Breaker; it owns this session", children: "Started from Breaker" }),
              o.orphan_run && /* @__PURE__ */ e(I, { variant: "muted", title: "A subagent whose session Breaker never saw: it started and ended between two looks", children: "Subagent, session unknown" }),
              o.bills_in_dollars && /* @__PURE__ */ e(I, { variant: "muted", title: "This harness bills in dollars. Breaker caps credits only.", children: "Bills in dollars: not capped" }),
              o.loop && /* @__PURE__ */ n(I, { variant: "muted", title: "A goal loop is armed on this session", children: [
                o.loop.active ? "Loop running" : o.loop.max_cycles > 0 && o.loop.cycle_count >= o.loop.max_cycles ? "Loop finished" : "Loop paused",
                ", cycle ",
                o.loop.cycle_count,
                o.loop.max_cycles ? ` of ${o.loop.max_cycles}` : ""
              ] })
            ] })
          ] }),
          /* @__PURE__ */ e("td", { style: q, children: p(o.own) }),
          /* @__PURE__ */ n("td", { style: q, children: [
            p(o.children),
            /* @__PURE__ */ n("div", { style: C, children: [
              G(o.runs, "run"),
              o.running.length > 0 && `, ${o.running.length} running`
            ] })
          ] }),
          /* @__PURE__ */ n("td", { style: { ...q, fontWeight: 600 }, children: [
            p(o.total),
            o.dollars > 0 && /* @__PURE__ */ n("div", { style: C, children: [
              "+ $",
              o.dollars.toFixed(2)
            ] }),
            /* @__PURE__ */ e("div", { style: C, children: Q(o.last_spend) })
          ] }),
          /* @__PURE__ */ e("td", { style: { ...L, minWidth: 190 }, children: /* @__PURE__ */ e(me, { session: o }) }),
          /* @__PURE__ */ e("td", { style: L, children: o.cap && o.cap.limit > 0 ? o.cap.mode === "enforce" ? /* @__PURE__ */ e(I, { variant: D[o.label].variant, title: D[o.label].help, children: D[o.label].text }) : /* @__PURE__ */ e(I, { variant: "muted", title: "A shadow cap is measured the same way and stops nothing", children: "Shadow: stops nothing" }) : /* @__PURE__ */ e("span", { style: C, children: D[o.label].text.replace("Holds", "Would hold") }) }),
          /* @__PURE__ */ e("td", { style: { ...L, whiteSpace: "nowrap", textAlign: "right" }, children: /* @__PURE__ */ e(be, { session: o, editing: c === o.session, onEdit: () => r(c === o.session ? null : o.session), onChanged: a }) })
        ] }),
        c === o.session && /* @__PURE__ */ e("tr", { children: /* @__PURE__ */ e("td", { colSpan: 7, style: { padding: "0 10px 14px" }, children: /* @__PURE__ */ e(ve, { session: o, onDone: async () => {
          r(null), await a();
        } }) }) })
      ] }, o.session)) })
    ] }) }),
    /* @__PURE__ */ e("p", { style: { ...C, marginTop: 12, lineHeight: 1.5 }, children: "A cap counts a session's own turns plus every subagent it started. When it trips, no new cycle starts and a turn or subagent already running finishes. It stays tripped until you restart it; raising the limit restarts nothing. A message you type is never refused." })
  ] }) : /* @__PURE__ */ e(T, { children: /* @__PURE__ */ e("p", { style: C, children: "Reading the meter…" }) });
}
function me({ session: t }) {
  const a = t.cap;
  if (!a || a.limit <= 0) return /* @__PURE__ */ e("span", { style: C, children: "No cap" });
  const c = Math.min(t.total / a.limit, 1), r = a.state === "tripped", o = r ? "var(--danger, #b91c1c)" : a.state === "warned" ? "var(--warn, #b45309)" : "var(--accent)";
  return /* @__PURE__ */ n("div", { children: [
    /* @__PURE__ */ n("div", { style: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }, children: [
      /* @__PURE__ */ e("span", { style: { fontVariantNumeric: "tabular-nums" }, children: p(a.limit) }),
      r ? /* @__PURE__ */ e(I, { variant: "err", children: "Tripped" }) : a.state === "warned" ? /* @__PURE__ */ n(I, { variant: "warn", children: [
        "Past ",
        a.warn_pct,
        "%"
      ] }) : /* @__PURE__ */ e(I, { variant: "muted", children: "Armed" })
    ] }),
    /* @__PURE__ */ e("div", { style: { height: 4, borderRadius: 2, background: "var(--border)", margin: "6px 0 4px", overflow: "hidden" }, "aria-hidden": !0, children: /* @__PURE__ */ e("div", { style: { width: `${c * 100}%`, height: "100%", background: o } }) }),
    a.trip && /* @__PURE__ */ e(fe, { cap: a })
  ] });
}
function fe({ cap: t }) {
  const a = t.trip;
  if (!a) return null;
  const c = t.mode === "shadow" ? "Would have tripped" : "Tripped", r = a.drained_seq === null;
  return /* @__PURE__ */ n("div", { style: { ...C, lineHeight: 1.45 }, children: [
    c,
    " at ",
    p(a.total),
    " against a limit of ",
    p(a.limit),
    ".",
    " ",
    r ? `${G(a.running.length, "subagent")} still running; spend so far ${p(a.peak)}.` : a.overshoot > 0 ? `Spend ended at ${p(a.peak)}, ${p(a.overshoot)} past the limit.` : "Nothing was running, so nothing more was spent."
  ] });
}
function be({ session: t, editing: a, onEdit: c, onChanged: r }) {
  var v, k;
  const o = O(), u = P(), [f, d] = b(""), g = async (w, x, S) => {
    d(w);
    try {
      const h = await o.post(`${M}${x}`, { session: t.session });
      u(S(h), { type: "success" });
    } catch (h) {
      u(E(h), { type: "error" });
    } finally {
      d(""), await r();
    }
  }, y = ((v = t.cap) == null ? void 0 : v.state) === "tripped", l = t.owned && ((k = t.loop) == null ? void 0 : k.active) === !0;
  return /* @__PURE__ */ n("span", { style: { display: "inline-flex", gap: 6 }, children: [
    y && /* @__PURE__ */ e(H, { busy: f === "restart", onClick: () => void g("restart", "/restart", (w) => w.note ? `Restarted: ${w.note}.` : "Restarted. If spend is still over the limit, it trips again at once."), title: "Arm the cap again. Over the limit, it trips again at once.", children: "Restart" }),
    l && !y && /* @__PURE__ */ e(H, { busy: f === "stop", onClick: () => void g("stop", "/runs/stop", () => "Loop removed. A turn already running is left to finish."), children: "Stop loop" }),
    /* @__PURE__ */ e(H, { onClick: c, children: a ? "Close" : t.cap && t.cap.limit > 0 ? "Change cap" : "Set cap" })
  ] });
}
function ve({ session: t, onDone: a }) {
  var x;
  const c = O(), r = P(), [o, u] = b(t.cap && t.cap.limit > 0 ? String(t.cap.limit) : ""), [f, d] = b(((x = t.cap) == null ? void 0 : x.mode) ?? "shadow"), [g, y] = b(!1), l = Number(o), v = o.trim() !== "" && Number.isFinite(l) && l > 0, k = async () => {
    y(!0);
    try {
      await c.put(`${M}/caps`, { session: t.session, limit: l, mode: f }), r(`Cap set at ${p(l)} credits.`, { type: "success" }), await a();
    } catch (S) {
      r(E(S), { type: "error" });
    } finally {
      y(!1);
    }
  }, w = async () => {
    y(!0);
    try {
      await c.post(`${M}/caps/remove`, { session: t.session }), r("Cap removed.", { type: "success" }), await a();
    } catch (S) {
      r(E(S), { type: "error" });
    } finally {
      y(!1);
    }
  };
  return /* @__PURE__ */ n("div", { style: { border: "1px solid var(--border)", borderRadius: 6, padding: 12, display: "grid", gap: 10, maxWidth: 720 }, children: [
    /* @__PURE__ */ n("div", { style: { display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }, children: [
      /* @__PURE__ */ e("label", { htmlFor: `limit-${t.session}`, style: { fontSize: 13 }, children: "Credit limit for this session and its subagents" }),
      /* @__PURE__ */ e("div", { style: { width: 140, display: "flex" }, children: /* @__PURE__ */ e(F, { id: `limit-${t.session}`, type: "number", min: 0, step: "any", value: o, onChange: (S) => u(S.target.value), placeholder: "e.g. 5000" }) }),
      /* @__PURE__ */ e(
        ie,
        {
          ariaLabel: "Cap mode",
          layoutId: `mode-${t.session}`,
          value: f,
          onChange: d,
          segments: [
            { key: "shadow", label: "Shadow" },
            { key: "enforce", label: "Enforce" }
          ]
        }
      )
    ] }),
    /* @__PURE__ */ n("p", { style: { ...C, lineHeight: 1.5, margin: 0 }, children: [
      f === "shadow" ? "Shadow measures the cap and stops nothing. It reports when the limit would have tripped and how far spend ran past it." : `Enforce on this session: ${D[t.label].text.toLowerCase()}. ${D[t.label].help}`,
      t.total > 0 && v && l <= t.total && " This session has already spent more than that, so the cap trips as soon as it is saved."
    ] }),
    /* @__PURE__ */ n("div", { style: { display: "flex", gap: 8 }, children: [
      /* @__PURE__ */ e(H, { primary: !0, busy: g, disabled: !v, onClick: () => void k(), children: "Save cap" }),
      t.cap && /* @__PURE__ */ e(H, { danger: !0, busy: g, onClick: () => void w(), children: "Remove cap" })
    ] })
  ] });
}
function we({ state: t, onStarted: a }) {
  const c = O(), r = P(), [o, u] = b(""), [f, d] = b(""), [g, y] = b("500"), [l, v] = b("10"), [k, w] = b("60"), [x, S] = b(!1), h = (t == null ? void 0 : t.capabilities.chat_slots) ?? !0, $ = o.trim() !== "" && Number(g) > 0, z = async () => {
    S(!0);
    try {
      const s = await c.post(`${M}/runs`, {
        prompt: o,
        title: f,
        limit: Number(g),
        max_cycles: Number(l),
        idle_secs: Number(k)
      });
      r(s.loop_note ? `Started, but no loop was armed: ${s.loop_note}` : "Started under a breaker. The session is listed under Breaker in the sidebar.", { type: s.loop_note ? "error" : "success" }), u(""), d(""), a();
    } catch (s) {
      r(E(s), { type: "error" });
    } finally {
      S(!1);
    }
  }, i = { display: "grid", gap: 4, fontSize: 13 };
  return /* @__PURE__ */ n(T, { children: [
    /* @__PURE__ */ e(K, { children: "Start work under a breaker" }),
    /* @__PURE__ */ e("p", { style: { ...C, fontSize: 13, lineHeight: 1.5, margin: "6px 0 14px", maxWidth: 760 }, children: "Breaker opens a session of its own, sends your prompt, and keeps it going with a goal loop. Because Breaker owns the session, the cap holds with no page open: when the session and its subagents reach the limit, the loop is removed before its next cycle. The turn that is running finishes." }),
    !h && /* @__PURE__ */ e(V, { tone: "warn", children: "This Kiro Crew does not give apps chat sessions of their own, so Breaker can't own work here." }),
    /* @__PURE__ */ n("div", { style: { display: "grid", gap: 12, maxWidth: 760 }, children: [
      /* @__PURE__ */ n("label", { style: i, children: [
        "Goal",
        /* @__PURE__ */ e(
          "textarea",
          {
            value: o,
            onChange: (s) => u(s.target.value),
            rows: 5,
            placeholder: "What should the session work toward?",
            style: { background: "var(--bg-elevated, var(--bg))", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "8px 12px", fontSize: 13, fontFamily: "inherit", resize: "vertical" }
          }
        )
      ] }),
      /* @__PURE__ */ n("label", { style: i, children: [
        "Name (optional)",
        /* @__PURE__ */ e("div", { style: { display: "flex" }, children: /* @__PURE__ */ e(F, { value: f, onChange: (s) => d(s.target.value), maxLength: 80, placeholder: "Shown in the sidebar" }) })
      ] }),
      /* @__PURE__ */ n("div", { style: { display: "grid", gap: 12, alignItems: "start", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }, children: [
        /* @__PURE__ */ n("label", { style: i, children: [
          "Credit limit",
          /* @__PURE__ */ e("div", { style: { display: "flex" }, children: /* @__PURE__ */ e(F, { type: "number", min: 0, step: "any", value: g, onChange: (s) => y(s.target.value) }) })
        ] }),
        /* @__PURE__ */ n("label", { style: i, children: [
          "Most cycles",
          /* @__PURE__ */ e("div", { style: { display: "flex" }, children: /* @__PURE__ */ e(F, { type: "number", min: 0, max: 500, value: l, onChange: (s) => v(s.target.value) }) }),
          /* @__PURE__ */ e("span", { style: C, children: "A second stop, kept by Kiro Crew itself. 0 sends the goal once." })
        ] }),
        /* @__PURE__ */ n("label", { style: i, children: [
          "Seconds idle before the next cycle",
          /* @__PURE__ */ e("div", { style: { display: "flex" }, children: /* @__PURE__ */ e(F, { type: "number", min: 30, max: 3600, value: k, onChange: (s) => w(s.target.value) }) })
        ] })
      ] }),
      /* @__PURE__ */ e("div", { children: /* @__PURE__ */ e(H, { primary: !0, busy: x, disabled: !$ || !h, onClick: () => void z(), children: "Start under a breaker" }) })
    ] })
  ] });
}
const xe = {
  cap_set: "Cap set",
  cap_removed: "Cap removed",
  warned: "Warned",
  tripped: "Tripped",
  drained: "Running work finished",
  restarted: "Restarted",
  stopped: "Stopped",
  stop_failed: "Could not stop",
  page_action_queued: "Waiting for a page",
  run_started: "Started under a breaker"
};
function ke({ state: t }) {
  const a = O(), [c, r] = b(null), [o, u] = b("");
  j(() => {
    a.get(`${M}/history?limit=200`).then((d) => r(d.events)).catch((d) => u(E(d)));
  }, [a, t == null ? void 0 : t.now]);
  const f = new Map(((t == null ? void 0 : t.sessions) ?? []).map((d) => [d.session, d.title]));
  return o ? /* @__PURE__ */ e(V, { tone: "danger", children: o }) : c ? c.length === 0 ? /* @__PURE__ */ e(T, { children: /* @__PURE__ */ e("p", { style: { ...C, fontSize: 13 }, children: "Nothing has happened yet. Caps you set, trips and stops are listed here." }) }) : /* @__PURE__ */ e(T, { children: /* @__PURE__ */ n("table", { style: { borderCollapse: "collapse", width: "100%" }, children: [
    /* @__PURE__ */ e("thead", { children: /* @__PURE__ */ n("tr", { children: [
      /* @__PURE__ */ e("th", { style: W, children: "When" }),
      /* @__PURE__ */ e("th", { style: W, children: "What" }),
      /* @__PURE__ */ e("th", { style: W, children: "Session" }),
      /* @__PURE__ */ e("th", { style: W, children: "Detail" })
    ] }) }),
    /* @__PURE__ */ e("tbody", { children: c.map((d, g) => /* @__PURE__ */ n("tr", { style: { borderTop: "1px solid var(--border)" }, children: [
      /* @__PURE__ */ e("td", { style: { ...L, whiteSpace: "nowrap", color: "var(--muted)" }, children: Q(d.at) }),
      /* @__PURE__ */ n("td", { style: { ...L, whiteSpace: "nowrap" }, children: [
        xe[d.kind] ?? d.kind,
        d.mode === "shadow" && (d.kind === "tripped" || d.kind === "warned") ? " (shadow)" : ""
      ] }),
      /* @__PURE__ */ e("td", { style: L, children: f.get(d.session) || /* @__PURE__ */ e("span", { style: Y, children: d.session }) }),
      /* @__PURE__ */ e("td", { style: { ...L, color: "var(--muted)" }, children: Se(d) })
    ] }, `${d.at}-${g}`)) })
  ] }) }) : /* @__PURE__ */ e(T, { children: /* @__PURE__ */ e("p", { style: C, children: "Loading…" }) });
}
function Se(t) {
  const a = [];
  return t.kind === "cap_set" && t.limit !== void 0 && a.push(`${p(t.limit)} credits, ${t.mode === "enforce" ? "enforced" : "shadow"}`), (t.kind === "tripped" || t.kind === "warned") && t.total !== void 0 && t.limit !== void 0 && a.push(`${p(t.total)} of ${p(t.limit)}`), t.kind === "drained" && t.overshoot !== void 0 && a.push(`${p(t.overshoot)} past the limit`), t.kind === "run_started" && t.limit !== void 0 && a.push(`limit ${p(t.limit)}`), t.detail && a.push(t.detail), a.join(". ");
}
function Ce() {
  const t = { fontSize: 13, lineHeight: 1.55, margin: "0 0 8px" };
  return /* @__PURE__ */ n("div", { style: { display: "grid", gap: 16, maxWidth: 820 }, children: [
    /* @__PURE__ */ n(T, { children: [
      /* @__PURE__ */ e(K, { children: "What Breaker can't do" }),
      /* @__PURE__ */ n("ul", { style: { paddingLeft: 18, margin: "8px 0 0" }, children: [
        /* @__PURE__ */ n("li", { style: t, children: [
          /* @__PURE__ */ e("b", { children: "It can't refuse a turn before it starts" }),
          ", except on work it owns. A Kiro Crew app has no hook in front of a turn. So a cap on your own loop is held by pausing the loop, and only while a Breaker page is open."
        ] }),
        /* @__PURE__ */ n("li", { style: t, children: [
          /* @__PURE__ */ e("b", { children: "It never cuts a running turn or subagent." }),
          " Spend can run past the limit while they finish. Breaker measures that and shows it."
        ] }),
        /* @__PURE__ */ n("li", { style: t, children: [
          /* @__PURE__ */ e("b", { children: "A subagent that finishes can still wake its session" }),
          ", and that turn can start more subagents. Breaker stops the loop, not that wake."
        ] }),
        /* @__PURE__ */ n("li", { style: t, children: [
          /* @__PURE__ */ e("b", { children: "A subagent that starts and ends between two looks" }),
          ' (about 10 seconds apart) is counted, and not tied to its session. It is listed as "Subagent, session unknown".'
        ] }),
        /* @__PURE__ */ n("li", { style: t, children: [
          /* @__PURE__ */ e("b", { children: "Credits only." }),
          " A harness that bills in dollars is listed and never capped."
        ] }),
        /* @__PURE__ */ n("li", { style: t, children: [
          /* @__PURE__ */ e("b", { children: "It stops nothing you type." }),
          " A message you send always runs."
        ] })
      ] })
    ] }),
    /* @__PURE__ */ n(T, { children: [
      /* @__PURE__ */ e(K, { children: "What an app would need from Kiro Crew to do this properly" }),
      /* @__PURE__ */ n("ul", { style: { paddingLeft: 18, margin: "8px 0 0" }, children: [
        /* @__PURE__ */ e("li", { style: t, children: "The parent session written on each subagent's usage row, so the link doesn't have to be caught while the run is alive." }),
        /* @__PURE__ */ e("li", { style: t, children: "A check an app can answer before a loop's next cycle, so a cap holds on any loop with no page open." }),
        /* @__PURE__ */ e("li", { style: t, children: "A stop reason an app can set on a loop it paused, shown where the loop is shown." }),
        /* @__PURE__ */ e("li", { style: t, children: "The same check before a subagent is spawned, to close the wake gap above." })
      ] }),
      /* @__PURE__ */ e("p", { style: { ...C, marginTop: 6, lineHeight: 1.5 }, children: "Breaker is a working prototype of the session cap proposed in KiroCrew#35488, built only from what Kiro Crew v0.13.1 gives a third-party app." })
    ] })
  ] });
}
export {
  Be as default
};
