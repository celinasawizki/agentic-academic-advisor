"use client"

import { ArrowRight, Bot, CheckCircle2, ChevronDown, CircleDashed, Cpu, ExternalLink, Globe, History, Loader2, RotateCcw, Search, SkipForward, XCircle } from "lucide-react"
import Link from "next/link"
import { useState } from "react"

import { Pill } from "@/components/planner/badges"
import { usePlan } from "@/components/planner/plan-context"
import { buttonVariants } from "@/components/ui/button"
import type { AgentExecution, RequirementsResearch } from "@/lib/types"
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
    <>
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
            <li>1–2 · Profile → Bulletin research (live search + fetch)</li>
            <li>3–4 · Requirements → Course discovery</li>
            <li>5–6 · Interest matching ∥ Graduation planning</li>
            <li>7–8 · Constraints → CP-SAT optimization</li>
            <li>9 · Independent review (can reject → re-optimize)</li>
            <li>10 · Student explanation</li>
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
    {plan.state.requirements_research && <ResearchPanel r={plan.state.requirements_research} />}
    {agents.some((a) => a.decision?.task) && <DecisionLog agents={agents} />}
    </>
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

const VSTATUS: Record<string, "success" | "warning" | "danger" | "neutral"> = { passed: "success", warnings: "warning", failed: "danger", "n/a": "neutral" }

