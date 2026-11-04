from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore")

    database_url: str = f"sqlite:///{REPO_ROOT / 'apps' / 'api' / 'academic_planner.db'}"
    data_dir: Path = REPO_ROOT / "data" / "temple"
    upload_dir: Path = REPO_ROOT / "apps" / "api" / "uploads"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    # Student education records are never sent to the LLM unless explicitly enabled
    # under an institutional data agreement. Only catalog data and interest text are sent.
    llm_may_receive_student_records: bool = False

    # Authorized Temple data feed for live availability (not available to this prototype).
    temple_data_api_url: str | None = None
    temple_data_api_token: str | None = None

    # Requirements Research Agent: fetch the public Academic Bulletin pages for a student's
    # programs at plan time (robots.txt respected, 1 request/second, cached for the TTL).
    # When off, or when Temple is unreachable, the ingested snapshot is used and labeled.
    live_bulletin_research: bool = True
    bulletin_cache_ttl_hours: int = 24
    bulletin_timeout_seconds: float = 8.0

    # Real students must upload their graduation plan before schedules are proposed; the plan's
    # courses for the planning semester are then the only courses scheduled. The whole-pipeline
    # audit tools (program sweep, stress test) turn this off to exercise requirement-driven planning.
    require_grad_plan: bool = True

    cors_origins: list[str] = ["http://localhost:3000"]
    max_upload_bytes: int = 5 * 1024 * 1024

    # F-1 full course of study (undergraduate): 12 credits, of which at most one
    # online course / 3 online credits may count. Configurable, not hardcoded in logic.
    f1_full_time_credits: int = 12
    f1_max_online_credits_counted: int = 3
    f1_hybrid_counts_as_in_person: bool = False

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


settings = Settings()
