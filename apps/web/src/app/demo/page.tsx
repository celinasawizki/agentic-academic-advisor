"use client"

import { ArrowRight, Briefcase, Database, Globe2, Loader2, Sparkles } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"

const OTHERS = [
  { id: "demo-priya", name: "Priya Shah", year: "Sophomore", programs: "Computer Science BS · Mathematics minor · Entrepreneurship & Innovation Management certificate",
    detail: "Machine learning, cybersecurity and startups · no early classes · Thursday evening club" },
  { id: "demo-marcus", name: "Marcus Bell", year: "Sophomore", programs: "Psychology BA", detail: "Clinical psychology & neuroscience · Tuesday morning internship" },
]

export default function DemoPage() {
  const router = useRouter()
  const [loading, setLoading] = useState<string | null>(null)

  const start = async (id: string) => {
    setLoading(id)
    try {
      const { plan_id } = await api.createPlan(id)
      router.push(`/plan/${plan_id}`)
    } catch (e) {
      toast.error((e as Error).message)
      setLoading(null)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-14">
      <h1 className="text-3xl font-semibold tracking-tight">Explore the demo</h1>
      <p className="mt-2 text-muted-foreground">
        Fictional students planned against real Temple data: every undergraduate major, minor and certificate from the Academic Bulletin, and a
        snapshot of Spring 2027 sections from Temple&apos;s public class search. Running a plan executes the real agents and optimizer.
      </p>

      <div className="mt-8 rounded-2xl border bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium tracking-wide text-primary uppercase">Featured scenario</div>
            <h2 className="mt-1 text-xl font-semibold">Lina Haddad <span className="text-sm font-normal text-muted-foreground">(fictional) · Junior</span></h2>
            <p className="mt-1 text-sm text-muted-foreground">Psychology BA · Entrepreneurship & Innovation Management minor · Data Science: Computational Analytics certificate</p>
          </div>
          <Button size="lg" className="h-10" disabled={!!loading} onClick={() => start("demo-lina")}>
            {loading === "demo-lina" ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
            Run the agents
          </Button>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <Fact icon={Sparkles} title="Interests" body="Industrial-Organizational Psychology, AI, technology & decision-making" />
          <Fact icon={Briefcase} title="Availability" body="Works Mon & Wed 1–6 PM (hard). Prefers Fridays off (soft). 15 credits." />
          <Fact icon={Globe2} title="Enrollment" body="Main Campus · F-1 international student · graduating May 2028" />
        </div>
        <p className="mt-5 flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
          <Database className="mt-0.5 size-3.5 shrink-0" />
          Try the schedule chat afterwards: &ldquo;I got a job on Tuesdays and Thursdays from 9 to 5&rdquo;. Every open section of Research
          Methods (PSY 3096) then collides with one of her jobs, and the solver names the conflicting constraints and offers verified fixes.
        </p>
      </div>

      <div className="mt-4 space-y-3">
        {OTHERS.map((s) => (
          <div key={s.id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-card p-5">
            <div>
              <h3 className="font-medium">{s.name} <span className="text-sm font-normal text-muted-foreground">(fictional) · {s.year}</span></h3>
              <p className="text-sm text-muted-foreground">{s.programs}</p>
              <p className="text-xs text-muted-foreground">{s.detail}</p>
            </div>
            <Button variant="outline" disabled={!!loading} onClick={() => start(s.id)}>
              {loading === s.id && <Loader2 className="size-4 animate-spin" />} Run
            </Button>
          </div>
        ))}
      </div>
      <p className="mt-6 text-sm text-muted-foreground">Or plan any of Temple&apos;s 435 programs yourself in <a href="/onboarding" className="text-primary hover:underline">Build my schedule</a>.</p>
    </div>
  )
}

function Fact({ icon: Icon, title, body }: { icon: React.ComponentType<{ className?: string }>; title: string; body: string }) {
  return (
    <div className="rounded-xl bg-muted/50 p-3">
      <div className="flex items-center gap-1.5 text-xs font-medium"><Icon className="size-3.5 text-primary" /> {title}</div>
      <p className="mt-1 text-xs text-muted-foreground">{body}</p>
    </div>
  )
}
