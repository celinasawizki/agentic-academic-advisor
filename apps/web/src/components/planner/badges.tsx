import { AlertTriangle, BadgeCheck, Bot, CircleDashed, Database, ShieldAlert, XCircle } from "lucide-react"

import { cn } from "@/lib/utils"

type Tone = "success" | "warning" | "info" | "danger" | "neutral" | "cherry"

const TONES: Record<Tone, string> = {
  success: "bg-success-soft text-success border-success/20",
  warning: "bg-warning-soft text-warning border-warning/25",
  info: "bg-info-soft text-info border-info/20",
  danger: "bg-destructive/10 text-destructive border-destructive/20",
  neutral: "bg-muted text-muted-foreground border-border",
  cherry: "bg-cherry-soft text-primary border-primary/20",
}

export function Pill({ tone = "neutral", icon: Icon, children, className }: {
  tone?: Tone
  icon?: React.ComponentType<{ className?: string }>
  children: React.ReactNode
  className?: string
}) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap", TONES[tone], className)}>
      {Icon && <Icon className="size-3" />}
      {children}
    </span>
  )
}

export const VerifiedFact = () => <Pill tone="success" icon={BadgeCheck}>Computed by rules engine</Pill>
export const AISuggestion = () => <Pill tone="info" icon={Bot}>AI suggestion</Pill>
export const PendingVerification = () => <Pill tone="warning" icon={CircleDashed}>Pending verification</Pill>
export const SnapshotData = ({ label = "Temple class-search snapshot" }: { label?: string }) => <Pill tone="neutral" icon={Database}>{label}</Pill>

export function ReviewBadge({ status }: { status?: string }) {
  if (status === "rejected") return <Pill tone="danger" icon={XCircle}>Rejected by review</Pill>
  if (status === "checks_passed") return <Pill tone="success" icon={BadgeCheck}>Deterministic checks passed</Pill>
  if (status === "checks_passed_with_warnings") return <Pill tone="warning" icon={AlertTriangle}>Checks passed · warnings</Pill>
  return <Pill tone="neutral" icon={CircleDashed}>Pending review</Pill>
}

export function F1Badge({ status }: { status: string }) {
  if (status === "not_applicable") return null
  const map: Record<string, [Tone, string]> = {
    meets: ["success", "F-1 full-time count met"],
    needs_confirmation: ["warning", "F-1: confirm with ISSS"],
    below: ["danger", "F-1: below full-time count"],
  }
  const [tone, label] = map[status] ?? ["neutral", status]
  return <Pill tone={tone} icon={ShieldAlert}>{label}</Pill>
}

const RELIABILITY: Record<string, [Tone, string, string]> = {
  VERIFIED: ["success", "Verified", "Checked by a person against an authoritative source"],
  PENDING_VERIFICATION: ["warning", "Pending verification", "Parsed from the bulletin; not yet checked against your degree audit"],
  AMBIGUOUS: ["danger", "Ambiguous", "Free text or unusual layout; an advisor must interpret it"],
  UNAVAILABLE: ["neutral", "Unavailable this term", "No eligible Main Campus/online section in the snapshot"],
  BLOCKED: ["info", "Blocked", "Offered, but you don't have the prerequisites yet"],
}

export function ReliabilityBadge({ status, title }: { status?: string; title?: string }) {
  const [tone, label, hint] = RELIABILITY[status ?? "PENDING_VERIFICATION"] ?? RELIABILITY.PENDING_VERIFICATION
  return <span title={title ?? hint}><Pill tone={tone}>{label}</Pill></span>
}

export function ReliabilityLegend({ counts }: { counts?: Record<string, number> }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(RELIABILITY).map(([k, [tone, label, hint]]) => (
        <span key={k} title={hint}><Pill tone={tone}>{label}{counts ? ` · ${counts[k] ?? 0}` : ""}</Pill></span>
      ))}
    </div>
  )
}

const CATEGORY: Record<string, [Tone, string]> = {
  REQUIRED: ["cherry", "Required course"],
  DEGREE_ELECTIVE: ["info", "Degree elective"],
  INTEREST_ELECTIVE: ["warning", "Interest-based elective"],
  OPTIONAL_ENRICHMENT: ["neutral", "Optional enrichment"],
}

export function CategoryBadge({ category, label }: { category?: string; label?: string }) {
  if (!category) return null
  const [tone, text] = CATEGORY[category] ?? ["neutral", category]
  return <Pill tone={tone}>{label ?? text}</Pill>
}
