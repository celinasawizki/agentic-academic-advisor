"use client"

import { AlertTriangle, BookCheck, Filter, GraduationCap, Info, Sparkles, Target } from "lucide-react"

import { useState } from "react"

import { AISuggestion, Pill, ReliabilityBadge, ReliabilityLegend } from "@/components/planner/badges"
import { WaitFor, usePlan } from "@/components/planner/plan-context"

import type { RequirementPattern, RequirementProgress } from "@/lib/types"
import { cn } from "@/lib/utils"

export default function Dashboard() {
  const { stable, plan } = usePlan()
  const st = (stable ?? plan)?.state
  const ready = !!(st?.academic_profile && st.degree_requirements && st.interest_matching && st.graduation_planning && st.course_discovery)
  return (
    <WaitFor ready={ready} label="Agents are analyzing your academic record…">
      {ready && <DashboardBody />}
    </WaitFor>
  )
}

function DashboardBody() {
  const { stable, plan } = usePlan()
  const st = (stable ?? plan)!.state
  const prof = st.academic_profile
  const reqs = st.degree_requirements!
  const im = st.interest_matching!
  const grad = st.graduation_planning!
  const disc = st.course_discovery!
  const byProgram = reqs.requirements.reduce<Record<string, RequirementProgress[]>>((acc, r) => {
    ;(acc[r.program_id] ??= []).push(r)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Credits earned" value={prof.earned_credits} sub={`+${prof.in_progress_credits} in progress`} />
        <Stat label="Courses still needed" value={`~${reqs.courses_needed}`} sub={`${reqs.remaining.length} open requirement rules`} />
        <Stat label="Semesters remaining" value={grad.semesters_remaining} sub={`Target ${st._student.expected_graduation}`} />
        <Stat label="Pace needed" value={`${grad.courses_per_term_needed}`} sub="courses per term" tone={grad.on_track ? "ok" : "warn"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section className="rounded-2xl border bg-card p-5">
          <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 font-semibold"><BookCheck className="size-4.5 text-primary" /> Degree progress</h2>
          </header>
          <div className="mb-4 rounded-xl bg-muted/40 p-3 text-xs">
            <div className="mb-1.5 font-medium">How reliable is each rule?</div>
            <ReliabilityLegend counts={reqs.reliability_counts} />
            <p className="mt-1.5 text-muted-foreground">Nothing is marked Verified until a person checks it against your official degree audit or department.</p>
          </div>
          <div className="space-y-6">
            {Object.entries(byProgram).map(([pid, rs]) => <ProgramProgress key={pid} rs={rs} />)}
          </div>
          <p className="mt-4 flex items-start gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" /> Requirements were parsed automatically from the Temple Academic Bulletin
            ({reqs.requirements[0]?.catalog_year ?? "current"} catalog) and are pending verification against your official degree audit. Rules the
            parser could not interpret are flagged for manual review. Courses are not double counted across programs unless a rule allows it.
          </p>
        </section>

        <div className="space-y-6">
          <section className="rounded-2xl border bg-card p-5">
            <header className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-semibold"><Sparkles className="size-4.5 text-primary" /> Academic interests</h2>
              {Object.values(im.scores)[0]?.method === "llm_semantic" ? <AISuggestion /> : <Pill>Concept matching</Pill>}
            </header>
            <p className="rounded-lg bg-muted/50 p-3 text-sm italic">&ldquo;{st._student.interests_text}&rdquo;</p>
            <div className="mt-3 flex flex-wrap gap-1.5">{im.themes.map((t) => <Pill key={t.label} tone="cherry">{t.label}</Pill>)}</div>
            <div className="mt-4 space-y-2">
              <div className="text-xs font-semibold text-muted-foreground">Top matching eligible courses</div>
              {im.ranking.filter((c) => disc.courses[c]?.prereq_status !== "missing").slice(0, 5).map((c) => (
                <div key={c} className="text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{c} · {disc.courses[c]?.title}</span>
                    <span className="font-mono text-muted-foreground">{Math.round(im.scores[c].score * 100)}%</span>
                  </div>
                  <div className="mt-0.5 h-1 rounded-full bg-muted"><div className="h-1 rounded-full bg-primary/70" style={{ width: `${im.scores[c].score * 100}%` }} /></div>
                  <div className="mt-1 text-muted-foreground">{im.scores[c].reason}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border bg-card p-5">
            <h2 className="mb-3 flex items-center gap-2 font-semibold"><GraduationCap className="size-4.5 text-primary" /> Graduation planning</h2>
            {grad.critical_courses.map((c) => (
              <div key={c.course} className="mb-2 flex gap-2 rounded-lg border border-primary/20 bg-cherry-soft p-3 text-xs">
                <Target className="size-4 shrink-0 text-primary" />
                <div><span className="font-semibold">{c.course} is graduation-critical.</span> {c.reason} Unlocks {c.unlocks.join(", ")}.</div>
              </div>
            ))}
            {grad.risks.map((r) => (
              <div key={r.issue} className="mb-2 flex gap-2 rounded-lg bg-warning-soft p-3 text-xs text-warning"><AlertTriangle className="size-4 shrink-0" /> {r.issue}</div>
            ))}
            {(st.scheduling_constraints?.pre_checks ?? []).map((p) => (
              <div key={p.detail} className="mb-2 flex gap-2 rounded-lg bg-warning-soft p-3 text-xs text-warning"><AlertTriangle className="size-4 shrink-0" /> {p.detail}</div>
            ))}
            <div className="mt-3 text-xs text-muted-foreground">
              <div className="mb-1 font-semibold">Planning assumptions (not verified facts)</div>
              <ul className="list-disc space-y-0.5 pl-4">{grad.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
            </div>
          </section>
        </div>
      </div>

      <section className="rounded-2xl border bg-card p-5">
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 font-semibold"><Filter className="size-4.5 text-primary" /> Course discovery · {disc.term_name}</h2>
          <Pill>Class-search snapshot</Pill>
        </header>
        <p className="mb-3 text-sm text-muted-foreground">
          {disc.eligible_sections.length} eligible sections across {new Set(disc.eligible_sections.map((e) => e.course)).size} requirement-relevant courses. Exclusions of courses your programs list by name:
        </p>
        <ul className="grid gap-1.5 text-xs sm:grid-cols-2">
          {disc.excluded.slice(0, 60).map((e, i) => (
            <li key={i} className="flex items-start gap-2 rounded-lg bg-muted/50 px-2.5 py-1.5">
              <span className="font-medium whitespace-nowrap">{e.section ?? e.course}</span>
              <span className="text-muted-foreground">{e.reason}</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub: string; tone?: "ok" | "warn" }) {
  return (
    <div className="rounded-2xl border bg-card p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-3xl font-semibold tracking-tight", tone === "warn" && "text-warning", tone === "ok" && "text-success")}>{value}</div>
      <div className="text-xs text-muted-foreground">{sub}</div>
    </div>
  )
}

function patternText(p: RequirementPattern) {
  if (p.attribute) return `any course with GenEd attribute ${p.attribute}`
  return `any ${p.subject} ${p.min}–${p.max}`
}

function ProgramProgress({ rs }: { rs: RequirementProgress[] }) {
  const [open, setOpen] = useState(false)
  const countable = rs.filter((r) => r.kind === "count" || r.kind === "credits")
  const done = countable.filter((r) => r.status === "complete").length
  const ip = countable.filter((r) => r.status === "in_progress").length
  const manual = rs.filter((r) => r.kind === "manual")
  const groups = rs.filter((r) => r.kind !== "note").reduce<Record<string, RequirementProgress[]>>((acc, r) => {
    ;(acc[r.group || "Requirements"] ??= []).push(r)
    return acc
  }, {})
  const shown = open ? Object.entries(groups) : Object.entries(groups).filter(([, g]) => g.some((r) => r.status !== "complete")).slice(0, 4)
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
        <div className="font-medium">
          {rs[0].program_name} <span className="text-xs font-normal text-muted-foreground capitalize">{rs[0].program_type} · catalog {rs[0].catalog_year ?? "n/a"}</span>
          {rs[0].source_url && <a href={rs[0].source_url} target="_blank" rel="noreferrer" className="ml-1.5 text-xs text-primary hover:underline">bulletin ↗</a>}
        </div>
        <div className="text-xs text-muted-foreground">{done}/{countable.length} rules complete{ip ? ` · ${ip} in progress` : ""}{manual.length ? ` · ${manual.length} manual` : ""}</div>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-muted">
        <div className="bg-success" style={{ width: `${(done / Math.max(1, countable.length)) * 100}%` }} />
        <div className="bg-info/60" style={{ width: `${(ip / Math.max(1, countable.length)) * 100}%` }} />
      </div>
      <div className="mt-2 space-y-2">
        {shown.map(([group, items]) => (
          <div key={group}>
            <div className="mb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{group}</div>
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {items.map((r) => (
                <li key={r.id} className={cn("rounded-lg border px-2.5 py-2 text-xs", r.status === "complete" && "bg-success-soft/40", r.kind === "manual" && "border-warning/40 bg-warning-soft/40")}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-medium">{r.name} <span className="ml-1 inline-block align-middle"><ReliabilityBadge status={r.reliability} title={r.reliability_reason} /></span></span>
                    <Pill tone={r.status === "complete" ? "success" : r.status === "in_progress" ? "info" : r.kind === "manual" ? "warning" : "neutral"}>
                      {r.status === "complete" ? "Complete" : r.status === "in_progress" ? "In progress" : r.kind === "manual" ? "Manual review"
                        : r.kind === "credits" ? `${r.remaining_needed} cr needed` : `${r.remaining_needed} needed`}
                    </Pill>
                  </div>
                  {r.options.length > 1 && (
                    <div className="mt-1 text-muted-foreground">
                      {r.options.slice(0, 12).map((o, i) => {
                        const code = o.join(" & ")
                        return (
                          <span key={code} className={cn(o.every((c) => r.completed.includes(c)) && "text-success line-through decoration-success/40", o.some((c) => r.in_progress.includes(c)) && "text-info")}>
                            {code}{i < Math.min(r.options.length, 12) - 1 ? ", " : ""}
                          </span>
                        )
                      })}
                      {r.options.length > 12 && <span> +{r.options.length - 12} more</span>}
                    </div>
                  )}
                  {r.patterns.length > 0 && <div className="mt-1 text-muted-foreground">Counts: {r.patterns.map(patternText).join("; ")}</div>}
                  {(r.completed.length > 0 || r.in_progress.length > 0) && r.options.length <= 1 && (
                    <div className="mt-1 text-muted-foreground">Applied: {[...r.completed, ...r.in_progress].join(", ")}</div>
                  )}
                  {r.kind === "manual" && <div className="mt-1 text-warning">Couldn&apos;t be parsed automatically — check with your advisor.</div>}
                  {r.notes.slice(0, 2).map((n) => <div key={n} className="mt-1 text-warning">{n}</div>)}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {Object.keys(groups).length > shown.length || open ? (
        <button type="button" onClick={() => setOpen(!open)} className="mt-2 text-xs font-medium text-primary hover:underline">
          {open ? "Show open requirements only" : `Show all ${rs.filter((r) => r.kind !== "note").length} requirement rules`}
        </button>
      ) : null}
    </div>
  )
}
