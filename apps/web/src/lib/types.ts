export type Day = "M" | "T" | "W" | "R" | "F" | "S" | "U"

export type Program = {
  id: string
  name: string
  type: "major" | "minor" | "certificate" | "gened"
  college: string
  catalog_year: string | null
  supported: boolean
  total_credit_hours: string | null
  source_url: string | null
  retrieved_at: string | null
}

export type Term = { id: string; name: string; start: string; end: string }

export type Meeting = { days: string; start: string; end: string }

export type AvailBlock = { day: Day; start: string; end: string; kind: "hard" | "soft" | "preferred"; label: string }

export type Section = {
  id: string
  course: string
  term_id: string
  section: string
  crn: string
  instructor: string
  campus: string
  modality: "in_person" | "online" | "hybrid" | "unknown"
  location: string
  meetings: Meeting[]
  seats_available: number | null
  credits?: number | null
  schedule_type?: string | null
  component?: string
  linked?: boolean
  attributes?: string[]
  data_source: string
  retrieved_at: string
}

export type OptionSection = Section & {
  title: string
  credits: number
  requires_linked_section?: boolean
  time_tba?: boolean
  category?: CourseCategory
  component_pairing?: "single" | "inferred"
  requirement_ids: string[]
  prereq_status: "satisfied" | "conditional" | "missing"
  prereq_pending: string[]
  interest_score: number
  priority: number
}

export type SoftViolation = { preference: string; section: string; course: string; detail: string }

export type F1 = {
  applies: boolean
  status: "meets" | "below" | "needs_confirmation" | "not_applicable"
  credits_toward_full_time: number
  full_time_required: number
  in_person_credits: number
  online_credits: number
  online_credits_counted: number
  hybrid_credits: number
  notes: string[]
}

export type ScheduleOption = {
  id: string
  strategy: "graduation" | "interest" | "balance"
  label: string
  rank: number
  credits: number
  weights?: { w_req: number; w_int: number; w_soft: number; w_dev: number; free_electives: number; enforce_critical: boolean }
  sections: OptionSection[]
  scores: {
    degree_progress: number
    interest_alignment: number
    preference_satisfaction: number
    soft_penalty: number
    status: string
  }
  soft_violations: SoftViolation[]
  critical_included: string[]
  critical_missing: string[]
  f1: F1
}

export type ConflictGroup = { key: string; kind: string; description: string }

export type Resolution = {
  relaxes: string
  feasible: boolean
  credits: number
  courses: string[]
  sections: string[]
  type: string
  constraint_class: string
  title: string
  detail: string
  requires: string
  alternatives?: string[]
  alternative_note?: string
}

export type RequirementPattern = { subject?: string; min?: number; max?: number; attribute?: string; metric?: string }

export type RequirementProgress = {
  id: string
  program_id: string
  program_name: string
  program_type: string
  group: string
  name: string
  kind: "count" | "credits" | "milestone" | "policy" | "manual" | "note"
  needed: number
  options: string[][]
  patterns: RequirementPattern[]
  requirement_notes: string[]
  catalog_year: string | null
  verification_status: string
  source_url: string | null
  completed: string[]
  in_progress: string[]
  remaining_needed: number
  remaining_courses: number
  candidate_courses: string[]
  status: "complete" | "in_progress" | "incomplete" | "unverified" | "manual" | "policy" | "note"
  notes: string[]
  value?: number | null
  min_grade?: string | null
  evidence?: string | null
  reliability?: Reliability
  reliability_reason?: string
}

export type FetchInfo = { mode: "live" | "cache" | "snapshot" | "unavailable"; retrieved_at: string | null; status?: number | null; error?: string | null; sha?: string | null }

export type RequirementsResearch = {
  programs: {
    program_id: string; name: string; type: string; query: string | null; search_provider: string | null
    search_results: { title: string; url: string; score: number | null }[]; search_matched_catalog_page: boolean; url: string | null
    fetch: FetchInfo | null; changes: { added: number; removed: number; rules_on_page: number; catalog_year_on_page: string | null } | null
  }[]
  school_layers: { id: string; name: string; type: string; url: string; rules: number; evidence_checked: number; evidence_missing: string[]; fetch_mode: string | null; retrieved_at: string | null }[]
  effective_programs: string[]
  fetches: { url: string; mode: string; retrieved_at: string | null; error: string | null }[]
  live_enabled: boolean
}

export type Reliability = "VERIFIED" | "PENDING_VERIFICATION" | "AMBIGUOUS" | "UNAVAILABLE" | "BLOCKED"
export type CourseCategory = "REQUIRED" | "DEGREE_ELECTIVE" | "INTEREST_ELECTIVE" | "OPTIONAL_ENRICHMENT"

export type Decision = {
  task: string
  data_sources: string[]
  findings: string[]
  recommendation: string
  validation: { status: "passed" | "warnings" | "failed" | "n/a"; detail: string }
  unresolved: string[]
}

export type Provenance = {
  term: string
  term_id: string
  course: string
  crn: string
  section: string
  campus: string
  modality: string
  meetings: string
  instructor: string
  source: string
  retrieved_at: string
  seats: string
  availability_status: string
}

