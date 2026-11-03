import type { Plan, Program, Term } from "./types"

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
    })
  } catch {
    throw new ApiError(0, `Cannot reach the planning API at ${API_URL}. Is the backend running?`)
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)
    } catch {}
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ ok: boolean; llm_enabled: boolean }>("/api/health"),
  programs: () => request<Program[]>("/api/catalog/programs"),
  terms: () => request<Term[]>("/api/catalog/terms"),
  courses: () => request<{ code: string; title: string; credits: number }[]>("/api/catalog/courses"),
  demoStudents: () => request<{ id: string; name: string; academic_year: string }[]>("/api/students/demo"),
  createStudent: (body: unknown) => request<{ id: string }>("/api/students", { method: "POST", body: JSON.stringify(body) }),
  parseAudit: (file: File) => {
    const fd = new FormData()
    fd.append("file", file)
    return request<{ entries: AuditEntry[]; notes: string[] }>("/api/degree-audit/parse", { method: "POST", body: fd })
  },
  createPlan: (student_id: string) =>
    request<{ plan_id: string }>("/api/plans", { method: "POST", body: JSON.stringify({ student_id }) }),
  plan: (id: string) => request<Plan>(`/api/plans/${id}`),
  modify: (id: string, message: string) =>
    request<{ applied: string[]; assumptions: string[]; unclear: string[]; mode: string; rerun: boolean }>(
      `/api/plans/${id}/modify`,
      { method: "POST", body: JSON.stringify({ message }) },
    ),
  preferences: (id: string, body: unknown) =>
    request<{ applied: string[] }>(`/api/plans/${id}/preferences`, { method: "POST", body: JSON.stringify(body) }),
  validate: (id: string, section_ids: string[]) =>
    request<ValidateResult>(`/api/plans/${id}/validate`, { method: "POST", body: JSON.stringify({ section_ids }) }),
  saveDraft: (plan_id: string, option_id: string) =>
    request<{ draft: { draft_id: string; crns: string[]; environment: string }; validation: { messages: string[] }; notice: string }>(
      "/api/integration/tuportal/drafts",
      { method: "POST", body: JSON.stringify({ plan_id, option_id }) },
    ),
  integrationStatus: () => request<Record<string, { note: string; live?: boolean; mock?: boolean; enabled?: boolean; model?: string | null }>>("/api/integration/status"),
  advisorOverview: () => request<AdvisorStudent[]>("/api/advisor/overview", { headers: { "X-Demo-Role": "advisor" } }),
  advisorReview: (body: { plan_id: string; status: string; note: string }) =>
    request<{ ok: boolean }>("/api/advisor/reviews", { method: "POST", body: JSON.stringify(body), headers: { "X-Demo-Role": "advisor" } }),
}

export type AuditEntry = {
  course: string
  status: "completed" | "in_progress" | "transfer" | "planned" | "unverified"
  grade: string | null
  term: string | null
  confidence: number
  raw_line?: string
  in_catalog?: boolean
}

export type Check = { check: string; passed: boolean; severity: "info" | "warning" | "error"; detail: string }

export type ValidateResult = {
  valid: boolean
  checks: Check[]
  soft_violations: { preference: string; detail: string }[]
  credits: number
}

export type AdvisorStudent = {
  student_id: string
  name: string
  academic_year: string
  programs: string[]
  expected_graduation: string
  f1: boolean
  plan_id: string | null
  remaining_requirements?: { id: string; name: string; program: string; needed: number }[]
  conflicts?: string[]
  risks?: { severity: string; issue: string }[]
  critical_courses?: string[]
  options?: { id: string; label: string; credits: number; courses: string[]; review_status: string }[]
  explanation?: string
  ai_summary?: string | null
  needs_review?: boolean
  advisor_review?: { status: string; note: string; by: string } | null
}
