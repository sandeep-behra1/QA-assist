import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

BACKEND_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DATABASE_URL = "postgresql+psycopg://cimet:cimet@localhost:5433/cimet_qa"

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Groq retires and renames models (llama-3.3-70b-versatile is already gone). If a call
# fails with a 404 "model does not exist", set GROQ_MODEL to a current one.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
# Speech-to-text model (Groq hosts Whisper). Same rule: override with GROQ_STT_MODEL if retired.
DEFAULT_GROQ_STT_MODEL = "whisper-large-v3-turbo"

LLM_PROVIDERS = {"mock", "groq", "openai_compatible"}


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines (comments, blank lines and simple quotes handled)."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Strip a trailing inline comment, but only when the value is unquoted.
        if value[:1] not in {'"', "'"} and " #" in value:
            value = value.split(" #", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_dotenv(path: Path) -> None:
    """Load backend/.env into the environment without overriding real env vars.

    Real environment variables always win, which is what lets the test suite
    pin LLM_PROVIDER=mock even when a developer's .env points at Groq.
    """
    if not path.is_file():
        return
    for key, value in parse_dotenv(path.read_text(encoding="utf-8-sig")).items():
        os.environ.setdefault(key, value)


class Settings(BaseModel):
    """Runtime configuration.

    Everything here has a working default: the app boots, migrates, seeds and
    scores with no environment at all. The LLM provider defaults to the offline
    mock, so no API key is ever required for the demo.
    """

    app_name: str = "CIMET QA SaleGuard"
    database_url: str = DEFAULT_DATABASE_URL
    sql_echo: bool = False

    media_root: Path = BACKEND_ROOT / "storage" / "audio"

    # LLM / evidence interpreter. For provider "groq" these are resolved from
    # GROQ_API_KEY / GROQ_MODEL; llm_api_key is never logged or returned by
    # any endpoint.
    llm_provider: str = "mock"  # "mock" | "groq" | "openai_compatible"
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str = DEFAULT_GROQ_MODEL
    llm_prompt_version: str = "evidence-interpreter-v2"
    llm_timeout_seconds: float = 20.0

    # Speech-to-text. The Groq key is independent of LLM_PROVIDER, so audio can
    # be transcribed live even while the interpretive checks run on the mock.
    groq_api_key: str | None = None
    groq_base_url: str = GROQ_BASE_URL
    groq_stt_model: str = DEFAULT_GROQ_STT_MODEL
    transcription_timeout_seconds: float = 180.0
    max_upload_bytes: int = 30 * 1024 * 1024

    # Demo tooling: the Demo Data page, presets and reset. Off by default.
    demo_mode: bool = False

    # A transcript segment whose ASR confidence is below this is treated as
    # unreliable transcription, which caps evaluation confidence at LOW.
    asr_confidence_floor: float = 0.60

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @property
    def llm_ready(self) -> bool:
        """True when scoring will actually be able to reach the configured model."""
        if self.llm_provider == "mock":
            return True
        return bool(self.llm_api_key)

    @property
    def stt_ready(self) -> bool:
        """True when live (Groq Whisper) transcription can be attempted."""
        return bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    load_dotenv(BACKEND_ROOT / ".env")

    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    if provider not in LLM_PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER must be one of {sorted(LLM_PROVIDERS)} (got {provider!r})."
        )

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = os.getenv("GROQ_BASE_URL", GROQ_BASE_URL)
        model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    else:
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL")
        model = os.getenv("LLM_MODEL", DEFAULT_GROQ_MODEL if provider == "mock" else "gpt-4o-mini")

    media_root = os.getenv("MEDIA_ROOT")
    return Settings(
        database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        sql_echo=os.getenv("SQL_ECHO", "").lower() in {"1", "true", "yes"},
        media_root=Path(media_root) if media_root else BACKEND_ROOT / "storage" / "audio",
        llm_provider=provider,
        llm_api_key=api_key or None,
        llm_base_url=base_url or None,
        llm_model=model,
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_base_url=os.getenv("GROQ_BASE_URL", GROQ_BASE_URL),
        groq_stt_model=os.getenv("GROQ_STT_MODEL", DEFAULT_GROQ_STT_MODEL),
        demo_mode=os.getenv("DEMO_MODE", "").lower() in {"1", "true", "yes"},
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(30 * 1024 * 1024))),
        asr_confidence_floor=float(os.getenv("ASR_CONFIDENCE_FLOOR", "0.60")),
    )
