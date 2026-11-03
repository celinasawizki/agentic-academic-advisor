"use client"

import { ArrowRight, Briefcase, Globe2, Loader2, Sparkles } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"

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
        Fictional students and clearly labeled demo course data. Running a plan executes the real agents and optimizer.
      </p>

      <div className="mt-8 rounded-2xl border bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium tracking-wide text-primary uppercase">Featured scenario</div>
            <h2 className="mt-1 text-xl font-semibold">Lina Haddad <span className="text-sm font-normal text-muted-foreground">(fictional) · Junior</span></h2>
            <p className="mt-1 text-sm text-muted-foreground">Psychology major · Entrepreneurship minor · Computer Science certificate</p>
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
        <p className="mt-5 rounded-lg bg-warning-soft px-3 py-2 text-xs text-warning">
          Built-in tension: the only section of required Research Methods that fits around work meets Friday morning. Watch how the agents
          handle it.
        </p>
      </div>

      <div className="mt-4 flex items-center justify-between rounded-2xl border bg-card p-5">
        <div>
          <h3 className="font-medium">Marcus Bell <span className="text-sm font-normal text-muted-foreground">(fictional) · Sophomore</span></h3>
          <p className="text-sm text-muted-foreground">Psychology major · clinical & neuroscience interests · Tuesday morning internship</p>
        </div>
        <Button variant="outline" disabled={!!loading} onClick={() => start("demo-marcus")}>
          {loading === "demo-marcus" && <Loader2 className="size-4 animate-spin" />} Run
        </Button>
      </div>
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
