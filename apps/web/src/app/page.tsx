import { ArrowRight, BrainCircuit, CalendarCheck2, FileSearch, GitBranch, ScanSearch, ShieldCheck, Sparkles, Workflow } from "lucide-react"
import Link from "next/link"

import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const AGENTS = [
  ["Academic Profile", "Separates completed, in-progress and transfer work"],
  ["Degree Requirements", "Computes what's left, with sources and catalog year"],
  ["Course Discovery", "Finds eligible sections; explains every exclusion"],
  ["Interest Matching", "Ranks courses against your own words"],
  ["Graduation Planning", "Finds prerequisite bottlenecks"],
  ["Scheduling & Constraints", "Hard vs. soft vs. academic vs. immigration rules"],
  ["Schedule Optimization", "OR-Tools CP-SAT, three strategies"],
  ["Academic Review", "Independent re-verification; can reject"],
  ["Student Explanation", "Plain language, never hides uncertainty"],
]

const PILLARS = [
  { icon: FileSearch, title: "Academic intelligence", body: "Degree audit upload, requirement matching by catalog year, prerequisite chains, and provenance on every fact." },
  { icon: Sparkles, title: "Personal interest matching", body: "Describe what excites you in plain language. Courses are ranked by meaning, not keyword lists." },
  { icon: CalendarCheck2, title: "Constraint optimization", body: "A real CP-SAT solver guarantees hard constraints. When no perfect schedule exists, it tells you exactly which constraints conflict." },
  { icon: ShieldCheck, title: "No black box", body: "Every recommendation shows which requirement it may satisfy, why the section was chosen, and what is still unverified." },
]

export default function Landing() {
  return (
    <div>
      <section className="relative overflow-hidden border-b">
        <div className="bg-grid absolute inset-0 [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_75%)]" />
        <div className="absolute -top-40 left-1/2 h-96 w-[60rem] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative mx-auto max-w-5xl px-6 pt-20 pb-24 text-center">
          <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border bg-background/80 px-3 py-1 text-xs text-muted-foreground shadow-sm">
            <Workflow className="size-3.5 text-primary" /> 9 specialized agents · deterministic verification · Temple University prototype
          </div>
          <h1 className="text-5xl font-semibold tracking-tight text-balance sm:text-6xl">
            Your Degree. Your Schedule. <span className="text-primary">Optimized.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-balance text-muted-foreground">
            An intelligent academic planning system that understands your requirements, interests, and availability.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link href="/onboarding" className={cn(buttonVariants({ size: "lg" }), "h-11 px-6 text-base")}>
              Build My Schedule <ArrowRight className="size-4" />
            </Link>
            <Link href="/demo" className={cn(buttonVariants({ size: "lg", variant: "outline" }), "h-11 px-6 text-base")}>
              Explore Demo
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-4 px-6 py-16 sm:grid-cols-2 lg:grid-cols-4">
        {PILLARS.map((p) => (
          <div key={p.title} className="rounded-2xl border bg-card p-5 shadow-xs">
            <div className="mb-3 grid size-9 place-items-center rounded-lg bg-cherry-soft text-primary">
              <p.icon className="size-4.5" />
            </div>
            <h3 className="font-semibold">{p.title}</h3>
            <p className="mt-1.5 text-sm text-muted-foreground">{p.body}</p>
          </div>
        ))}
      </section>

      <section className="border-y bg-muted/30">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <div className="mb-8 flex items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">A planning team, not a chatbot</h2>
              <p className="mt-1 text-muted-foreground">Agents share one planning state. The optimizer — not the language model — decides what is valid.</p>
            </div>
            <BrainCircuit className="hidden size-10 text-primary/60 sm:block" />
          </div>
          <ol className="grid gap-3 sm:grid-cols-3">
            {AGENTS.map(([name, desc], i) => (
              <li key={name} className="flex gap-3 rounded-xl border bg-card p-4">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">{i + 1}</span>
                <div>
                  <div className="text-sm font-medium">{name} Agent</div>
                  <div className="text-xs text-muted-foreground">{desc}</div>
                </div>
              </li>
            ))}
          </ol>
          <div className="mt-6 flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><GitBranch className="size-3.5" /> Review agent can send schedules back to the optimizer</span>
            <span className="flex items-center gap-1.5"><ScanSearch className="size-3.5" /> Every step logged with sources and timestamps</span>
          </div>
        </div>
      </section>
    </div>
  )
}
