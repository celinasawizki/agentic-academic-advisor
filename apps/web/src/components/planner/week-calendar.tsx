"use client"

import { Lock, MonitorPlay } from "lucide-react"

import { DAY_END, DAY_NAME, DAY_START, WEEKDAYS, fmt12, toMin } from "@/lib/time"
import type { AvailBlock, Day, OptionSection } from "@/lib/types"
import { cn } from "@/lib/utils"

const PALETTE = [
  "bg-[oklch(0.95_0.04_15)] border-[oklch(0.55_0.16_15)] text-[oklch(0.35_0.12_15)]",
  "bg-[oklch(0.95_0.04_250)] border-[oklch(0.55_0.13_250)] text-[oklch(0.35_0.1_250)]",
  "bg-[oklch(0.95_0.05_155)] border-[oklch(0.55_0.12_155)] text-[oklch(0.33_0.09_155)]",
  "bg-[oklch(0.96_0.06_85)] border-[oklch(0.62_0.13_70)] text-[oklch(0.38_0.09_60)]",
  "bg-[oklch(0.95_0.04_300)] border-[oklch(0.55_0.13_300)] text-[oklch(0.35_0.1_300)]",
  "bg-[oklch(0.95_0.03_200)] border-[oklch(0.55_0.1_200)] text-[oklch(0.33_0.08_200)]",
]

const HOUR_PX = 44
const START = DAY_START + 60
const END = DAY_END

export function colorFor(course: string, courses: string[]) {
  return PALETTE[Math.max(0, courses.indexOf(course)) % PALETTE.length]
}

export function WeekCalendar({
  sections,
  blocks = [],
  locked = [],
  selected,
  onSelect,
  compact = false,
}: {
  sections: OptionSection[]
  blocks?: AvailBlock[]
  locked?: string[]
  selected?: string | null
  onSelect?: (sectionId: string) => void
  compact?: boolean
}) {
  const hourPx = compact ? 30 : HOUR_PX
  const hours = Array.from({ length: (END - START) / 60 }, (_, i) => START / 60 + i)
  const courses = sections.map((s) => s.course)
  const online = sections.filter((s) => s.meetings.length === 0)
  const y = (m: number) => ((m - START) / 60) * hourPx

  return (
    <div className="w-full">
      <div className="grid overflow-hidden rounded-xl border bg-card" style={{ gridTemplateColumns: `3.25rem repeat(5, minmax(0, 1fr))` }}>
        <div className="border-b bg-muted/40" />
        {WEEKDAYS.map((d) => (
          <div key={d} className="border-b border-l bg-muted/40 py-2 text-center text-xs font-semibold text-muted-foreground">
            {DAY_NAME[d]}
          </div>
        ))}
        <div className="relative" style={{ height: hours.length * hourPx }}>
          {hours.map((h) => (
            <div key={h} className="absolute right-1.5 -translate-y-1/2 text-[10px] text-muted-foreground" style={{ top: y(h * 60) }}>
              {h > START / 60 ? fmt12(`${h}:00`).replace(":00", "") : ""}
            </div>
          ))}
        </div>
        {WEEKDAYS.map((day) => (
          <div key={day} className="relative border-l" style={{ height: hours.length * hourPx }}>
            {hours.map((h) => (
              <div key={h} className="absolute inset-x-0 border-t border-dashed border-border/70" style={{ top: y(h * 60) }} />
            ))}
            {blocks.filter((b) => b.day === day).map((b, i) => {
              const top = y(Math.max(START, toMin(b.start)))
              const h = y(Math.min(END, toMin(b.end))) - top
              if (h <= 0) return null
              return (
                <div
                  key={i}
                  title={`${b.kind === "hard" ? "Unavailable (hard)" : b.kind === "soft" ? "Prefer to avoid (soft)" : "Preferred"}: ${b.label}`}
                  className={cn(
                    "absolute inset-x-0 flex items-start justify-end p-1 text-[9px] font-medium",
                    b.kind === "hard" && "bg-[repeating-linear-gradient(135deg,oklch(0.9_0.03_15/.55)_0_6px,transparent_6px_12px)] text-primary/70",
                    b.kind === "soft" && "bg-warning-soft/70 text-warning",
                    b.kind === "preferred" && "bg-success-soft/60 text-success",
                  )}
                  style={{ top, height: h }}
                >
                  {!compact && <span className="truncate">{b.label}</span>}
                </div>
              )
            })}
            {sections.flatMap((s) =>
              s.meetings.filter((m) => m.days.includes(day)).map((m, i) => {
                const top = y(toMin(m.start))
                const h = y(toMin(m.end)) - top
                const isLocked = locked.includes(s.id)
                return (
                  <button
                    type="button"
                    key={`${s.id}-${i}`}
                    onClick={() => onSelect?.(s.id)}
                    className={cn(
                      "absolute inset-x-1 overflow-hidden rounded-md border-l-[3px] px-1.5 py-1 text-left shadow-sm transition-all hover:z-10 hover:shadow-md",
                      colorFor(s.course, courses),
                      selected === s.id && "ring-2 ring-primary ring-offset-1",
                      !onSelect && "cursor-default",
                    )}
                    style={{ top, height: h }}
                  >
                    <div className="flex items-center gap-1 text-[11px] leading-tight font-semibold">
                      {s.course}
                      {isLocked && <Lock className="size-2.5" />}
                    </div>
                    {!compact && h > 38 && <div className="truncate text-[10px] leading-tight opacity-80">{s.title}</div>}
                    {!compact && h > 56 && (
                      <div className="truncate text-[10px] leading-tight opacity-70">
                        {fmt12(m.start)} · {s.location}
                      </div>
                    )}
                  </button>
                )
              }),
            )}
          </div>
        ))}
      </div>
      {online.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {online.map((s) => (
            <button
              type="button"
              key={s.id}
              onClick={() => onSelect?.(s.id)}
              className={cn("flex items-center gap-1.5 rounded-md border-l-[3px] px-2 py-1 text-[11px] font-medium", colorFor(s.course, courses),
                selected === s.id && "ring-2 ring-primary ring-offset-1")}
            >
              <MonitorPlay className="size-3" /> {s.course} · Online asynchronous
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function dayHas(sections: OptionSection[], day: Day) {
  return sections.some((s) => s.meetings.some((m) => m.days.includes(day)))
}
