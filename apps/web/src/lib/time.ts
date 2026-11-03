import type { AvailBlock, Day } from "./types"

export const DAYS: Day[] = ["M", "T", "W", "R", "F", "S", "U"]
export const WEEKDAYS: Day[] = ["M", "T", "W", "R", "F"]
export const DAY_NAME: Record<Day, string> = { M: "Mon", T: "Tue", W: "Wed", R: "Thu", F: "Fri", S: "Sat", U: "Sun" }
export const DAY_START = 7 * 60
export const DAY_END = 22 * 60

export const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}

export const toHHMM = (min: number) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`

export const fmt12 = (hhmm: string) => {
  const m = toMin(hhmm)
  const h = Math.floor(m / 60)
  const suffix = h >= 12 ? "PM" : "AM"
  const h12 = h % 12 === 0 ? 12 : h % 12
  return `${h12}:${String(m % 60).padStart(2, "0")} ${suffix}`
}

export const meetingLabel = (days: string, start: string, end: string) =>
  `${days.split("").map((d) => DAY_NAME[d as Day]).join("/")} ${fmt12(start)}–${fmt12(end)}`

/** Cells are 30-minute slots keyed "D:minute". Merge contiguous same-kind cells into blocks. */
export function cellsToBlocks(cells: Map<string, AvailBlock["kind"]>, labels: Partial<Record<AvailBlock["kind"], string>>): AvailBlock[] {
  const out: AvailBlock[] = []
  for (const day of DAYS) {
    let cur: { kind: AvailBlock["kind"]; start: number } | null = null
    for (let t = DAY_START; t <= DAY_END; t += 30) {
      const kind = t < DAY_END ? cells.get(`${day}:${t}`) : undefined
      if (cur && kind !== cur.kind) {
        out.push({ day, start: toHHMM(cur.start), end: toHHMM(t), kind: cur.kind, label: labels[cur.kind] ?? "" })
        cur = null
      }
      if (kind && !cur) cur = { kind, start: t }
    }
  }
  return out
}

export function blocksToCells(blocks: AvailBlock[]): Map<string, AvailBlock["kind"]> {
  const cells = new Map<string, AvailBlock["kind"]>()
  for (const b of blocks) {
    for (let t = Math.max(DAY_START, toMin(b.start) - (toMin(b.start) % 30)); t < Math.min(DAY_END, toMin(b.end)); t += 30) {
      cells.set(`${b.day}:${t}`, b.kind)
    }
  }
  return cells
}
