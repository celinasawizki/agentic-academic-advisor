"use client"

import { AlertTriangle, BrainCircuit, CalendarRange, LayoutDashboard, Loader2, MessageSquareQuote } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { createContext, useCallback, useContext, useEffect, useState } from "react"

import { api } from "@/lib/api"
import type { Plan } from "@/lib/types"
import { cn } from "@/lib/utils"

type Ctx = { plan: Plan | null; stable: Plan | null; error: string | null; refresh: () => Promise<void>; busy: boolean }
const PlanCtx = createContext<Ctx>({ plan: null, stable: null, error: null, refresh: async () => {}, busy: true })
export const usePlan = () => useContext(PlanCtx)

export function PlanShell({ planId, children }: { planId: string; children: React.ReactNode }) {
  const [plan, setPlan] = useState<Plan | null>(null)
  const [stable, setStable] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const path = usePathname()

  useEffect(() => {
    let cancelled = false
    let t: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const p = await api.plan(planId)
        if (cancelled) return
        setPlan(p)
        if (p.status === "complete") setStable(p)
        setError(null)
        if (p.status === "pending" || p.status === "running") t = setTimeout(poll, 700)
      } catch (e) {
        if (cancelled) return
        setError((e as Error).message)
        t = setTimeout(poll, 3000)
      }
    }
    poll()
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [planId, version])

  const refresh = useCallback(async () => setVersion((v) => v + 1), [])

  const busy = !plan || plan.status === "pending" || plan.status === "running"
  const base = `/plan/${planId}`
  const tabs = [
    { href: base, label: "Agent workspace", icon: BrainCircuit },
    { href: `${base}/dashboard`, label: "Academic dashboard", icon: LayoutDashboard },
    { href: `${base}/schedules`, label: "Schedules", icon: CalendarRange },
    { href: `${base}/explain`, label: "Explanation", icon: MessageSquareQuote },
  ]
  const student = plan?.state._student

  return (
    <PlanCtx.Provider value={{ plan, stable, error, refresh, busy }}>
      <div className="border-b bg-muted/20">
        <div className="mx-auto max-w-7xl px-4 pt-5 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs text-muted-foreground">Planning {plan?.state.course_discovery?.term_name ?? plan?.term_id ?? "…"}</div>
              <h1 className="text-xl font-semibold tracking-tight">{student?.name ?? "Loading plan…"}</h1>
            </div>
            <div className="flex items-center gap-2 text-xs">
              {busy ? (
                <span className="flex items-center gap-1.5 rounded-full bg-cherry-soft px-3 py-1 font-medium text-primary">
                  <Loader2 className="size-3.5 animate-spin" /> Agents running
                </span>
              ) : plan?.status === "failed" ? (
                <span className="flex items-center gap-1.5 rounded-full bg-destructive/10 px-3 py-1 font-medium text-destructive"><AlertTriangle className="size-3.5" /> Failed</span>
              ) : (
                <span className="rounded-full bg-success-soft px-3 py-1 font-medium text-success">Plan complete · iteration {plan?.iteration}</span>
              )}
            </div>
          </div>
          <nav className="mt-4 flex gap-1 overflow-x-auto">
            {tabs.map((t) => {
              const active = t.href === base ? path === base : path.startsWith(t.href)
              return (
                <Link key={t.href} href={t.href}
                  className={cn("flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm whitespace-nowrap transition-colors",
                    active ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
                  <t.icon className="size-4" /> {t.label}
                </Link>
              )
            })}
          </nav>
        </div>
      </div>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {error && !plan && <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">{error}</div>}
        {plan?.status === "failed" && (
          <div className="mb-4 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            Planning failed. See the agent workspace for the failing step.
          </div>
        )}
        {children}
      </div>
    </PlanCtx.Provider>
  )
}

export function WaitFor({ ready, label, children }: { ready: boolean; label: string; children: React.ReactNode }) {
  if (ready) return <>{children}</>
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed py-24 text-sm text-muted-foreground">
      <Loader2 className="size-6 animate-spin text-primary" /> {label}
    </div>
  )
}
