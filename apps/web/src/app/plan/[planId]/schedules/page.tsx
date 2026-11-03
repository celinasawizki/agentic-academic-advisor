"use client"

import {
  AlertTriangle, ArrowRightLeft, CalendarCog, CheckCircle2, CircleSlash, Info, Loader2, Lock, LockOpen, MessageSquare, Send, Sparkles,
  Trash2, Upload, XCircle,
} from "lucide-react"
import Link from "next/link"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { AvailabilityGrid } from "@/components/planner/availability-grid"
import { F1Badge, Pill, ReviewBadge, SnapshotData } from "@/components/planner/badges"
import { CourseExplainer } from "@/components/planner/course-explainer"
import { WaitFor, usePlan } from "@/components/planner/plan-context"
import { WeekCalendar, dayHas } from "@/components/planner/week-calendar"
import { Button, buttonVariants } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api, type ValidateResult } from "@/lib/api"
import { meetingLabel } from "@/lib/time"
import type { AvailBlock, OptionSection, Resolution, ScheduleOption } from "@/lib/types"
import { cn } from "@/lib/utils"

const EXAMPLES = ["Give me Fridays off", "Find more courses related to AI", "Move my classes later in the day", "I want to take 18 credits instead", "I got a job on Tuesdays. Rebuild my schedule."]

export default function SchedulesPage() {
  const { stable, busy } = usePlan()
  return (
    <WaitFor ready={!!stable} label="Optimizing and reviewing schedules…">
      {stable && (
        <div className="relative">
          {busy && (
            <div className="sticky top-16 z-30 mb-3 flex items-center justify-center gap-2 rounded-xl border border-primary/30 bg-cherry-soft px-4 py-2 text-sm font-medium text-primary shadow-sm">
              <Loader2 className="size-4 animate-spin" /> Agents are re-planning with your changes — showing the previous result until they finish.
            </div>
          )}
          <div className={cn(busy && "pointer-events-none opacity-60 transition-opacity")}>
            <Builder />
          </div>
        </div>
      )}
    </WaitFor>
  )
}

