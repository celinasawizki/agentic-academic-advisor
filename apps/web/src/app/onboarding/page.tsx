"use client"

import {
  ArrowLeft, ArrowRight, BookOpen, Building2, CalendarClock, Check, FileUp, Gauge, Globe2, Loader2, Plus, Search, ShieldAlert,
  Sparkles, Trash2, UserRound,
} from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { AvailabilityGrid } from "@/components/planner/availability-grid"
import { Pill } from "@/components/planner/badges"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Textarea } from "@/components/ui/textarea"
import { api, type AuditEntry } from "@/lib/api"
import type { AvailBlock, Program, Term } from "@/lib/types"
import { cn } from "@/lib/utils"

type Status = AuditEntry["status"]
type Row = { course: string; status: Status; grade: string | null; term: string | null; source: "manual" | "degree_audit_pdf"; confidence: number; verified: boolean }

const STEPS = [
  { key: "profile", title: "What are you currently studying?", icon: UserRound },
  { key: "records", title: "Let's understand your academic progress.", icon: BookOpen },
  { key: "interests", title: "What topics are you most interested in exploring?", icon: Sparkles },
  { key: "availability", title: "When are you available to attend classes?", icon: CalendarClock },
  { key: "credits", title: "How many credits would you like to take?", icon: Gauge },
  { key: "campus", title: "Which Temple campus are you studying at?", icon: Building2 },
  { key: "f1", title: "Are you an international student studying under an F-1 visa?", icon: Globe2 },
] as const

const SUGGESTED = ["Clinical Psychology", "Industrial-Organizational Psychology", "Cognitive Neuroscience", "Artificial Intelligence",
  "Entrepreneurship", "Finance", "Marketing", "Computer Science", "Human-Computer Interaction", "Organizational Behavior", "Data Science", "Research Methods"]

const STATUS_LABEL: Record<Status, string> = { completed: "Completed", in_progress: "In progress", transfer: "Transfer", planned: "Planned", unverified: "Unverified" }

const DEMO = {
  name: "Jordan Rivera (fictional)", academic_year: "Junior", expected_graduation: "2028-05", catalog_year: "2026-2027",
  programs: ["psychology-ba", "entrepreneurship-innovation-management-minor", "data-science-computational-analytics-certificate", "gened"],
  interests: "I'm studying Psychology, but I'm especially interested in Industrial-Organizational Psychology, workplace behavior, artificial intelligence, and how technology affects human decision-making.",
  rows: [
    ["PSY 1001", "completed", "A"], ["PSY 1002", "completed", "A"], ["PSY 1003", "completed", "B+"], ["PSY 1004", "completed", "A"],
    ["PSY 2402", "completed", "A"], ["PSY 2101", "completed", "A-"], ["ECON 1101", "completed", "B+"], ["HRM 1101", "completed", "A"],
    ["MATH 1041", "completed", "B"], ["ENG 0802", "completed", "B+"], ["IH 0851", "completed", "A-"], ["ARTH 0808", "transfer", "TR"],
    ["PSY 2301", "in_progress", null], ["PSY 2501", "in_progress", null], ["CIS 1068", "in_progress", null], ["ECON 1102", "in_progress", null],
  ] as [string, Status, string | null][],
  availability: [
    { day: "M", start: "13:00", end: "18:00", kind: "hard", label: "Work" },
    { day: "W", start: "13:00", end: "18:00", kind: "hard", label: "Work" },
    { day: "F", start: "07:00", end: "22:00", kind: "soft", label: "Prefer Fridays off" },
  ] as AvailBlock[],
}

