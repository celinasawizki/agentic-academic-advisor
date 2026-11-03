"use client"

import { AlertTriangle, ArrowUpRight, CheckCircle2, ClipboardCheck, Globe2, Loader2, PlayCircle, Users } from "lucide-react"
import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { Pill, ReviewBadge } from "@/components/planner/badges"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { api, type AdvisorStudent } from "@/lib/api"

export default function AdvisorPage() {
  const [rows, setRows] = useState<AdvisorStudent[] | null>(null)
  const [running, setRunning] = useState<string | null>(null)

  const load = useCallback(() => api.advisorOverview().then(setRows).catch((e) => toast.error(e.message)), [])
  useEffect(() => { load() }, [load])

  const runPlan = async (sid: string) => {
    setRunning(sid)
    try {
      await api.createPlan(sid)
      await new Promise((r) => setTimeout(r, 1500))
      await load()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setRunning(null)
    }
  }

  const needs = rows?.filter((r) => r.needs_review).length ?? 0
  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><Users className="size-6 text-primary" /> Advisor view</h1>
          <p className="mt-1 text-sm text-muted-foreground">The same agents and checks, summarized for an advisor&apos;s caseload. Fictional students only.</p>
        </div>
        <div className="flex gap-2 text-sm">
          <Pill tone="warning" icon={AlertTriangle}>{needs} plan(s) need review</Pill>
          <Pill>Demo role gate — production requires Temple SSO & advisor assignment</Pill>
        </div>
      </div>

      {!rows ? (
        <div className="mt-10 flex justify-center"><Loader2 className="size-6 animate-spin text-primary" /></div>
      ) : (
        <div className="mt-6 space-y-4">
          {rows.map((s) => (
            <article key={s.student_id} className="rounded-2xl border bg-card p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-semibold">{s.name}</h2>
                  <p className="text-xs text-muted-foreground">
                    {s.academic_year} · {s.programs.join(", ")} · graduating {s.expected_graduation}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {s.f1 && <Pill tone="info" icon={Globe2}>F-1</Pill>}
                    {s.needs_review ? <Pill tone="warning" icon={AlertTriangle}>Needs advisor review</Pill> : s.plan_id && <Pill tone="success" icon={CheckCircle2}>No conflicts</Pill>}
                    {s.advisor_review && <Pill tone="cherry" icon={ClipboardCheck}>Advisor: {s.advisor_review.status.replace("_", " ")}</Pill>}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={running === s.student_id} onClick={() => runPlan(s.student_id)}>
                    {running === s.student_id ? <Loader2 className="animate-spin" /> : <PlayCircle />} {s.plan_id ? "Re-run agents" : "Run agents"}
                  </Button>
                  {s.plan_id && (
                    <Link href={`/plan/${s.plan_id}/schedules`} className="inline-flex h-7 items-center gap-1 rounded-lg px-2.5 text-[0.8rem] font-medium text-primary hover:bg-muted">
                      Open plan <ArrowUpRight className="size-3.5" />
                    </Link>
                  )}
                </div>
              </div>

              {s.plan_id && (
                <div className="mt-4 grid gap-4 lg:grid-cols-3">
                  <div>
                    <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">Unresolved requirements</h3>
                    <ul className="space-y-1 text-xs">
                      {s.remaining_requirements!.map((r) => (
                        <li key={r.id} className="flex justify-between gap-2"><span>{r.program}: {r.name}</span><span className="text-muted-foreground">{r.needed}</span></li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">Scheduling conflicts & risks</h3>
                    <ul className="space-y-1 text-xs">
                      {s.conflicts!.map((c) => <li key={c} className="text-warning">• {c}</li>)}
                      {s.risks!.map((r) => <li key={r.issue} className="text-warning">• {r.issue}</li>)}
                      {s.critical_courses!.length > 0 && <li>Graduation-critical: {s.critical_courses!.join(", ")}</li>}
                      {!s.conflicts!.length && !s.risks!.length && <li className="text-muted-foreground">None detected</li>}
                    </ul>
                  </div>
                  <div>
                    <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">Proposed options</h3>
                    <ul className="space-y-1.5 text-xs">
                      {s.options!.map((o) => (
                        <li key={o.id}>
                          <div className="flex items-center justify-between gap-2"><span className="font-medium">{o.label} · {o.credits} cr</span><ReviewBadge status={o.review_status} /></div>
                          <div className="text-muted-foreground">{o.courses.join(", ")}</div>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="lg:col-span-3">
                    <p className="rounded-lg bg-muted/50 p-3 text-xs">
                      <span className="font-medium">Planner summary:</span> {s.explanation} {s.ai_summary}
                    </p>
                    <AdvisorNote planId={s.plan_id} onSaved={load} />
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

function AdvisorNote({ planId, onSaved }: { planId: string; onSaved: () => void }) {
  const [note, setNote] = useState("")
  const save = async (status: string) => {
    try {
      await api.advisorReview({ plan_id: planId, status, note })
      toast.success("Advisor review recorded")
      setNote("")
      onSaved()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  return (
    <div className="mt-3 flex flex-col gap-2 sm:flex-row">
      <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={1} placeholder="Note to student (optional)" className="min-h-8" />
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => save("changes_requested")}>Request changes</Button>
        <Button size="sm" onClick={() => save("approved")}>Approve plan</Button>
      </div>
    </div>
  )
}
