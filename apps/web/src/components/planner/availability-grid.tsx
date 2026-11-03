"use client"

import { Ban, Eraser, Heart, Hourglass } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"

import { Input } from "@/components/ui/input"
import { DAYS, DAY_END, DAY_NAME, DAY_START, blocksToCells, cellsToBlocks, fmt12, toHHMM, toMin } from "@/lib/time"
import type { AvailBlock } from "@/lib/types"
import { cn } from "@/lib/utils"

type Tool = AvailBlock["kind"] | "erase"

const TOOLS: { key: Tool; label: string; hint: string; icon: React.ComponentType<{ className?: string }>; swatch: string }[] = [
  { key: "hard", label: "Unavailable", hint: "Hard constraint: never schedule here", icon: Ban, swatch: "bg-primary" },
  { key: "soft", label: "Prefer to avoid", hint: "Soft: only relaxed with your approval", icon: Hourglass, swatch: "bg-warning" },
  { key: "preferred", label: "Preferred", hint: "Times you'd like classes", icon: Heart, swatch: "bg-success" },
  { key: "erase", label: "Erase", hint: "Clear cells", icon: Eraser, swatch: "bg-muted-foreground" },
]

const CELL_CLASS: Record<AvailBlock["kind"], string> = {
  hard: "bg-primary/80",
  soft: "bg-warning/60",
  preferred: "bg-success/50",
}

export function AvailabilityGrid({ value, onChange }: { value: AvailBlock[]; onChange: (blocks: AvailBlock[]) => void }) {
  const [tool, setTool] = useState<Tool>("hard")
  const [labels, setLabels] = useState<Partial<Record<AvailBlock["kind"], string>>>(() => {
    const l: Partial<Record<AvailBlock["kind"], string>> = { hard: "Unavailable", soft: "Prefer to avoid", preferred: "Preferred time" }
    for (const b of value) if (b.label) l[b.kind] = b.label
    return l
  })
  const cells = useMemo(() => blocksToCells(value), [value])
  const [draft, setDraft] = useState<Map<string, AvailBlock["kind"]> | null>(null)
  const dragging = useRef(false)
  const slots = useMemo(() => Array.from({ length: (DAY_END - DAY_START) / 30 }, (_, i) => DAY_START + i * 30), [])
  const shown = draft ?? cells

  const paint = (key: string) => {
    setDraft((prev) => {
      const next = new Map(prev ?? cells)
      if (tool === "erase") next.delete(key)
      else next.set(key, tool)
      return next
    })
  }

  useEffect(() => {
    const up = () => {
      if (!dragging.current) return
      dragging.current = false
      setDraft((d) => {
        if (d) {
          const merged = cellsToBlocks(d, labels).map((b) => {
            const prior = value.find((v) => v.day === b.day && v.kind === b.kind && toMin(v.start) <= toMin(b.start) && toMin(v.end) > toMin(b.start))
            return prior ? { ...b, label: prior.label } : b
          })
          queueMicrotask(() => onChange(merged))
        }
        return null
      })
    }
    window.addEventListener("pointerup", up)
    return () => window.removeEventListener("pointerup", up)
  }, [labels, onChange, value])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {TOOLS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTool(t.key)}
            className={cn(
              "flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-all",
              tool === t.key ? "border-primary bg-cherry-soft shadow-sm" : "hover:bg-muted",
            )}
          >
            <span className={cn("size-3 rounded-sm", t.swatch)} />
            <span>
              <span className="block font-medium">{t.label}</span>
              <span className="block text-[11px] text-muted-foreground">{t.hint}</span>
            </span>
          </button>
        ))}
      </div>
      {tool !== "erase" && (
        <div className="flex max-w-sm items-center gap-2">
          <span className="text-xs whitespace-nowrap text-muted-foreground">Label for new blocks</span>
          <Input
            value={labels[tool] ?? ""}
            onChange={(e) => setLabels({ ...labels, [tool]: e.target.value })}
            placeholder="e.g. Work, Internship, Practice"
            className="h-8"
          />
        </div>
      )}
      <div className="overflow-x-auto rounded-xl border bg-card select-none" onPointerLeave={() => undefined}>
        <div className="grid min-w-[560px]" style={{ gridTemplateColumns: "3.5rem repeat(7, minmax(0, 1fr))" }}>
          <div className="border-b bg-muted/40" />
          {DAYS.map((d) => (
            <div key={d} className="border-b border-l bg-muted/40 py-1.5 text-center text-xs font-semibold text-muted-foreground">
              {DAY_NAME[d]}
            </div>
          ))}
          {slots.map((t) => (
            <div key={t} className="contents">
              <div className="pr-1.5 text-right text-[10px] leading-[14px] text-muted-foreground">{t % 60 === 0 ? fmt12(toHHMM(t)).replace(":00", "") : ""}</div>
              {DAYS.map((d) => {
                const key = `${d}:${t}`
                const kind = shown.get(key)
                return (
                  <div
                    key={key}
                    role="button"
                    aria-label={`${DAY_NAME[d]} ${fmt12(toHHMM(t))} ${kind ?? "available"}`}
                    onPointerDown={(e) => {
                      e.preventDefault()
                      dragging.current = true
                      paint(key)
                    }}
                    onPointerEnter={() => dragging.current && paint(key)}
                    className={cn(
                      "h-3.5 cursor-crosshair border-l transition-colors",
                      t % 60 === 0 ? "border-t border-t-border/80" : "border-t border-t-border/30",
                      kind ? CELL_CLASS[kind] : "hover:bg-muted",
                    )}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