function Builder() {
  const { stable: plan, refresh } = usePlan()
  const st = plan!.state
  const opt = st.schedule_optimization!
  const reviews = st.academic_review!.reviews
  const expl = st.student_explanation!
  const prefs = st._student.preferences
  const [selectedId, setSelectedId] = useState<string | null>(opt.options[0]?.id ?? null)
  const [focusSection, setFocusSection] = useState<string | null>(null)
  const [editState, setEditState] = useState<{ iter: number; sections: OptionSection[] | null; validation: ValidateResult | null }>({ iter: 0, sections: null, validation: null })
  const [availOpen, setAvailOpen] = useState(false)
  const [exportResult, setExportResult] = useState<Awaited<ReturnType<typeof api.saveDraft>> | null>(null)
  const [busy, setBusy] = useState(false)

  const fresh = editState.iter === plan!.iteration
  const edited = fresh ? editState.sections : null
  const validation = fresh ? editState.validation : null
  const setEdited = (sections: OptionSection[] | null) => setEditState((e) => ({ ...e, iter: plan!.iteration, sections, validation: sections ? e.validation : null }))
  const setValidation = (validation: ValidateResult | null) => setEditState((e) => ({ ...e, iter: plan!.iteration, validation }))

  const selected = opt.options.find((o) => o.id === selectedId) ?? opt.options[0] ?? null
  const sections = edited ?? selected?.sections ?? []

  const rerun = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true)
    try {
      await fn()
      toast.success(msg)
      await refresh()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const toggleLock = (sid: string) => {
    const locked = prefs.locked_sections.includes(sid) ? prefs.locked_sections.filter((x) => x !== sid) : [...prefs.locked_sections, sid]
    rerun(() => api.preferences(plan!.id, { locked_sections: locked }), "Lock updated — agents are re-planning")
  }
  const removeCourse = (course: string) =>
    rerun(() => api.preferences(plan!.id, { excluded_courses: [...prefs.excluded_courses, course] }), `${course} removed — agents are re-planning`)

  const swap = async (section: OptionSection, altId: string) => {
    const alt = st.course_discovery!.eligible_sections.find((e) => e.section.id === altId)
    if (!alt) return
    const next = sections.map((s) => (s.id === section.id
      ? { ...s, ...alt.section, id: alt.section.id, credits: alt.section.credits ?? s.credits,
          requires_linked_section: alt.requires_linked_section, time_tba: alt.time_tba }
      : s))
    setEdited(next)
    setFocusSection(altId)
    try {
      setValidation(await api.validate(plan!.id, next.map((s) => s.id)))
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const exportDraft = async () => {
    if (!selected) return
    setBusy(true)
    try {
      setExportResult(await api.saveDraft(plan!.id, selected.id))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const focused = sections.find((s) => s.id === focusSection) ?? null
  const focusedExpl = expl.options.find((o) => o.option_id === selected?.id)?.courses.find((c) => c.course === focused?.course) ?? null

  return (
    <div className="space-y-6">
      <ConflictBanner perfect={opt.ideal_analysis.perfect_exists} headline={expl.headline} conflicts={opt.ideal_analysis.conflict_set.map((g) => g.description)}
        details={expl.conflict_explanation.details} minimal={!!opt.ideal_analysis.minimal} resolutions={opt.ideal_analysis.resolutions}
        options={opt.options} onSelect={setSelectedId}
        onReduceCredits={(n) => rerun(() => api.preferences(plan!.id, { credit_min: Math.min(prefs.credit_min, n), credit_target: n }), "Credit load updated")}
        onEditAvailability={() => setAvailOpen(true)} />

      {opt.infeasible_strategies.filter((inf) => opt.ideal_analysis.perfect_exists
        || inf.conflict_set.map((g) => g.key).sort().join() !== opt.ideal_analysis.conflict_set.map((g) => g.key).sort().join()).map((inf) => (
        <div key={inf.strategy} className="rounded-2xl border border-destructive/25 bg-destructive/5 p-4 text-sm">
          <div className="flex items-center gap-2 font-semibold text-destructive"><CircleSlash className="size-4" /> {inf.label}: no valid schedule</div>
          <p className="mt-1 text-muted-foreground">
            The solver proved these constraints cannot all hold{inf.minimal ? " (irreducible conflict set — removing any one restores feasibility)" : ""}:
          </p>
          <ul className="mt-2 flex flex-wrap gap-1.5">{inf.conflict_set.map((g) => <Pill key={g.key} tone="danger">{g.description}</Pill>)}</ul>
          <ResolutionList resolutions={inf.resolutions} options={opt.options} onSelect={setSelectedId}
            onReduceCredits={(n) => rerun(() => api.preferences(plan!.id, { credit_min: Math.min(prefs.credit_min, n), credit_target: n }), "Credit load updated")}
            onEditAvailability={() => setAvailOpen(true)} />
        </div>
      ))}

      <div className="grid gap-3 md:grid-cols-3">
        {opt.options.map((o) => (
          <OptionCard key={o.id} o={o} active={o.id === selected?.id} review={reviews[o.id]?.status} onClick={() => { setSelectedId(o.id); setEdited(null); setValidation(null) }} />
        ))}
      </div>

      {selected && (
        <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold">{selected.label}</h2>
                <ReviewBadge status={reviews[selected.id]?.status} />
                <F1Badge status={selected.f1.status} />
                <SnapshotData />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => setAvailOpen(true)}><CalendarCog /> Availability</Button>
                <CreditControl key={prefs.credit_target} value={prefs.credit_target} min={prefs.credit_min} max={prefs.credit_max} disabled={busy}
                  onApply={(n) => rerun(() => api.preferences(plan!.id, { credit_target: n, credit_min: Math.min(prefs.credit_min, n), credit_max: Math.max(prefs.credit_max, n) }), `Target set to ${n} credits`)} />
                <Button size="sm" onClick={exportDraft} disabled={busy || !!edited || reviews[selected.id]?.status === "rejected"}>
                  <Upload /> Save draft to TUportal (mock)
                </Button>
              </div>
            </div>
            {edited && (
              <div className={cn("flex flex-wrap items-center justify-between gap-2 rounded-xl border p-3 text-sm", validation?.valid ? "border-success/30 bg-success-soft" : "border-destructive/30 bg-destructive/5")}>
                <div className="flex items-center gap-2">
                  {validation ? (validation.valid ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />) : <Loader2 className="size-4 animate-spin" />}
                  <span className="font-medium">Manual edit — {validation ? (validation.valid ? "passes deterministic checks" : "fails validation") : "validating…"}</span>
                  {validation && <span className="text-muted-foreground">{validation.credits} credits</span>}
                </div>
                <div className="flex gap-2">
                  {validation?.valid && focused && (
                    <Button size="sm" variant="outline" onClick={() => toggleLock(focused.id)}><Lock /> Lock this section & re-optimize</Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => { setEdited(null); setValidation(null) }}>Discard</Button>
                </div>
                {validation && (
                  <ul className="w-full space-y-0.5 text-xs">
                    {validation.checks.filter((c) => !c.passed).map((c) => (
                      <li key={c.check} className={c.severity === "error" ? "text-destructive" : "text-warning"}>• {c.detail}</li>
                    ))}
                    {validation.soft_violations.map((v) => <li key={v.detail} className="text-warning">• Preference: {v.detail}</li>)}
                  </ul>
                )}
              </div>
            )}
            <WeekCalendar sections={sections} blocks={st._student.availability} locked={prefs.locked_sections} selected={focusSection} onSelect={setFocusSection} />
            <ChatBox planId={plan!.id} busy={busy} setBusy={setBusy} />
          </div>

          <aside className="space-y-3">
            <div className="rounded-2xl border bg-card">
              <div className="border-b px-4 py-3 text-sm font-semibold">Courses · {sections.reduce((s, x) => s + ((x.component ?? "primary") === "primary" ? x.credits : 0), 0)} credits</div>
              <ul className="divide-y">
                {sections.map((s) => {
                  const alts = st.course_discovery!.eligible_sections.filter((e) => e.course === s.course && e.section.id !== s.id
                    && (e.section.component ?? "primary") === (s.component ?? "primary")).slice(0, 8)
                  const isComponent = (s.component ?? "primary") !== "primary"
                  const isLocked = prefs.locked_sections.includes(s.id)
                  return (
                    <li key={s.id} className={cn("px-4 py-3 text-sm", focusSection === s.id && "bg-cherry-soft/50")}>
                      <button type="button" className="w-full text-left" onClick={() => setFocusSection(s.id)}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold">{s.course}{isComponent && <span className="font-normal"> {s.component}</span>} <span className="font-normal text-muted-foreground">§{s.section} · CRN {s.crn}</span></span>
                          <span className="text-xs text-muted-foreground">{isComponent ? "with course" : `${s.credits} cr`}</span>
                        </div>
                        <div className="text-xs">{s.title}</div>
                        <div className="mt-0.5 text-[11px] text-muted-foreground">
                          {s.meetings.length ? s.meetings.map((m) => meetingLabel(m.days, m.start, m.end)).join("; ") : s.modality === "online" ? "Online asynchronous" : "Time TBA"} · {s.modality.replace("_", "-")} · {s.campus} · {s.instructor}
                        </div>
                      </button>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {s.prereq_status === "conditional" && <Pill tone="warning">{s.prereq_pending.length ? `Conditional on ${s.prereq_pending.join(", ")}` : "Prereq may need placement"}</Pill>}
                        {s.requires_linked_section && <Pill tone="warning">+ linked recitation/lab</Pill>}
                        {s.time_tba && <Pill tone="warning">Time TBA</Pill>}
                        {selected.critical_included.includes(s.course) && <Pill tone="cherry">Graduation-critical</Pill>}
                        {s.interest_score >= 0.5 && <Pill tone="info"><Sparkles className="size-3" /> {Math.round(s.interest_score * 100)}% interest</Pill>}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        <Button size="xs" variant="outline" disabled={busy || !!edited} onClick={() => toggleLock(s.id)}>
                          {isLocked ? <LockOpen /> : <Lock />} {isLocked ? "Unlock" : "Lock"}
                        </Button>
                        {!isComponent && <Button size="xs" variant="outline" disabled={busy || !!edited} onClick={() => removeCourse(s.course)}><Trash2 /> Remove</Button>}
                        {alts.map((a) => (
                          <Button key={a.section.id} size="xs" variant="ghost" onClick={() => swap(s, a.section.id)}
                            title={a.section.meetings.length ? a.section.meetings.map((m) => meetingLabel(m.days, m.start, m.end)).join("; ") : "Online"}>
                            <ArrowRightLeft /> §{a.section.section}
                          </Button>
                        ))}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </div>
            {focusedExpl && !edited ? (
              <CourseExplainer c={focusedExpl} />
            ) : (
              <div className="rounded-2xl border border-dashed p-4 text-center text-xs text-muted-foreground">
                <Info className="mx-auto mb-1 size-4" /> Select a course to see exactly why it was recommended.
              </div>
            )}
            <Link href={`/plan/${plan!.id}/explain`} className={cn(buttonVariants({ variant: "outline" }), "w-full")}>How was this schedule created?</Link>
          </aside>
        </div>
      )}

      <AvailabilityDialog open={availOpen} onOpenChange={setAvailOpen} initial={st._student.availability}
        onSave={(blocks) => { setAvailOpen(false); rerun(() => api.preferences(plan!.id, { availability: blocks }), "Availability updated — agents are re-planning") }} />

      <Dialog open={!!exportResult} onOpenChange={(o) => !o && setExportResult(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Draft saved to mock planning environment</DialogTitle>
            <DialogDescription>{exportResult?.notice}</DialogDescription>
          </DialogHeader>
          {exportResult && (
            <div className="space-y-2 text-sm">
              <div className="rounded-lg bg-muted p-3 font-mono text-xs">
                <div>draft_id: {exportResult.draft.draft_id}</div>
                <div>CRNs: {exportResult.draft.crns.join(", ")}</div>
                <div>environment: {exportResult.draft.environment}</div>
              </div>
              {exportResult.validation.messages.map((m) => <p key={m} className="text-xs text-warning">{m}</p>)}
              <p className="text-xs text-muted-foreground">Actual registration is a separate, explicitly authorized action in TUportal / Self-Service Banner.</p>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function OptionCard({ o, active, review, onClick }: { o: ScheduleOption; active: boolean; review?: string; onClick: () => void }) {
  const fridayFree = !dayHas(o.sections, "F")
  return (
    <button type="button" onClick={onClick}
      className={cn("rounded-2xl border bg-card p-4 text-left transition-all hover:shadow-md", active && "border-primary shadow-md ring-1 ring-primary/30")}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold tracking-wide text-primary uppercase">Option {String.fromCharCode(64 + o.rank)}</span>
        <ReviewBadge status={review} />
      </div>
      <div className="mt-1 text-lg font-semibold">{o.label}</div>
      <div className="mt-0.5 text-xs text-muted-foreground">{[...new Set(o.sections.map((s) => s.course))].join(" · ")}</div>
      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <Metric label="Credits" value={`${o.credits}`} />
        <Metric label="Degree progress" value={o.scores.degree_progress.toFixed(1)} />
        <Metric label="Interest alignment" value={`${Math.round(o.scores.interest_alignment * 100)}%`} />
        <Metric label="Preferences met" value={`${Math.round(o.scores.preference_satisfaction * 100)}%`} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Pill tone={fridayFree ? "success" : "warning"}>{fridayFree ? "Fridays free" : "Friday class"}</Pill>
        {o.critical_missing.length > 0 && <Pill tone="danger">Defers {o.critical_missing.join(", ")}</Pill>}
        {o.soft_violations.length > 0 && <Pill tone="warning">{o.soft_violations.length} preference conflict(s)</Pill>}
      </div>
    </button>
  )
}

const Metric = ({ label, value }: { label: string; value: string }) => (
  <div className="flex justify-between"><span className="text-muted-foreground">{label}</span><span className="font-medium">{value}</span></div>
)

function ConflictBanner(props: {
  perfect: boolean; headline: string; conflicts: string[]; details: string[]; minimal: boolean; resolutions: Resolution[]
  options: ScheduleOption[]; onSelect: (id: string) => void; onReduceCredits: (n: number) => void; onEditAvailability: () => void
}) {
  if (props.perfect) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-success/30 bg-success-soft p-4 text-sm font-medium text-success">
        <CheckCircle2 className="size-5" /> {props.headline}
      </div>
    )
  }
  return (
    <div className="rounded-2xl border border-warning/40 bg-warning-soft/60 p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-warning" />
        <div className="flex-1">
          <h2 className="font-semibold">{props.headline}</h2>
          {props.details.map((d) => <p key={d} className="mt-1 text-sm">{d}</p>)}
          <p className="mt-2 text-xs text-muted-foreground">
            CP-SAT {props.minimal ? "computed an irreducible" : "found a"} set of constraints that cannot all hold together:
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">{props.conflicts.map((c) => <Pill key={c} tone="warning">{c}</Pill>)}</div>
          <ResolutionList {...props} />
        </div>
      </div>
    </div>
  )
}

function ResolutionList({ resolutions, options, onSelect, onReduceCredits, onEditAvailability }: {
  resolutions: Resolution[]; options: ScheduleOption[]; onSelect: (id: string) => void; onReduceCredits: (n: number) => void; onEditAvailability: () => void
}) {
  const CLASS: Record<string, string> = { soft: "Soft preference", hard: "Hard constraint", academic_priority: "Academic priority", immigration: "Immigration rule" }
  const matchOption = (sectionIds: string[]) => options.find((o) => o.sections.map((s) => s.id).sort().join() === [...sectionIds].sort().join())
  const deferOption = (r: Resolution) => options.find((o) => o.critical_missing.includes(r.relaxes.split(":")[1]) && o.soft_violations.length === 0)
  return (
    <div className="mt-4 grid gap-2 md:grid-cols-2">
      {resolutions.map((r, i) => {
        const existing = r.type === "defer_course" ? deferOption(r) : matchOption(r.sections)
        return (
          <div key={r.relaxes} className="rounded-xl border bg-card p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">Option {i + 1}: {r.title}</span>
              <Pill tone={r.constraint_class === "soft" ? "warning" : r.constraint_class === "immigration" ? "danger" : "neutral"}>{CLASS[r.constraint_class] ?? r.constraint_class}</Pill>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{r.detail}</p>
            {r.alternative_note && <p className="mt-1 text-xs text-muted-foreground">{r.alternative_note}</p>}
            {r.feasible && r.courses.length > 0 && <p className="mt-1 text-xs">Verified feasible: {r.courses.join(", ")} ({r.credits} cr)</p>}
            {!r.feasible && r.type !== "not_overridable" && <p className="mt-1 text-xs text-destructive">Relaxing this alone is not enough.</p>}
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">Requires {r.requires}</span>
              {existing ? (
                <Button size="xs" variant="outline" onClick={() => onSelect(existing.id)}>View {existing.label}</Button>
              ) : r.type === "reduce_credits" && r.feasible ? (
                <Button size="xs" variant="outline" onClick={() => onReduceCredits(r.credits)}>Use {r.credits} credits</Button>
              ) : r.type === "change_hard" ? (
                <Button size="xs" variant="outline" onClick={onEditAvailability}>Edit availability</Button>
              ) : null}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function CreditControl({ value, min, max, disabled, onApply }: { value: number; min: number; max: number; disabled: boolean; onApply: (n: number) => void }) {
  const [v, setV] = useState(value)
  return (
    <div className="flex items-center gap-1 rounded-lg border px-1.5">
      <span className="pl-1 text-xs text-muted-foreground">Target</span>
      <Input type="number" min={1} max={24} value={v} onChange={(e) => setV(Number(e.target.value))} className="h-6 w-14 border-0 px-1 text-center shadow-none" />
      <Button size="xs" variant="ghost" disabled={disabled || v === value} onClick={() => onApply(v)} title={`Acceptable ${min}–${max}`}>Apply</Button>
    </div>
  )
}

function ChatBox({ planId, busy, setBusy }: { planId: string; busy: boolean; setBusy: (b: boolean) => void }) {
  const { refresh } = usePlan()
  const [text, setText] = useState("")
  const [last, setLast] = useState<{ applied: string[]; assumptions: string[]; unclear: string[]; mode: string } | null>(null)
  const send = async (message: string) => {
    if (!message.trim()) return
    setBusy(true)
    try {
      const r = await api.modify(planId, message)
      setLast(r)
      setText("")
      if (r.rerun) {
        toast.success("Constraints updated — re-running agents")
        await refresh()
      }
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="rounded-2xl border bg-card p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold"><MessageSquare className="size-4 text-primary" /> Ask for changes</div>
      <form onSubmit={(e) => { e.preventDefault(); send(text) }} className="flex gap-2">
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Give me Fridays off" maxLength={500} />
        <Button type="submit" disabled={busy || !text.trim()}>{busy ? <Loader2 className="animate-spin" /> : <Send />}</Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((e) => (
          <button key={e} type="button" disabled={busy} onClick={() => send(e)} className="rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50">{e}</button>
        ))}
      </div>
      {last && (
        <div className="mt-3 space-y-1 rounded-lg bg-muted/50 p-3 text-xs">
          <div className="text-muted-foreground">Interpreted by {last.mode === "llm" ? "Claude (structured output)" : "deterministic parser"} → structured changes, then the optimizer re-ran:</div>
          {last.applied.map((a) => <div key={a} className="flex items-center gap-1.5"><CheckCircle2 className="size-3 text-success" /> {a}</div>)}
          {last.assumptions.map((a) => <div key={a} className="text-warning">Assumption: {a}</div>)}
          {last.unclear.map((a) => <div key={a} className="text-destructive">{a}</div>)}
        </div>
      )}
    </div>
  )
}

function AvailabilityDialog({ open, onOpenChange, initial, onSave }: { open: boolean; onOpenChange: (o: boolean) => void; initial: AvailBlock[]; onSave: (b: AvailBlock[]) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
        {open && <AvailabilityEditor initial={initial} onCancel={() => onOpenChange(false)} onSave={onSave} />}
      </DialogContent>
    </Dialog>
  )
}

function AvailabilityEditor({ initial, onCancel, onSave }: { initial: AvailBlock[]; onCancel: () => void; onSave: (b: AvailBlock[]) => void }) {
  const [blocks, setBlocks] = useState(initial)
  const hard = useMemo(() => blocks.filter((b) => b.kind === "hard").length, [blocks])
  return (
    <>
        <DialogHeader>
          <DialogTitle>Weekly availability</DialogTitle>
          <DialogDescription>Changing a hard constraint is always your explicit decision. {hard} hard block(s) currently set.</DialogDescription>
        </DialogHeader>
        <AvailabilityGrid value={blocks} onChange={setBlocks} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button onClick={() => onSave(blocks)}>Save & re-plan</Button>
        </div>
    </>
  )
}