export type CourseExplanation = {
  section_id: string
  course: string
  title: string
  credits: number
  meeting: string
  modality: string
  campus: string
  location: string
  reasons: { kind: string; verified: boolean; text: string; status?: string; source?: string | null; score?: number; ai_generated?: boolean }[]
  prerequisites: string
  prerequisite_text?: string
  requirement_status: string
  section_choice: string
  category?: CourseCategory
  category_label?: string
  alternatives_considered?: { course: string; title: string; why_not: string; verified?: boolean; method?: string; score?: number; score_of_chosen?: number; displaced?: string[] }[]
  priority?: number | null
  priority_basis?: { factor: string; value: number }[]
  unverified?: string[]
  data: Provenance
}

export type AgentExecution = {
  id: number
  agent: string
  title: string
  responsibility: string
  iteration: number
  status: "pending" | "running" | "complete" | "failed" | "skipped"
  mode: "llm" | "deterministic" | "llm_fallback"
  summary: string
  log: { t: string; message: string; data: Record<string, unknown> }[]
  sources: { kind: string; description: string; url: string | null; retrieved_at: string | null; verification_status: string }[]
  error: string | null
  decision?: Partial<Decision>
  started_at: string | null
  finished_at: string | null
}

export type StudentSnapshot = {
  id: string
  name: string
  is_demo: boolean
  academic_year: string
  expected_graduation: string
  catalog_year: string | null
  planning_term: string
  program_ids: string[]
  campus: string
  f1_status: "yes" | "no" | "prefer_not"
  interests_text: string
  career_interests?: string
  availability: AvailBlock[]
  preferences: {
    credit_target: number
    credit_min: number
    credit_max: number
    avoid_before: string | null
    prefer_later: boolean
    locked_sections: string[]
    excluded_courses: string[]
    required_courses: string[]
    interest_boost_terms: string[]
    deferred_courses?: string[]
    accepted_tradeoffs?: string[]
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = any

export type PlanState = {
  _student: StudentSnapshot
  _iteration: number
  _history: { message: string; applied: string[]; assumptions: string[]; mode: string }[]
  _error?: string
  academic_profile?: Loose
  degree_requirements?: { requirements: RequirementProgress[]; remaining: RequirementProgress[]; courses_needed: number; manual_review: RequirementProgress[]; review_flags: { requirement: string; issue: string }[]; reliability_counts?: Record<Reliability, number>; layers?: { id: string; name: string; type: string; source_url: string | null }[] }
  requirements_research?: RequirementsResearch
  course_discovery?: {
    term_id: string
    term_name: string
    eligible_sections: { section: Section; course: string; requirement_ids: string[]; prereq_status: string; prereq_pending: string[]; requires_linked_section?: boolean; time_tba?: boolean }[]
    excluded: { course: string; section?: string; reason: string; kind?: string }[]
    pattern_exclusion_summary?: Record<string, number>
    courses: Record<string, { code: string; title: string; credits: number; description: string; requirement_ids: string[]; prereq_status: string; prereq_text?: string; offered?: boolean }>
  }
  interest_matching?: {
    themes: { label: string; evidence: string }[]
    scores: Record<string, { score: number; reason: string; matched_themes: string[]; method: string }>
    ranking: string[]
    blocked_high_interest: { course: string; title: string; score: number; missing_prereq: string }[]
    interest_electives?: { course: string; title: string; score: number; reason: string }[]
    enrichment?: { course: string; title: string; score: number; reason: string; why_not: string }[]
  }
  graduation_planning?: {
    semesters_remaining: number
    courses_needed: number
    courses_per_term_needed: number
    priorities: Record<string, { priority: number; chain_length: number; unlocks: string[]; mandatory: boolean }>
    critical_courses: { course: string; chain_length: number; slack: number; unlocks: string[]; reason: string }[]
    risks: { severity: string; issue: string }[]
    assumptions: string[]
    on_track: boolean
  }
  scheduling_constraints?: {
    hard: { code: string; description: string }[]
    soft: { code: string; description: string }[]
    academic: { code: string; description: string }[]
    immigration: { code: string; description: string }[]
    pre_checks: { course: string; issue: string; detail: string }[]
  }
  schedule_optimization?: {
    objective?: string
    candidate_pool?: { eligible_courses: number; considered: number; max_courses: number; slack: number; not_considered: { course: string; score: number; reason: string }[] }
    options: ScheduleOption[]
    infeasible_strategies: { strategy: string; label: string; conflict_set: ConflictGroup[]; minimal: boolean; resolutions: Resolution[] }[]
    ideal_analysis: { perfect_exists: boolean; minimal?: boolean; conflict_set: ConflictGroup[]; resolutions: Resolution[] }
    solver: string
  }
  academic_review?: {
    reviews: Record<string, { status: string; checks: { check: string; passed: boolean; severity: string; detail: string }[]; errors: number; warnings: number }>
    rejected: string[]
    note: string
  }
  student_explanation?: {
    headline: string
    conflict_explanation: { constraints_in_conflict: string[]; details: string[]; minimal: boolean; resolutions: Resolution[] }
    options: { option_id: string; label: string; courses: CourseExplanation[]; tradeoffs: string[]; unresolved: string[]; review_status: string; summary: string; ai_summary?: string }[]
    blocked_interest_alternatives: { course: string; title: string; message: string; eligible_alternatives: { course: string; title: string; in_a_schedule: boolean }[] }[]
    overall_ai_summary: string | null
    enrichment?: { course: string; title: string; score: number; reason: string; why_not: string }[]
    disclaimer: string
  }
}

export type Plan = {
  id: string
  status: "pending" | "running" | "complete" | "failed"
  term_id: string
  student_id: string
  is_demo?: boolean
  iteration: number
  agents: AgentExecution[]
  state: PlanState
}
