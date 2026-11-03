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
export const DemoData = () => <Pill tone="neutral" icon={Database}>Demo data</Pill>

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
