"use client"

import { AlertTriangle, Bot, ChevronDown, Cpu, Lightbulb, Scale, ShieldCheck } from "lucide-react"
import { useState } from "react"

import { AISuggestion, Pill, ReviewBadge } from "@/components/planner/badges"
import { CourseExplainer } from "@/components/planner/course-explainer"
import { WaitFor, usePlan } from "@/components/planner/plan-context"
import { cn } from "@/lib/utils"

export default function ExplainPage() {
  const { stable } = usePlan()
  return <WaitFor ready={!!stable?.state.student_explanation} label="Preparing explanations…">{stable?.state.student_explanation && <Body />}</WaitFor>
}

function Body() {
  const plan = usePlan().stable!
  const st = plan.state
  const ex = st.student_explanation!
  const [optId, setOptId] = useState(ex.options[0]?.option_id)
  const o = ex.options.find((x) => x.option_id === optId)
  const review = st.academic_review!.reviews[optId ?? ""]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {ex.options.map((x) => (
          <button key={x.option_id} type="button" onClick={() => setOptId(x.option_id)}
            className={cn("rounded-full border px-3 py-1 text-sm", x.option_id === optId ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>
            {x.label}
          </button>
        ))}
      </div>

      {o && (
        <>
          <section className="rounded-2xl border bg-card p-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">Why we recommended {o.label}</h2>
              <ReviewBadge status={o.review_status} />
            </div>
            <p className="mt-2 text-sm">{o.summary}</p>
            {o.ai_summary && (
              <div className="mt-3 rounded-xl bg-info-soft/60 p-3 text-sm">
                <div className="mb-1"><AISuggestion /></div>
                {o.ai_summary}
              </div>
            )}
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold"><Scale className="size-4 text-primary" /> Tradeoffs</h3>
                {o.tradeoffs.length ? <ul className="list-disc space-y-1 pl-5 text-sm">{o.tradeoffs.map((t) => <li key={t}>{t}</li>)}</ul> : <p className="text-sm text-muted-foreground">No preference tradeoffs.</p>}
              </div>
              <div>
                <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold"><AlertTriangle className="size-4 text-warning" /> Unresolved / needs verification</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm">{o.unresolved.map((t) => <li key={t}>{t}</li>)}</ul>
              </div>
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-lg font-semibold">Course-by-course</h2>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{o.courses.map((c) => <CourseExplainer key={c.section_id} c={c} />)}</div>
          </section>
        </>
      )}

      {ex.blocked_interest_alternatives.length > 0 && (
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-3 flex items-center gap-2 font-semibold"><Lightbulb className="size-4.5 text-primary" /> Interesting, but not yet eligible</h2>
          {ex.blocked_interest_alternatives.map((b) => (
            <div key={b.course} className="mb-3 text-sm">
              <p>{b.message}</p>
              <p className="mt-1 text-muted-foreground">
                Eligible alternatives: {b.eligible_alternatives.map((a) => `${a.course} ${a.title}${a.in_a_schedule ? " (in a proposed schedule)" : ""}`).join("; ")}
              </p>
            </div>
          ))}
        </section>
      )}

      <HowCreated plan={plan} review={review} />

      <p className="rounded-xl bg-muted/60 p-3 text-xs text-muted-foreground"><ShieldCheck className="mr-1 inline size-3.5" />{ex.disclaimer}</p>
    </div>
  )

}

function HowCreated({ plan, review }: { plan: NonNullable<ReturnType<typeof usePlan>["stable"]>; review?: { checks: { check: string; passed: boolean; severity: string; detail: string }[] } }) {
  const st = plan.state
  const cons = st.scheduling_constraints!
  const [open, setOpen] = useState(true)
  return (
    <section className="rounded-2xl border bg-card">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center justify-between p-5 text-left">
        <h2 className="font-semibold">How was this schedule created?</h2>
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-5 border-t p-5 text-sm">
          <p className="text-muted-foreground">
            A readable summary of the agents&apos; structured outputs and checks. No hidden reasoning is shown — only evidence, tool results and decisions.
          </p>
          <ol className="space-y-2">
            {plan.agents.filter((a) => a.iteration === plan.iteration && a.status === "complete").map((a) => (
              <li key={a.id} className="flex gap-3">
                {a.mode === "llm" ? <Bot className="mt-0.5 size-4 shrink-0 text-info" /> : <Cpu className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
                <div><span className="font-medium">{a.title}:</span> <span className="text-muted-foreground">{a.summary}</span></div>
              </li>
            ))}
          </ol>
          <div className="grid gap-4 md:grid-cols-2">
            <ConstraintList title="Hard constraints (never violated automatically)" items={cons.hard.map((c) => c.description)} tone="danger" />
            <ConstraintList title="Soft preferences (relaxed only with your approval)" items={cons.soft.map((c) => c.description)} tone="warning" />
            <ConstraintList title="Academic requirements (cannot be waived here)" items={cons.academic.map((c) => c.description)} tone="neutral" />
            <ConstraintList title="Immigration rules (cannot be overridden by preferences)" items={cons.immigration.map((c) => c.description)} tone="cherry" />
          </div>
          {review && (
            <div>
              <h3 className="mb-2 font-semibold">Academic Review Agent — deterministic checks for this option</h3>
              <ul className="grid gap-1 text-xs md:grid-cols-2">
                {review.checks.map((c) => (
                  <li key={c.check} className="flex items-start gap-2">
                    <Pill tone={c.passed ? "success" : c.severity === "error" ? "danger" : "warning"}>{c.passed ? "pass" : c.severity}</Pill>
                    <span>{c.detail}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-xs text-muted-foreground">Solver: {st.schedule_optimization!.solver}. Strategies: Graduation Priority, Interest Priority, Work-Life Balance, each with different objective weights; later options are constrained to differ from earlier ones.</p>
        </div>
      )}
    </section>
  )
}

function ConstraintList({ title, items, tone }: { title: string; items: string[]; tone: "danger" | "warning" | "neutral" | "cherry" }) {
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-semibold">{title}</h3>
      {items.length ? (
        <div className="flex flex-wrap gap-1.5">{items.map((i) => <Pill key={i} tone={tone} className="whitespace-normal">{i}</Pill>)}</div>
      ) : <p className="text-xs text-muted-foreground">None</p>}
    </div>
  )
}
