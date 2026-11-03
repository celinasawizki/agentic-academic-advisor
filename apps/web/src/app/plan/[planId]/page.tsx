"use client"

import { ArrowRight, Bot, CheckCircle2, ChevronDown, CircleDashed, Cpu, ExternalLink, History, Loader2, RotateCcw, SkipForward, XCircle } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { Pill } from "@/components/planner/badges"
import { usePlan } from "@/components/planner/plan-context"
import { buttonVariants } from "@/components/ui/button"
import type { AgentExecution } from "@/lib/types"
import { cn } from "@/lib/utils"

const STATUS: Record<AgentExecution["status"], { icon: React.ComponentType<{ className?: string }>; label: string; cls: string }> = {
  pending: { icon: CircleDashed, label: "Pending", cls: "text-muted-foreground" },
  running: { icon: Loader2, label: "Running", cls: "text-primary animate-spin" },
  complete: { icon: CheckCircle2, label: "Complete", cls: "text-success" },
  failed: { icon: XCircle, label: "Failed", cls: "text-destructive" },
  skipped: { icon: SkipForward, label: "Reused", cls: "text-muted-foreground" },
}

export default function Workspace() {
  const { plan } = usePlan()
  const [viewIter, setViewIter] = useState<number | null>(null)
  if (!plan) return null
  const iterations = [...new Set(plan.agents.map((a) => a.iteration))].sort((a, b) => a - b)
  const iter = viewIter ?? iterations[iterations.length - 1]
  const agents = plan.agents.filter((a) => a.iteration === iter)
  const done = agents.filter((a) => a.status === "complete" || a.status === "skipped").length
  const history = plan.state._history ?? []

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Agent research workspace</h2>
            <p className="text-sm text-muted-foreground">Live status from the orchestrator. Each card is a persisted execution record — not an animation.</p>
          </div>
          {iterations.length > 1 && (
            <div className="flex items-center gap-1 rounded-lg border p-0.5 text-xs">
              {iterations.map((i) => (
                <button key={i} type="button" onClick={() => setViewIter(i)}
                  className={cn("rounded-md px-2.5 py-1", i === iter ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>
                  Run {i}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${(done / Math.max(1, agents.length)) * 100}%` }} />
        </div>
        <ol className="space-y-2.5">
          {agents.map((a, i) => <AgentCard key={a.id} a={a} index={i} />)}
        </ol>
        {plan.status === "complete" && (
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href={`/plan/${plan.id}/schedules`} className={buttonVariants({ size: "lg" })}>View schedule options <ArrowRight /></Link>
            <Link href={`/plan/${plan.id}/dashboard`} className={buttonVariants({ size: "lg", variant: "outline" })}>Academic dashboard</Link>
          </div>
        )}
      </div>
      <aside className="space-y-4">
        <div className="rounded-2xl border bg-card p-4">
          <h3 className="mb-2 text-sm font-semibold">Workflow</h3>
          <ol className="space-y-1.5 text-xs text-muted-foreground">
            <li>1–3 · Profile → Requirements → Course discovery</li>
            <li>4–5 · Interest matching ∥ Graduation planning</li>
            <li>6–7 · Constraints → CP-SAT optimization</li>
            <li>8 · Independent review (can reject → re-optimize)</li>
            <li>9 · Student explanation</li>
          </ol>
          <div className="mt-3 space-y-1.5 border-t pt-3 text-xs">
            <div className="flex items-center gap-2"><Pill tone="info" icon={Bot}>LLM</Pill> Claude produced schema-validated output</div>
            <div className="flex items-center gap-2"><Pill icon={Cpu}>Deterministic</Pill> Rules / solver / fallback logic</div>
          </div>
        </div>
        {history.length > 0 && (
          <div className="rounded-2xl border bg-card p-4">
            <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><History className="size-4" /> Change history</h3>
            <ul className="space-y-3 text-xs">
              {history.map((h, i) => (
                <li key={i}>
                  <div className="font-medium">&ldquo;{h.message}&rdquo;</div>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-muted-foreground">{h.applied.map((x) => <li key={x}>{x}</li>)}</ul>
                  {h.assumptions.map((x) => <div key={x} className="mt-1 text-warning">Assumption: {x}</div>)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  )
}

function AgentCard({ a, index }: { a: AgentExecution; index: number }) {
  const [open, setOpen] = useState(false)
  const S = STATUS[a.status]
  const secs = a.started_at && a.finished_at ? (new Date(a.finished_at).getTime() - new Date(a.started_at).getTime()) / 1000 : null
  const isRevision = a.summary?.startsWith("Revision") && a.status === "pending"
  return (
    <li className={cn("rounded-xl border bg-card transition-shadow", a.status === "running" && "border-primary/40 shadow-md shadow-primary/5")}>
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 p-4 text-left">
        <S.icon className={cn("mt-0.5 size-5 shrink-0", S.cls)} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">{index + 1}</span>
            <span className="font-medium">{a.title}</span>
            <span className={cn("text-xs", S.cls.replace("animate-spin", ""))}>{S.label}</span>
            {a.status === "complete" && (a.mode === "llm" ? <Pill tone="info" icon={Bot}>Claude</Pill> : a.mode === "llm_fallback" ? <Pill tone="warning" icon={RotateCcw}>LLM unavailable → fallback</Pill> : <Pill icon={Cpu}>Deterministic</Pill>)}
            {secs !== null && <span className="text-[11px] text-muted-foreground">{secs < 1 ? `${Math.round(secs * 1000)} ms` : `${secs.toFixed(1)} s`}</span>}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{a.responsibility}</p>
          {a.summary && !isRevision && a.status !== "pending" && <p className="mt-2 text-sm">{a.summary}</p>}
          {isRevision && <p className="mt-2 text-sm text-warning">{a.summary}</p>}
          {a.error && <p className="mt-2 font-mono text-xs text-destructive">{a.error}</p>}
        </div>
        {(a.log.length > 0 || a.sources.length > 0) && <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />}
      </button>
      {open && (
        <div className="space-y-3 border-t px-4 py-3 text-xs">
          {a.log.length > 0 && (
            <div>
              <div className="mb-1 font-semibold">Research log</div>
              <ul className="space-y-1.5">
                {a.log.map((l, i) => (
                  <li key={i} className="rounded-md bg-muted/50 px-2 py-1.5">
                    <div>{l.message}</div>
                    {Object.keys(l.data ?? {}).length > 0 && (
                      <pre className="mt-1 overflow-x-auto font-mono text-[10px] whitespace-pre-wrap text-muted-foreground">{JSON.stringify(l.data, null, 1)}</pre>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {a.sources.length > 0 && (
            <div>
              <div className="mb-1 font-semibold">Sources</div>
              <ul className="space-y-1">
                {a.sources.map((s, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-2">
                    <Pill tone={s.verification_status === "demo_unverified" ? "warning" : "success"}>{s.verification_status.replace("_", " ")}</Pill>
                    <span>{s.description}</span>
                    {s.url && <a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-primary hover:underline">source <ExternalLink className="size-3" /></a>}
                    {s.retrieved_at && <span className="text-muted-foreground">retrieved {new Date(s.retrieved_at).toLocaleDateString()}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  )
}
