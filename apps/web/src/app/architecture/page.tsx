"use client"

import { Database, ExternalLink, Plug, ShieldCheck } from "lucide-react"
import { useEffect, useState } from "react"

import { Pill } from "@/components/planner/badges"
import { api } from "@/lib/api"

const FLOW = [
  ["Student input", "Onboarding, PDF audit (parsed locally), natural-language interests, availability"],
  ["Shared planning state", "PlanRun.state in the database; every agent reads and writes typed JSON"],
  ["Agents 1–6", "Profile → Requirements → Discovery → Interests → Graduation → Constraints"],
  ["CP-SAT optimizer", "Hard constraints behind enforcement literals; soft preferences in the objective"],
  ["Review agent", "Re-verifies independently; rejection sends the optimizer back for revision"],
  ["Explanation agent", "Plain-language output; verified facts vs. AI suggestions labeled"],
  ["Mock TUportal adapter", "Draft schedule export; never registers anyone"],
]

export default function Architecture() {
  const [status, setStatus] = useState<Awaited<ReturnType<typeof api.integrationStatus>> | null>(null)
  useEffect(() => { api.integrationStatus().then(setStatus).catch(() => {}) }, [])

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">How it works</h1>
      <p className="mt-2 text-muted-foreground">Language models interpret and explain. Deterministic code decides what is valid.</p>

      <ol className="mt-8 space-y-2">
        {FLOW.map(([t, d], i) => (
          <li key={t} className="flex gap-4 rounded-xl border bg-card p-4">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">{i + 1}</span>
            <div><div className="font-medium">{t}</div><div className="text-sm text-muted-foreground">{d}</div></div>
          </li>
        ))}
      </ol>

      <h2 className="mt-12 mb-3 flex items-center gap-2 text-xl font-semibold"><Plug className="size-5 text-primary" /> Integration status</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {status ? Object.entries(status).map(([k, v]) => (
          <div key={k} className="rounded-xl border bg-card p-4 text-sm">
            <div className="flex items-center justify-between font-medium capitalize">
              {k.replace("_", " ")}
              {k === "llm" ? <Pill tone={v.enabled ? "info" : "neutral"}>{v.enabled ? `Enabled · ${v.model}` : "Off · deterministic fallbacks"}</Pill>
                : <Pill tone={v.live ? "success" : "warning"}>{v.mock ? "Mock" : v.live ? "Live" : "Demo fixture"}</Pill>}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{v.note ?? (k === "llm" ? "Student education records are not sent to the LLM; only catalog data, interest text and de-identified schedule facts." : "")}</p>
          </div>
        )) : <p className="text-sm text-muted-foreground">Connect the API to see live integration status.</p>}
      </div>

      <h2 className="mt-12 mb-3 flex items-center gap-2 text-xl font-semibold"><Database className="size-5 text-primary" /> Temple data sources</h2>
      <ul className="space-y-2 text-sm">
        <li className="rounded-xl border bg-card p-4">
          <a className="inline-flex items-center gap-1 font-medium text-primary hover:underline" href="https://sites.temple.edu/degreeaudit/" target="_blank" rel="noreferrer">Degree Audit <ExternalLink className="size-3" /></a>
          <p className="text-muted-foreground">Behind university authentication with no public API. MVP: student-uploaded PDF parsed locally, then verified row-by-row by the student.</p>
        </li>
        <li className="rounded-xl border bg-card p-4">
          <a className="inline-flex items-center gap-1 font-medium text-primary hover:underline" href="https://bulletin.temple.edu/" target="_blank" rel="noreferrer">Academic Bulletin <ExternalLink className="size-3" /></a>
          <p className="text-muted-foreground">Requirements are stored with source URL, retrieval timestamp and catalog year. MVP programs are demo fixtures marked pending verification.</p>
        </li>
        <li className="rounded-xl border bg-card p-4">
          <a className="inline-flex items-center gap-1 font-medium text-primary hover:underline" href="https://prd-xereg.temple.edu/StudentRegistrationSsb/ssb/courseSearch/courseSearch" target="_blank" rel="noreferrer">Course Search <ExternalLink className="size-3" /></a>
          <p className="text-muted-foreground">Session-based Banner application without a documented open API. A CourseSearchAdapter interface isolates it; the MVP serves labeled demo sections.</p>
        </li>
      </ul>

      <h2 className="mt-12 mb-3 flex items-center gap-2 text-xl font-semibold"><ShieldCheck className="size-5 text-primary" /> Privacy & safety</h2>
      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        <li>Consent required before processing records; uploads validated (PDF signature, 5 MB) and never stored.</li>
        <li>API keys stay server-side; transcripts are not logged; students can delete their records.</li>
        <li>Untrusted text (uploads, course descriptions, chat) is wrapped and treated as data to resist prompt injection; LLM outputs are schema-validated and filtered against the dataset.</li>
        <li>Not FERPA-certified. Real student records should not be sent to external AI providers without institutional agreements.</li>
      </ul>
    </div>
  )
}
