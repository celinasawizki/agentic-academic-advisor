import { BadgeCheck, Bot, BookOpen, CalendarCheck, Database, GraduationCap, Sparkles } from "lucide-react"

import { AISuggestion, PendingVerification, Pill, VerifiedFact } from "@/components/planner/badges"
import type { CourseExplanation } from "@/lib/types"

const ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  requirement: BookOpen,
  interest: Sparkles,
  graduation: GraduationCap,
  schedule_fit: CalendarCheck,
}

export function CourseExplainer({ c }: { c: CourseExplanation }) {
  return (
    <div className="rounded-2xl border bg-card p-4 text-sm">
      <div className="text-xs text-muted-foreground">{c.course} · §{c.section_id.split("-").pop()} · {c.credits} credits</div>
      <h3 className="font-semibold">{c.title}</h3>
      <div className="mt-0.5 text-xs text-muted-foreground">{c.meeting} · {c.location}</div>

      <div className="mt-3 text-xs font-semibold">Reason for recommendation</div>
      <ul className="mt-1.5 space-y-2">
        {c.reasons.map((r, i) => {
          const Icon = ICON[r.kind] ?? BadgeCheck
          return (
            <li key={i} className="flex gap-2 text-xs">
              <Icon className="mt-0.5 size-3.5 shrink-0 text-primary" />
              <div className="flex-1">
                <span>{r.text}</span>
                <div className="mt-1">
                  {r.kind === "requirement" ? <PendingVerification /> : r.kind === "interest" ? (r.ai_generated ? <AISuggestion /> : <Pill icon={Bot}>Concept match (deterministic)</Pill>) : <VerifiedFact />}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
      <dl className="mt-3 space-y-1.5 border-t pt-3 text-xs">
        <Row k="Requirement status" v={c.requirement_status} />
        {c.prerequisites && <Row k="Prerequisites" v={c.prerequisites} />}
        <Row k="Why this section" v={c.section_choice} />
        <Row k="Data source" v={<span className="inline-flex items-center gap-1"><Database className="size-3" /> {c.data.source === "demo_fixture" ? "demo fixture" : "class-search snapshot"} · CRN {c.data.crn} · retrieved {new Date(c.data.retrieved_at).toLocaleDateString()}</span>} />
      </dl>
    </div>
  )
}

const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <div className="grid grid-cols-[7rem_1fr] gap-2"><dt className="text-muted-foreground">{k}</dt><dd>{v}</dd></div>
)
