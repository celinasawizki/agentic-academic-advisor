import { AlertCircle, BadgeCheck, BookOpen, CalendarCheck, Database, GitCompare, GraduationCap, Sparkles } from "lucide-react"

import { AISuggestion, CategoryBadge, Pill, ReliabilityBadge, VerifiedFact } from "@/components/planner/badges"
import type { CourseExplanation } from "@/lib/types"

const ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  requirement: BookOpen,
  interest: Sparkles,
  graduation: GraduationCap,
  schedule_fit: CalendarCheck,
}

export function CourseExplainer({ c }: { c: CourseExplanation }) {
  const d = c.data
  return (
    <div className="rounded-2xl border bg-card p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">{c.course} · §{d?.section ?? c.section_id.split("-").pop()} · {c.credits} credits</div>
        <CategoryBadge category={c.category} label={c.category_label} />
      </div>
      <h3 className="font-semibold">{c.title}</h3>
      <div className="mt-0.5 text-xs text-muted-foreground">{c.meeting} · {c.location}</div>

      <div className="mt-3 text-xs font-semibold">Why this course?</div>
      <ul className="mt-1.5 space-y-2">
        {c.reasons.map((r, i) => {
          const Icon = ICON[r.kind] ?? BadgeCheck
          return (
            <li key={i} className="flex gap-2 text-xs">
              <Icon className="mt-0.5 size-3.5 shrink-0 text-primary" />
              <div className="flex-1">
                <span>{r.text}</span>
                <div className="mt-1">
                  {r.kind === "requirement" && r.status !== "not_a_requirement" ? <ReliabilityBadge status={r.status} />
                    : r.kind === "interest" ? (r.ai_generated ? <AISuggestion /> : <Pill>Concept match (deterministic)</Pill>)
                    : <VerifiedFact />}
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      <dl className="mt-3 space-y-1.5 border-t pt-3 text-xs">
        <Row k="Prerequisites" v={<>{c.prerequisites}{c.prerequisite_text && <div className="mt-0.5 text-muted-foreground">Bulletin: {c.prerequisite_text}</div>}</>} />
        <Row k="Why this section" v={c.section_choice} />
      </dl>

      {c.alternatives_considered && c.alternatives_considered.length > 0 && (
        <div className="mt-3 border-t pt-3 text-xs">
          <div className="mb-1 flex items-center gap-1.5 font-semibold"><GitCompare className="size-3.5" /> Alternatives considered</div>
          <ul className="space-y-1">
            {c.alternatives_considered.map((a) => (
              <li key={a.course}><span className="font-medium">{a.course}</span> {a.title} — <span className="text-muted-foreground">not chosen: {a.why_not}</span></li>
            ))}
          </ul>
        </div>
      )}

      {c.unverified && c.unverified.length > 0 && (
        <div className="mt-3 rounded-lg bg-warning-soft/60 p-2.5 text-xs">
          <div className="mb-1 flex items-center gap-1.5 font-semibold text-warning"><AlertCircle className="size-3.5" /> Still unverified</div>
          <ul className="list-disc space-y-0.5 pl-4">{c.unverified.map((u) => <li key={u}>{u}</li>)}</ul>
        </div>
      )}

      {d && (
        <div className="mt-3 border-t pt-3 text-xs">
          <div className="mb-1 flex items-center gap-1.5 font-semibold"><Database className="size-3.5" /> Data provenance</div>
          <dl className="grid grid-cols-[6.5rem_1fr] gap-x-2 gap-y-0.5">
            <dt className="text-muted-foreground">Term</dt><dd>{d.term} ({d.term_id})</dd>
            <dt className="text-muted-foreground">Course · CRN</dt><dd>{d.course} §{d.section} · CRN {d.crn}</dd>
            <dt className="text-muted-foreground">Campus</dt><dd>{d.campus} · {d.modality.replace("_", "-")}</dd>
            <dt className="text-muted-foreground">Meetings</dt><dd>{d.meetings}</dd>
            <dt className="text-muted-foreground">Instructor</dt><dd>{d.instructor}</dd>
            <dt className="text-muted-foreground">Source</dt><dd>{d.source === "demo_fixture" ? "Synthetic test fixture" : "Temple public class search (snapshot)"}</dd>
            <dt className="text-muted-foreground">Retrieved</dt><dd>{d.retrieved_at ? new Date(d.retrieved_at).toLocaleString() : "—"}</dd>
            <dt className="text-muted-foreground">Seats</dt><dd>{d.seats}</dd>
          </dl>
          <p className="mt-1.5 text-muted-foreground">{d.availability_status}</p>
        </div>
      )}
    </div>
  )
}

const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
  <div className="grid grid-cols-[7rem_1fr] gap-2"><dt className="text-muted-foreground">{k}</dt><dd>{v}</dd></div>
)