export default function Onboarding() {
  const router = useRouter()
  const [step, setStep] = useState(0)
  const [programs, setPrograms] = useState<Program[]>([])
  const [terms, setTerms] = useState<Term[]>([])
  const [courseList, setCourseList] = useState<{ code: string; title: string }[]>([])
  const [submitting, setSubmitting] = useState(false)

  const [name, setName] = useState("")
  const [year, setYear] = useState("Junior")
  const [grad, setGrad] = useState("2028-05")
  const [catalogYear, setCatalogYear] = useState("")
  const [term, setTerm] = useState("202703")
  const [selected, setSelected] = useState<string[]>(["gened"])
  const [programQuery, setProgramQuery] = useState("")
  const [typeFilter, setTypeFilter] = useState<"all" | Program["type"]>("all")
  const [rows, setRows] = useState<Row[]>([])
  const [consent, setConsent] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [newCourse, setNewCourse] = useState("")
  const [newStatus, setNewStatus] = useState<Status>("completed")
  const [interests, setInterests] = useState("")
  const [tags, setTags] = useState<string[]>([])
  const [availability, setAvailability] = useState<AvailBlock[]>([])
  const [credits, setCredits] = useState({ target: 15, min: 12, max: 18 })
  const [campus, setCampus] = useState("Main")
  const [f1, setF1] = useState<"yes" | "no" | "prefer_not">("prefer_not")

  useEffect(() => {
    Promise.all([api.programs(), api.terms(), api.courses()])
      .then(([p, t, c]) => { setPrograms(p); setTerms(t); setCourseList(c) })
      .catch((e) => toast.error(e.message))
  }, [])

  const prefill = () => {
    setName(DEMO.name); setYear(DEMO.academic_year); setGrad(DEMO.expected_graduation); setCatalogYear(DEMO.catalog_year)
    setSelected(DEMO.programs); setInterests(DEMO.interests); setAvailability(DEMO.availability); setCredits({ target: 15, min: 12, max: 18 })
    setRows(DEMO.rows.map(([course, status, grade]) => ({ course, status, grade, term: null, source: "manual", confidence: 1, verified: true })))
    setF1("yes"); setConsent(true)
    toast.success("Filled with fictional demo values")
  }

  const filteredPrograms = useMemo(() => {
    const q = programQuery.toLowerCase().trim()
    return programs
      .filter((p) => (typeFilter === "all" || p.type === typeFilter) && (!q || `${p.name} ${p.type} ${p.college}`.toLowerCase().includes(q)))
      .sort((a, b) => Number(selected.includes(b.id)) - Number(selected.includes(a.id)) || a.name.localeCompare(b.name))
  }, [programs, programQuery, typeFilter, selected])
  const catalogYears = useMemo(() => [...new Set(programs.map((p) => p.catalog_year).filter(Boolean) as string[])].sort().reverse(), [programs])
  const counts = useMemo(() => programs.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.type]: (acc[p.type] ?? 0) + 1 }), {}), [programs])

  const upload = async (file: File) => {
    if (!consent) return toast.error("Please give consent before uploading academic records.")
    if (file.size > 5 * 1024 * 1024) return toast.error("File is larger than 5 MB.")
    setUploading(true)
    try {
      const res = await api.parseAudit(file)
      const existing = new Set(rows.map((r) => r.course))
      const added = res.entries.filter((e) => !existing.has(e.course)).map((e) => ({
        course: e.course, status: e.status, grade: e.grade, term: e.term, source: "degree_audit_pdf" as const, confidence: e.confidence, verified: false,
      }))
      setRows([...rows, ...added])
      toast.success(`Extracted ${added.length} course(s). Review each row before continuing.`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const addCourse = () => {
    const code = newCourse.trim().toUpperCase().replace(/^([A-Z]{2,5})\s?(\d{4}).*$/, "$1 $2")
    if (!/^[A-Z]{2,5} \d{4}$/.test(code)) return toast.error("Use a course code like PSY 1001")
    if (rows.some((r) => r.course === code)) return toast.error(`${code} is already listed`)
    setRows([...rows, { course: code, status: newStatus, grade: null, term: null, source: "manual", confidence: 1, verified: true }])
    setNewCourse("")
  }

  const canNext = () => {
    if (step === 0) return name.trim() && selected.some((id) => programs.find((p) => p.id === id)?.supported && id !== "gened")
    if (step === 1) return consent && rows.every((r) => r.verified)
    if (step === 4) return credits.min <= credits.target && credits.target <= credits.max
    if (step === 5) return campus === "Main"
    return true
  }

  const submit = async () => {
    setSubmitting(true)
    try {
      const { id } = await api.createStudent({
        name, academic_year: year, expected_graduation: grad, catalog_year: catalogYear || null, planning_term: term,
        programs: selected.filter((id) => programs.find((p) => p.id === id)?.supported), campus, f1_status: f1,
        interests_text: [interests, tags.length ? `Interested in: ${tags.join(", ")}.` : ""].filter(Boolean).join(" "),
        interest_tags: tags, credit_target: credits.target, credit_min: credits.min, credit_max: credits.max,
        transcript: rows.map((r) => ({ course: r.course, status: r.status, grade: r.grade, term: r.term, source: r.source,
          confidence: r.confidence, verified_by_student: r.verified })),
        availability, consent_to_process: consent,
      })
      const { plan_id } = await api.createPlan(id)
      router.push(`/plan/${plan_id}`)
    } catch (e) {
      toast.error((e as Error).message)
      setSubmitting(false)
    }
  }

  const S = STEPS[step]
  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div className="flex-1">
          <div className="mb-2 flex justify-between text-xs text-muted-foreground">
            <span>Step {step + 1} of {STEPS.length}</span>
            <button type="button" onClick={prefill} className="font-medium text-primary hover:underline">Prefill fictional demo values</button>
          </div>
          <Progress value={((step + 1) / STEPS.length) * 100} />
        </div>
      </div>
      <div className="mb-6 flex gap-1.5 overflow-x-auto pb-1">
        {STEPS.map((s, i) => (
          <button key={s.key} type="button" onClick={() => i < step && setStep(i)}
            className={cn("flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
              i === step ? "border-primary bg-cherry-soft text-primary" : i < step ? "bg-muted text-foreground" : "text-muted-foreground")}>
            {i < step ? <Check className="size-3" /> : <s.icon className="size-3" />} {s.key[0].toUpperCase() + s.key.slice(1)}
          </button>
        ))}
      </div>

      <div className="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <S.icon className="size-5 text-primary" /> {S.title}
        </h1>

        <div className="mt-6">
          {step === 0 && (
            <div className="space-y-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Your name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="First Last" /></Field>
                <Field label="Current academic year">
                  <NativeSelect value={year} onChange={setYear} options={["Freshman", "Sophomore", "Junior", "Senior"]} />
                </Field>
                <Field label="Expected graduation"><Input type="month" value={grad} onChange={(e) => setGrad(e.target.value)} /></Field>
                <Field label="Catalog year (if known)" hint="Requirements depend on the year you entered your program.">
                  <NativeSelect value={catalogYear} onChange={setCatalogYear} options={["", ...catalogYears]} labels={{ "": "I'm not sure" }} />
                </Field>
                <Field label="Planning semester">
                  <NativeSelect value={term} onChange={setTerm} options={terms.map((t) => t.id)} labels={Object.fromEntries(terms.map((t) => [t.id, t.name]))} />
                </Field>
              </div>
              <div>
                <Label className="mb-2 block">Programs (majors, minors, certificates)</Label>
                <div className="mb-2 flex flex-col gap-2 sm:flex-row">
                  <div className="relative flex-1">
                    <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
                    <Input value={programQuery} onChange={(e) => setProgramQuery(e.target.value)} placeholder={`Search ${programs.length} Temple programs…`} className="pl-8" />
                  </div>
                  <div className="flex gap-1 rounded-lg border p-0.5 text-xs">
                    {(["all", "major", "minor", "certificate"] as const).map((t) => (
                      <button key={t} type="button" onClick={() => setTypeFilter(t)}
                        className={cn("rounded-md px-2 py-1 capitalize", typeFilter === t ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>
                        {t === "all" ? "All" : `${t}s`} <span className="opacity-70">{t === "all" ? programs.length : counts[t] ?? 0}</span>
                      </button>
                    ))}
                  </div>
                </div>
                {selected.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {selected.map((id) => {
                      const p = programs.find((x) => x.id === id)
                      return p ? (
                        <button key={id} type="button" onClick={() => setSelected(selected.filter((x) => x !== id))}
                          className="rounded-full border border-primary/30 bg-cherry-soft px-2.5 py-0.5 text-xs text-primary">
                          {p.name} ×
                        </button>
                      ) : null
                    })}
                  </div>
                )}
                <div className="grid max-h-72 gap-1.5 overflow-y-auto rounded-xl border p-2 sm:grid-cols-2">
                  {filteredPrograms.slice(0, 120).map((p) => {
                    const on = selected.includes(p.id)
                    return (
                      <button key={p.id} type="button" disabled={!p.supported}
                        onClick={() => setSelected(on ? selected.filter((x) => x !== p.id) : [...selected, p.id])}
                        className={cn("flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                          on ? "border-primary bg-cherry-soft" : "hover:bg-muted", !p.supported && "cursor-not-allowed opacity-55")}>
                        <span>
                          <span className="block font-medium">{p.name}</span>
                          <span className="block text-[11px] text-muted-foreground capitalize">{p.type === "gened" ? "General education" : p.type} · {p.college}</span>
                        </span>
                        {p.supported ? (on && <Check className="size-4 shrink-0 text-primary" />) : <Pill>Needs manual review</Pill>}
                      </button>
                    )
                  })}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {filteredPrograms.length > 120 ? `Showing 120 of ${filteredPrograms.length} — refine your search. ` : ""}
                  Every undergraduate major, minor and certificate in the Temple Academic Bulletin. Requirements are parsed automatically and are
                  pending verification; programs whose requirement tables could not be parsed are marked.
                </p>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-5">
              <label className="flex items-start gap-3 rounded-xl border bg-muted/40 p-4 text-sm">
                <Checkbox checked={consent} onCheckedChange={(v) => setConsent(!!v)} className="mt-0.5" />
                <span>
                  <span className="font-medium">I consent to this prototype processing my academic records for planning.</span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Uploaded PDFs are parsed in memory on the planning server, never stored, and never sent to an external AI provider. You can
                    delete your records at any time. For the hackathon, please use fictional data.
                  </span>
                </span>
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className={cn("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-colors hover:bg-muted/50", !consent && "pointer-events-none opacity-50")}>
                  {uploading ? <Loader2 className="size-6 animate-spin text-primary" /> : <FileUp className="size-6 text-primary" />}
                  <span className="text-sm font-medium">Upload degree audit or unofficial transcript</span>
                  <span className="text-xs text-muted-foreground">PDF, max 5 MB · parsed locally</span>
                  <input type="file" accept="application/pdf" className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
                </label>
                <div className="rounded-xl border p-4">
                  <div className="mb-2 text-sm font-medium">Add a course manually</div>
                  <div className="flex gap-2">
                    <Input list="course-codes" value={newCourse} onChange={(e) => setNewCourse(e.target.value)} placeholder="PSY 1001" onKeyDown={(e) => e.key === "Enter" && addCourse()} />
                    <datalist id="course-codes">{courseList.map((c) => <option key={c.code} value={c.code}>{c.title}</option>)}</datalist>
                    <NativeSelect value={newStatus} onChange={(v) => setNewStatus(v as Status)} options={Object.keys(STATUS_LABEL)} labels={STATUS_LABEL} />
                    <Button type="button" variant="outline" size="icon-lg" onClick={addCourse}><Plus /></Button>
                  </div>
                </div>
              </div>
              <div className="overflow-hidden rounded-xl border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                    <tr><th className="px-3 py-2">Course</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Grade</th><th className="px-3 py-2">Source</th><th className="px-3 py-2">Verified</th><th /></tr>
                  </thead>
                  <tbody>
                    {rows.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-muted-foreground">No courses yet.</td></tr>}
                    {rows.map((r, i) => (
                      <tr key={r.course} className={cn("border-t", !r.verified && "bg-warning-soft/50")}>
                        <td className="px-3 py-1.5 font-medium">
                          {r.course}
                          {!courseList.some((c) => c.code === r.course) && <span className="ml-1.5"><Pill tone="warning">not in dataset</Pill></span>}
                        </td>
                        <td className="px-3 py-1.5">
                          <NativeSelect value={r.status} onChange={(v) => setRows(rows.map((x, j) => (j === i ? { ...x, status: v as Status } : x)))}
                            options={Object.keys(STATUS_LABEL)} labels={STATUS_LABEL} small />
                        </td>
                        <td className="px-3 py-1.5 text-muted-foreground">{r.grade ?? "—"}</td>
                        <td className="px-3 py-1.5">
                          {r.source === "degree_audit_pdf" ? <Pill tone={r.confidence >= 0.8 ? "info" : "warning"}>PDF · {Math.round(r.confidence * 100)}%</Pill> : <Pill>Manual</Pill>}
                        </td>
                        <td className="px-3 py-1.5">
                          <Checkbox checked={r.verified} onCheckedChange={(v) => setRows(rows.map((x, j) => (j === i ? { ...x, verified: !!v } : x)))} />
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <button type="button" onClick={() => setRows(rows.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-destructive"><Trash2 className="size-4" /></button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                {(Object.keys(STATUS_LABEL) as Status[]).map((s) => (
                  <Pill key={s} tone={s === "completed" ? "success" : s === "in_progress" ? "info" : s === "unverified" ? "warning" : "neutral"}>
                    {STATUS_LABEL[s]}: {rows.filter((r) => r.status === s).length}
                  </Pill>
                ))}
                <span className="text-muted-foreground">In-progress courses are never treated as completed.</span>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              <Textarea value={interests} onChange={(e) => setInterests(e.target.value)} rows={6} maxLength={4000} className="text-base"
                placeholder="I'm studying Psychology, but I'm especially interested in Industrial-Organizational Psychology, workplace behavior, artificial intelligence, and how technology affects human decision-making." />
              <div>
                <div className="mb-2 text-xs text-muted-foreground">Optional suggestions — you&apos;re not limited to these.</div>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTED.map((t) => {
                    const on = tags.includes(t)
                    return (
                      <button key={t} type="button" onClick={() => setTags(on ? tags.filter((x) => x !== t) : [...tags, t])}
                        className={cn("rounded-full border px-3 py-1 text-sm transition-colors", on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>
                        {t}
                      </button>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Click and drag to paint. <b className="text-foreground">Unavailable</b> times are hard constraints the planner will never violate.
                <b className="text-foreground"> Prefer to avoid</b> is a soft preference that can only be relaxed with your approval.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => setAvailability([...availability.filter((b) => b.label !== "Prefer Fridays off"), { day: "F", start: "07:00", end: "22:00", kind: "soft", label: "Prefer Fridays off" }])}>
                  + Prefer Fridays off
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => setAvailability([...availability, ...["M", "T", "W", "R", "F"].map((d) => ({ day: d, start: "07:00", end: "10:00", kind: "soft", label: "No early classes" }) as AvailBlock)])}>
                  + Avoid classes before 10 AM
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => setAvailability([])}>Clear</Button>
              </div>
              <AvailabilityGrid value={availability} onChange={setAvailability} />
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[12, 15, 18].map((n) => (
                  <button key={n} type="button" onClick={() => setCredits({ target: n, min: Math.min(credits.min, n), max: Math.max(credits.max, n) })}
                    className={cn("rounded-xl border p-4 text-center transition-colors", credits.target === n ? "border-primary bg-cherry-soft" : "hover:bg-muted")}>
                    <div className="text-2xl font-semibold">{n}</div><div className="text-xs text-muted-foreground">credits</div>
                  </button>
                ))}
                <div className={cn("rounded-xl border p-3", ![12, 15, 18].includes(credits.target) && "border-primary bg-cherry-soft")}>
                  <Label className="text-xs">Custom target</Label>
                  <Input type="number" min={1} max={24} value={credits.target} onChange={(e) => setCredits({ ...credits, target: Number(e.target.value) })} className="mt-1" />
                </div>
              </div>
              <div className="grid max-w-md grid-cols-2 gap-4">
                <Field label="Minimum acceptable"><Input type="number" min={0} max={24} value={credits.min} onChange={(e) => setCredits({ ...credits, min: Number(e.target.value) })} /></Field>
                <Field label="Maximum acceptable"><Input type="number" min={1} max={24} value={credits.max} onChange={(e) => setCredits({ ...credits, max: Number(e.target.value) })} /></Field>
              </div>
              <p className="text-xs text-muted-foreground">
                Your target is a preference the optimizer aims for. The acceptable range is a hard limit. Enrollment minimums (e.g. full-time or
                F-1 status) are checked separately and are not changed by this setting.
              </p>
            </div>
          )}

          {step === 5 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {[["Main", "Main Campus", "Philadelphia · includes eligible online courses", true], ["Ambler", "Ambler Campus", "Coming soon", false],
                ["Rome", "Temple Rome", "Coming soon", false], ["Japan", "Temple Japan", "Coming soon", false]].map(([id, label, sub, ok]) => (
                <button key={id as string} type="button" disabled={!ok} onClick={() => setCampus(id as string)}
                  className={cn("rounded-xl border p-4 text-left transition-colors", campus === id ? "border-primary bg-cherry-soft" : "hover:bg-muted", !ok && "cursor-not-allowed opacity-55")}>
                  <div className="flex items-center justify-between font-medium">{label}{!ok && <Pill>Future</Pill>}</div>
                  <div className="text-xs text-muted-foreground">{sub}</div>
                </button>
              ))}
              <p className="text-xs text-muted-foreground sm:col-span-2">This prototype schedules Main Campus and online sections only. In-person sections from other campuses are never recommended.</p>
            </div>
          )}

          {step === 6 && (
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-3">
                {([["yes", "Yes"], ["no", "No"], ["prefer_not", "Prefer not to say"]] as const).map(([v, l]) => (
                  <button key={v} type="button" onClick={() => setF1(v)}
                    className={cn("rounded-xl border p-4 text-center font-medium transition-colors", f1 === v ? "border-primary bg-cherry-soft" : "hover:bg-muted")}>{l}</button>
                ))}
              </div>
              <div className="flex gap-3 rounded-xl border border-warning/30 bg-warning-soft p-4 text-sm">
                <ShieldAlert className="mt-0.5 size-5 shrink-0 text-warning" />
                <div className="space-y-1.5">
                  <p className="font-medium">Planning assistance, not immigration advice.</p>
                  <p className="text-muted-foreground">
                    For F-1 students we apply a configurable planning rule: no more than one online course (3 credits) counts toward the
                    required full course of study each semester. You may still take additional online courses — they just don&apos;t count toward
                    the minimum. Hybrid courses are not assumed to count as in-person. We never claim a schedule is immigration-compliant;
                    confirm with Temple&apos;s International Student and Scholar Services (ISSS).
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="mt-8 flex items-center justify-between border-t pt-5">
          <Button variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}><ArrowLeft /> Back</Button>
          {step < STEPS.length - 1 ? (
            <Button onClick={() => setStep(step + 1)} disabled={!canNext()}>Continue <ArrowRight /></Button>
          ) : (
            <Button onClick={submit} disabled={submitting || !consent} className="px-4">
              {submitting ? <Loader2 className="animate-spin" /> : <Sparkles />} Run the planning agents
            </Button>
          )}
        </div>
        {step === 1 && !canNext() && <p className="mt-2 text-right text-xs text-muted-foreground">Give consent and verify every extracted row to continue.</p>}
      </div>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

function NativeSelect({ value, onChange, options, labels, small }: {
  value: string; onChange: (v: string) => void; options: string[]; labels?: Record<string, string>; small?: boolean
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className={cn("w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50", small ? "h-7" : "h-8")}>
      {options.map((o) => <option key={o} value={o}>{labels?.[o] ?? o}</option>)}
    </select>
  )
}