function DecisionLog({ agents }: { agents: AgentExecution[] }) {
  const rows = agents.filter((a) => a.status === "complete" && a.decision?.task)
  return (
    <section className="mt-6 rounded-2xl border bg-card">
      <div className="border-b px-4 py-3">
        <h3 className="font-semibold">Decision log</h3>
        <p className="text-xs text-muted-foreground">
          Structured summaries built from each agent&apos;s actual output and evidence — not model reasoning. Later agents check earlier findings
          (e.g. Interest Matching cross-checks requirement links and section availability).
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-xs">
          <thead className="bg-muted/40 text-muted-foreground">
            <tr><th className="px-3 py-2">Agent</th><th className="px-3 py-2">Research task &amp; sources</th><th className="px-3 py-2">Findings</th>
              <th className="px-3 py-2">Recommendation</th><th className="px-3 py-2">Validation</th><th className="px-3 py-2">Unresolved</th></tr>
          </thead>
          <tbody>
            {rows.map((a) => {
              const d = a.decision!
              return (
                <tr key={a.id} className="border-t align-top">
                  <td className="px-3 py-2 font-medium whitespace-nowrap">{a.title.replace(" Agent", "")}</td>
                  <td className="px-3 py-2"><div>{d.task}</div><div className="mt-1 text-muted-foreground">{(d.data_sources ?? []).join(" · ")}</div></td>
                  <td className="px-3 py-2"><ul className="list-disc space-y-0.5 pl-4">{(d.findings ?? []).filter(Boolean).map((f) => <li key={f}>{f}</li>)}</ul></td>
                  <td className="px-3 py-2">{d.recommendation}</td>
                  <td className="px-3 py-2"><Pill tone={VSTATUS[d.validation?.status ?? "n/a"]}>{d.validation?.status}</Pill><div className="mt-1 text-muted-foreground">{d.validation?.detail}</div></td>
                  <td className="px-3 py-2">{(d.unresolved ?? []).length ? <ul className="list-disc space-y-0.5 pl-4 text-warning">{d.unresolved!.map((u) => <li key={u}>{u}</li>)}</ul> : <span className="text-muted-foreground">None</span>}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

const FETCH: Record<string, { label: string; tone: "success" | "info" | "warning" | "danger" }> = {
  live: { label: "Fetched live", tone: "success" },
  cache: { label: "Live (cached ≤24 h)", tone: "info" },
  snapshot: { label: "Offline: ingest snapshot", tone: "warning" },
  unavailable: { label: "Unavailable", tone: "danger" },
}

function when(t: string | null | undefined) {
  return t ? new Date(t).toLocaleString([], { dateStyle: "short", timeStyle: "short" }) : ""
}

function ResearchPanel({ r }: { r: RequirementsResearch }) {
  return (
    <section className="mt-6 rounded-2xl border bg-card">
      <div className="border-b px-4 py-3">
        <h3 className="flex items-center gap-2 font-semibold"><Globe className="size-4 text-primary" /> Bulletin research</h3>
        <p className="text-xs text-muted-foreground">
          What the Requirements Research Agent searched for, which official Temple Academic Bulletin page it used, and whether the page
          was read live. {r.live_enabled ? "Live research is on (robots.txt respected, 1 request/second, 24-hour cache)." : "Live research is off; the ingest snapshot was used."}
        </p>
      </div>
      <div className="divide-y text-xs">
        {r.programs.map((p) => (
          <div key={p.program_id} className="grid gap-2 px-4 py-3 md:grid-cols-[1.1fr_1.6fr_1fr]">
            <div>
              <div className="font-medium">{p.name}</div>
              <div className="text-muted-foreground capitalize">{p.type}</div>
            </div>
            <div className="min-w-0">
              {p.query ? (
                <>
                  <div className="flex items-center gap-1.5"><Search className="size-3.5 shrink-0 text-muted-foreground" /><span className="truncate">&ldquo;{p.query}&rdquo;</span></div>
                  <div className="mt-0.5 text-muted-foreground">{p.search_provider}</div>
                  {p.search_results[0] && (
                    <a href={p.search_results[0].url} target="_blank" rel="noreferrer" className="mt-1 inline-flex max-w-full items-center gap-1 text-primary hover:underline">
                      <span className="truncate">{p.search_results[0].url.replace("https://", "")}</span> <ExternalLink className="size-3 shrink-0" />
                    </a>
                  )}
                  <div className={cn("mt-0.5", p.search_matched_catalog_page ? "text-success" : "text-warning")}>
                    {p.search_matched_catalog_page ? "Search found the official program page" : "Search did not return the catalog's page; the catalog's page was used"}
                  </div>
                </>
              ) : (
                <span className="text-muted-foreground">University-wide framework page (no search needed)</span>
              )}
            </div>
            <div className="space-y-1">
              {p.fetch && <Pill tone={FETCH[p.fetch.mode].tone}>{FETCH[p.fetch.mode].label}</Pill>}
              {p.fetch?.retrieved_at && <div className="text-muted-foreground">{when(p.fetch.retrieved_at)}</div>}
              {p.changes && (
                <div className={p.changes.added || p.changes.removed ? "text-warning" : "text-muted-foreground"}>
                  {p.changes.added || p.changes.removed
                    ? `Page changed since ingest: +${p.changes.added} / −${p.changes.removed} rules (page version used)`
                    : `${p.changes.rules_on_page} rules on the page match the planner`}
                </div>
              )}
              {p.fetch?.error && p.fetch.mode !== "live" && <div className="text-muted-foreground">{p.fetch.error}</div>}
            </div>
          </div>
        ))}
        {r.school_layers.map((l) => (
          <div key={l.id} className="grid gap-2 bg-muted/20 px-4 py-3 md:grid-cols-[1.1fr_1.6fr_1fr]">
            <div>
              <div className="font-medium">{l.name}</div>
              <div className="text-muted-foreground">{l.type === "school" ? "School/college rules" : "University rules"} · applied automatically</div>
            </div>
            <div className="min-w-0">
              <a href={l.url} target="_blank" rel="noreferrer" className="inline-flex max-w-full items-center gap-1 text-primary hover:underline">
                <span className="truncate">{l.url.replace("https://", "")}</span> <ExternalLink className="size-3 shrink-0" />
              </a>
              <div className={cn("mt-0.5", l.evidence_missing.length ? "text-warning" : "text-success")}>
                {l.evidence_checked - l.evidence_missing.length}/{l.evidence_checked} quoted bulletin sentences found on the page
                {l.evidence_missing.length > 0 && " — changed rules are marked Ambiguous"}
              </div>
            </div>
            <div className="space-y-1">
              {l.fetch_mode && <Pill tone={FETCH[l.fetch_mode]?.tone ?? "neutral"}>{FETCH[l.fetch_mode]?.label ?? l.fetch_mode}</Pill>}
              {l.retrieved_at && <div className="text-muted-foreground">{when(l.retrieved_at)}</div>}
              <div className="text-muted-foreground">{l.rules} rule(s)</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
