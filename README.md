# CIMET QA Gate — "Score the Sale Before It Ships"

An evidence-backed QA scoring engine for sales calls. Every completed sale is
scored against the retailer checklist that was **in force on its call date**,
each result is tied to a real transcript segment, and the final
`APPROVED` / `HOLD` / `HUMAN_REVIEW` decision is made by deterministic
application code — never by a language model.

Persistent (PostgreSQL) · Configurable (rules are data) · Evidence-backed ·
Deterministic where it matters · LLM-constrained · Human-reviewable · Auditable.

---

## 1. The business problem

A sale closed over the phone must pass QA before it can be auto-submitted.
Today that means a person listens to the call against a checklist. This system
automates the checklist pass and — crucially — knows when to stop and ask a
human.

The design bias is stated once and enforced everywhere: **a false approval of a
critical compliance issue is far more damaging than an unnecessary escalation.**
So the engine is built to be unsure out loud rather than confidently wrong.

Checks come in three families:

| Family | Question it answers | Example |
|---|---|---|
| **VERBATIM** | Did the agent say a required thing? | Recording disclaimer, DMO disclosure, cooling-off period |
| **FACTUAL** | Does what was said match the system of record? | Email, peak rate, NMI, DOB, life support, move-in date |
| **BEHAVIOUR** | What shape did the call have? | Dead air, interruptions, rapport, objection handling |

Criticality is configuration, not code. Behaviour checks default to
non-critical; a non-critical failure becomes a coaching note rather than a
blocker unless a checklist explicitly marks it `BLOCKING`.

## 2. System architecture

```mermaid
flowchart TD
    subgraph Inputs
        CRM[Lead / CRM data]
        CAT[Retailer · Plan · Rate card]
        TR[Canonical transcript]
        AU[Call audio]
    end

    CRM --> NORM[Normalisation]
    CAT --> NORM
    TR --> NORM
    AU -. future transcription .-> TR

    NORM --> RES[Checklist version resolution<br/>by retailer + vertical + call date]
    RES --> ROUTER[Rule router<br/>dispatch on evaluation_method]

    ROUTER --> V[Verbatim evaluator]
    ROUTER --> F[Factual evaluator]
    ROUTER --> B[Behaviour evaluator]
    ROUTER --> S[Semantic evaluator]
    S <-->|proposal only| LLM[Evidence interpreter<br/>mock or OpenAI-compatible]

    V --> RESULTS[Structured CheckResults<br/>+ validated Evidence]
    F --> RESULTS
    B --> RESULTS
    S --> RESULTS

    RESULTS --> GATE[Deterministic gate engine<br/>plain Python, no LLM]
    RESULTS --> SCORE[QA score<br/>reported, never gating]

    GATE --> APPROVED[APPROVED]
    GATE --> HOLD[HOLD]
    GATE --> REVIEW[HUMAN REVIEW]

    APPROVED --> AUDIT[Audit trail]
    HOLD --> AUDIT
    REVIEW --> HR[Human review + override]
    HR --> AUDIT
```

Layering is strict: **API → services → repositories → database.** Routes hold
no business logic, services never build API payloads, and nothing above the
repository layer writes SQL.

```
backend/app/
  api/            FastAPI routers + ORM→DTO mappers
  core/           settings, shared enums
  db/             engine, session, Base, portable column types
  models/         SQLAlchemy ORM (the persistent domain model)
  schemas/        Pydantic v2 request/response contracts
  repositories/   the only place that talks SQL
  services/
    ingestion/    transcript parsing + audio storage (the upstream seam)
    normalization/ spoken→canonical email, number, date, identifier, boolean
    evidence/     locate → extract → validate segment references
    rules/        version resolution, authoritative sources, authoring
    scoring/      evaluators, dispatch registry, engine, QA score
    gate/         the deterministic gate policy (one file, no dependencies)
    review/       override + review queue
    audit/        append-only event recording
    storage/      FileStorage abstraction (local disk today, S3 later)
    llm/          EvidenceInterpreter abstraction + adapters
    leads/        lead application service
    dashboard/    operational aggregation
  seed/           realistic Energy seed data, inserted into PostgreSQL
```

## 3. Domain model

```
Vertical  →  Retailer  →  Plan  →  RateCard (date-effective)
                  ↓
              Checklist  →  ChecklistVersion (date-effective, immutable once published)
                                    ↓
                              CheckDefinition (one QA rule, expressed as data)

Lead ──< Call ──< Transcript ──< TranscriptSegment
  └──< ScoringRun ──< CheckResult ──< Evidence
                            └──< HumanOverride
ScoringRun ──< HumanReview            AuditEvent (append-only, spans everything)
```

Leads use **normalised core columns plus a flexible `attributes` JSONB blob**.
Fields every vertical shares (email, DOB, address) are real columns so they can
be indexed and compared; anything vertical-specific — NMI, MIRN, fuel type,
life support, loan term, policy excess — lives in `attributes`. A retailer
adding one CRM field needs no migration.

Ids are realistic, not `LEAD001`: PostgreSQL sequences start leads at
`3613790`, calls at `7100452`, transcripts at `900124`, retailers at `101`,
plans at `2045`, agents at `7821`.

## 4. The canonical transcript contract

This shape is frozen. It is what the scoring engine consumes, and it is
deliberately independent of whoever produced the transcription.

```json
{
  "transcript_id": 900124,
  "lead_id": 3613790,
  "call_id": 7100452,
  "source": "MANUAL_UPLOAD",
  "language": "en-AU",
  "segments": [
    {
      "segment_id": 1,
      "speaker": "AGENT",
      "start_time": 12.10,
      "end_time": 17.85,
      "text": "This call may be recorded for quality and compliance purposes.",
      "asr_confidence": 0.98
    }
  ]
}
```

Two confidences, never conflated:

* `segment.asr_confidence` — how sure the **transcriber** was of the words.
* `CheckResult.confidence_level` (`HIGH`/`MEDIUM`/`LOW`) — how sure the
  **evaluator** is of its verdict.

They are related but distinct: poor transcription *lowers* evaluation
confidence, and a `LOW`-confidence critical check is downgraded to `UNCERTAIN`.

`speaker` supports `AGENT`, `CUSTOMER`, `UNKNOWN`. Silence is **not** a
segment type — dead air is derived from gaps between consecutive segments,
which keeps the contract clean for any provider.

## 5. Database and migrations

PostgreSQL via SQLAlchemy 2.x, schema managed by Alembic. 22 tables:

`verticals`, `retailers`, `retailer_verticals`, `plans`, `rate_cards`,
`agents`, `team_leaders`, `campaigns`, `sites`, `leads`, `calls`,
`transcripts`, `transcript_segments`, `checklists`, `checklist_versions`,
`check_definitions`, `scoring_runs`, `check_results`, `evidence`,
`human_reviews`, `human_overrides`, `audit_events`.

One migration, `f9fd04fa44a3_initial_schema`, creates the id sequences and
every table. JSON columns are `JSONB` on PostgreSQL and plain `JSON`
elsewhere, so the test suite can also run on SQLite without a server.

## 6. Checklist versioning

```mermaid
flowchart LR
    D[Draft v3<br/>editable] -->|publish with effective_from| P3[Published v3<br/>2026-10-01 → open]
    P2[Published v2<br/>2026-09-01 → 2026-09-30] -.->|window closed automatically| P3
    P1[Published v1<br/>2026-01-01 → 2026-08-31] -.-> P2

    C1[Call on 2026-08-20] --> P1
    C2[Call on 2026-09-18] --> P2
    C3[Call on 2026-10-05] --> P3
```

* Published versions are **immutable**. Editing one raises `409`; the only way
  to change a rule is to create a new draft, edit it, and publish it with an
  effective date.
* Publishing closes the previous version's window the day before, so windows
  stay contiguous and every call date resolves to exactly one version.
* Drafts are never eligible for scoring.

The seeded demo ships two published versions, and lead `3614266` (an August
call) proves the point: it is scored against v1's older disclaimer wording and
the older rate card. Under the current rules it would fail both.

## 7. Scoring workflow

```mermaid
sequenceDiagram
    participant API
    participant Engine as Scoring engine
    participant Rules
    participant Eval as Evaluators
    participant Gate as Deterministic gate
    participant DB

    API->>Engine: POST /leads/{id}/score
    Engine->>DB: load lead, transcript, plan
    Engine->>Rules: resolve checklist for call_date
    Rules-->>Engine: ChecklistVersion (published, in-window)
    Engine->>Rules: rate card in force on call_date
    Engine->>DB: INSERT ScoringRun (RUNNING)
    loop each active check
        Engine->>Eval: applicability → evaluate
        Eval-->>Engine: status, confidence, evidence, reason
        Engine->>DB: INSERT CheckResult + Evidence
    end
    Engine->>Gate: statuses + execution statuses
    Gate-->>Engine: APPROVED | HOLD | HUMAN_REVIEW
    Engine->>DB: UPDATE run, INSERT audit events
    Engine-->>API: ScoringRun
```

**Scoring runs are append-only.** Re-scoring inserts a new `ScoringRun`; every
earlier run keeps its results, evidence and gate decision byte-for-byte, so
"what did we decide in September, and why?" stays answerable.

## 8. Evidence workflow and traceability

```mermaid
flowchart LR
    CD[CheckDefinition] --> LOC[Locate candidates<br/>by evidence_source + keywords]
    LOC --> EXT[Extract observed value<br/>email · number · date · id · boolean]
    EXT --> VAL[Validate segment ids<br/>against the real transcript]
    VAL --> EV[Evidence row<br/>transcript_id · segment_id · speaker<br/>text · start_time · end_time · extraction_method]
    EV --> UI[Reviewer clicks the quote]
    UI --> TRX[Transcript segment highlights]
    UI --> AUD[Audio seeks to start_time]
```

Checks never scan the transcript themselves; all search goes through the
evidence engine. That is what makes "did the evaluator search the complete
relevant scope?" answerable by inspection — the precondition for allowing an
absence-based FAIL at all.

Every result answers: **what rule** (code + name), **which version**
(`rule_version`), **what we observed**, **what was expected**, **where in the
transcript** (segment id + timestamps + extraction method), **why**
(human-readable reason), **how confident** (`HIGH`/`MEDIUM`/`LOW`).

## 9. Where the LLM is used — and where it is not

The LLM is an **evidence interpreter**, reached only by the `SEMANTIC`
evaluator (and by the interpretive behaviour metrics, rapport and objection
handling, which route through it).

### It is routed by rule configuration — it is not a fallback

Which evaluator runs is decided by each rule's `evaluation_method`, stored in
the database. There is no "try the deterministic check, then ask the model if
that fails" step anywhere:

| Check | Method | LLM involved? |
|---|---|---|
| Recording disclaimer, account holder, DMO, T&Cs, cooling-off | `NORMALIZED_TEXT` | **No** |
| Email, peak rate, supply charge, address, DOB, NMI, MIRN, fuel type, life support, move-in date, concession, gift card | `EMAIL` / `NUMERIC` / `DATE` / `IDENTIFIER` / `BOOLEAN` / `NORMALIZED_TEXT` | **No** |
| Dead air, interruptions | `BEHAVIOUR` (measured from segment timings) | **No** |
| **Rapport, objection handling** | `BEHAVIOUR` with an interpretive metric | **Yes** — both non-critical |

So in the seeded checklist, **every critical check is fully deterministic** and
the model is consulted for exactly two non-critical coaching signals. A
deterministic FAIL or UNCERTAIN is final: nothing sends it to a model for a
second opinion, so a model cannot turn a wrong rate or a wrong email into a
pass. `tests/test_llm_boundary.py` proves this with a deliberately hostile
interpreter that answers `PASS / HIGH` to everything — the gate is unchanged.

A `SEMANTIC` rule can be *configured* as critical (say, a paraphrase-tolerant
disclosure). If you do, the controls in §10 apply, and you should treat it as a
deliberate choice, not a default.

**Used for:** conversational interpretation and behaviour judgement that has no
exact answer.

**Never used for:** the gate, criticality, checklist version selection,
authoritative values, or any exact comparison — numeric, email, date,
identifier and boolean equality are all deterministic code.

It may return only this, and nothing else:

```json
{
  "decision": "PASS|FAIL|UNCERTAIN",
  "confidence_level": "HIGH|MEDIUM|LOW",
  "evidence_segment_ids": [47],
  "observed_value": "...",
  "reason": "..."
}
```

Coarse confidence levels are deliberate: an LLM's self-reported float is not
meaningful enough to gate compliance on.

### Providers

* **`mock`** (default) — deterministic keyword matching, offline, no key. What
  the test suite always uses (`conftest.py` forces it, even if your
  `backend/.env` points at Groq).
* **`groq`** — Groq's OpenAI-compatible API. Configure in `backend/.env`
  (git-ignored; see `.env.example`):

  ```
  LLM_PROVIDER=groq
  GROQ_API_KEY=<your key>
  GROQ_MODEL=openai/gpt-oss-120b
  ```

  Check the connection without scoring anything:

  ```powershell
  cd backend
  .\.venv\Scripts\python -m app.services.llm.selftest
  ```

  `GET /health` reports `llm_provider`, `llm_model` and `llm_ready` (whether a
  key is set — never the key). Groq retires models: `llama-3.3-70b-versatile`
  is already gone, and a 404 "model does not exist" means set `GROQ_MODEL` to a
  current one (`https://api.groq.com/openai/v1/models` lists what your key can
  use).
* **`openai_compatible`** — the same adapter pointed at any other OpenAI-style
  endpoint via `LLM_BASE_URL`.

### What is sent to the provider

Data minimisation is the default. The prompt contains the check's name and
criteria and the in-scope **transcript segments**, and nothing else: **no CRM
fields** (email, DOB, address, NMI, phone) and no rate-card values. A rule can
opt in to specific reference values with
`"llm_context_sources": ["PLAN.name"]`. Card numbers, CVVs and expiry dates are
already redacted at ingest, before any of this.

Spoken personal details in the transcript itself (a name, an address read
aloud) are still sent, because the model has to read the call. Do not point a
real provider at real customer calls until that is covered by your data-handling
agreement.

### When the provider fails

Any failure — no key, network error, timeout, HTTP error, prose instead of JSON,
an invented `decision` value — becomes `UNCERTAIN` and the check is marked
`execution_status=ERROR`. Rate limits (HTTP 429/503) are retried up to twice,
only when the provider's own suggested wait is 8 seconds or less; longer waits
fail fast rather than hang the scoring request. Provider error text is stored
for diagnosis with organisation ids masked, and the API key is never stored.

**Operational consequence to know about.** By your policy, a check that errors
can never lead to `APPROVED` — and that applies to non-critical checks too. So
during a Groq outage or rate-limit spell, sales that would otherwise be approved
are routed to `HUMAN_REVIEW` because their coaching checks could not run.
Groq's free tier allows 8,000 tokens per minute on `gpt-oss-120b`; each sale
uses roughly 2–3k, so scoring many sales back-to-back needs a paid tier (or a
smaller model). One-at-a-time scoring from the UI is fine.

Every interpreter call is recorded on the result: provider, model,
prompt_version, evaluation_method, latency, success, what it claimed, and any
segment ids it cited that did not exist.

## 10. Hallucination controls (implemented, not just documented)

| Control | Where it lives | Proven by |
|---|---|---|
| No transcript evidence → never PASS | `evaluators/factual.py`, `semantic.py` | `test_value_never_stated_is_uncertain_and_never_pass` |
| Authoritative source missing → UNCERTAIN | `rules/sources.py` returns `found=False`, never a default | `test_missing_authoritative_value_is_uncertain_not_fail` |
| Contradictory evidence → UNCERTAIN unless a precedence rule exists | `evaluators/factual.py` | `test_contradictory_evidence_is_uncertain_without_precedence_rule` |
| LLM must cite real segments | `evidence/validator.py` | `test_interpreter_citing_a_nonexistent_segment_has_it_discarded` |
| A claimed PASS with no valid citation is downgraded | `evaluators/semantic.py` | `test_interpreter_claiming_pass_without_citation_is_downgraded` |
| Strict schema validation of model output | `llm/schemas.py` | `test_malformed_interpreter_decision_is_rejected_by_the_schema` |
| Provider failure → UNCERTAIN, never a crash or a pass | `llm/interpreter.py` | `test_provider_failure_degrades_to_uncertain_and_flags_execution` |
| LOW confidence on a critical check → UNCERTAIN | `scoring/context.py` | `test_low_confidence_on_a_critical_semantic_check_becomes_uncertain` |
| Incomplete/errored execution can never approve | `gate/policy.py` | `test_incomplete_execution_can_never_approve` |
| Rule version chosen by application logic, not a model | `rules/resolver.py` | `test_call_date_selects_the_version_in_force_at_the_time` |
| Published rules immutable | `rules/authoring.py` | `test_published_version_cannot_gain_a_check` |
| Overrides preserve the machine result | `review/service.py` | `test_override_preserves_the_machine_result` |
| Card numbers never reach scoring, the LLM, or the UI | `normalization/redaction.py`, applied at ingest | `test_card_numbers_are_redacted_at_ingest` |

`False` is not `missing`: `get_authoritative_value` distinguishes "concession
is false" from "concession is unknown", because conflating them would let a
missing CRM field silently pass a check.

### Extra guards for messy real speech

Real transcripts are noisier than scripted ones. These closed the ways a wrong
value could otherwise slip through (all deterministic, all tested in
`tests/test_false_pass_guards.py`):

* **Keywords match on word boundaries**, and "peak rate" never matches inside
  "off-peak rate", so an off-peak figure cannot be read as the peak rate.
* **Numbers must carry a rate unit** (`cents`, `$`, `kWh`) to count, and every
  candidate is collected rather than the first one taken: "33.14 cents for 12
  months" ignores the 12; two different rates in a call conflict to UNCERTAIN.
  The spoken word "for" is never read as the digit 4.
* **Approximate or range figures are never verified**: "around", "about",
  "between", "33 to 34 cents" → UNCERTAIN even if the right number appears.
* **Answers found in the next turn** (question in one turn, answer in the next)
  are read via a configured context window; a wrong answer there still FAILs.
* **Speech-to-text artefacts**: a disclosure split across adjacent segments, or
  with words run together ("assuranceand"), still matches — at MEDIUM
  confidence — but never across the other party speaking, and never for short
  phrases. Number words and digits meet on both sides ("fourteen" = "14").
* **One-time codes read aloud are redacted**, alongside card numbers.
* **Dead air is not flagged after "I'll mute the recording"**, with a short
  look-back so the customer's "okay" doesn't defeat the exclusion.
* **The model is only shown what it needs** and may only cite what it was
  shown: objection handling runs only when the customer raised a concern;
  rapport sees only the opening and closing; a citation outside that set is
  discarded.

## 11. Gate logic

`apply_gate_policy()` in
[`backend/app/services/gate/policy.py`](backend/app/services/gate/policy.py) is
the only place a gate is decided, and it is plain control flow over enum
values:

1. Any applicable check that **did not complete** → `HUMAN_REVIEW`
2. Any **critical** check `FAIL` → `HOLD`
3. Any **critical** check `UNCERTAIN` → `HUMAN_REVIEW`
4. Any applicable check without a terminal status → `HUMAN_REVIEW`
5. Any non-critical `FAIL` explicitly configured `BLOCKING` → `HOLD`
6. Otherwise → `APPROVED`

Rule 1 outranks rule 2 on purpose: if the system did not finish looking, it
does not get to assert *why* the sale is being stopped. Both outcomes stop the
sale, so the ordering introduces no approval risk.

No LLM call happens in this function or anywhere downstream of it — that is
structural, not a convention: its inputs are enums and its output is an enum.

### QA score is not the gate

The score is reported for coaching and trend reporting and is calculated
separately. In the seeded demo, lead `3613827` scores **94.1%** and is still
`HOLD`, because the one thing it got wrong was a critical rate quote. Approval
is never `score >= threshold`.

## 12. Human review

Overrides are **additive**. The machine's `CheckResult.status` is never
written to; a `HumanOverride` row is appended carrying the original status, the
new status, a reason code, mandatory free-text notes, the actor and the
timestamp. The run keeps its machine `gate_result` and gains an
`override_gate_result`, so both the automated and the reviewed outcome remain
visible forever.

Reason codes: `TRANSCRIPTION_ERROR`, `EVIDENCE_MISSED`, `RULE_INTERPRETATION`,
`CRM_DATA_ERROR`, `AGENT_CORRECTED_LATER`, `APPROVED_EXCEPTION`, `OTHER`.

The review queue prioritises **critical UNCERTAIN** above **critical FAIL** —
an uncertain check is the one actually waiting on a person; a failure is
already decided.

## 13. Audio storage

Uploaded recordings go through the `FileStorage` abstraction
(`app/services/storage/`). Only the storage key is persisted; local disk today,
S3/Azure Blob later by implementing one protocol — no business-logic change.

Playback is served by the backend with **HTTP Range support**, which is what
lets the reviewer's player seek straight to a piece of evidence instead of
downloading the whole call.

On a sale's page the audio player sits beside the transcript, always visible.
**Every check shows its position in the call** (an "Audio time" fact plus a
timestamp on each evidence quote), and so does every transcript line. When a
recording exists these are playable (`▶ 0:14–0:18` plays that moment with five
seconds of context either side and highlights the matching transcript lines).
When a sale has no recording, the panel shows a placeholder with an "Upload
recording" action instead, and the timestamps stay visible as plain text so the
moment can still be located in the transcript.

The seed attaches synthetic audio to three sales (`3613790`, `3613827`,
`3614071`) and leaves the rest without, so the demo shows both states. The
seeded audio is a tone rendered from the transcript's own timings (a different
pitch per speaker, real silence in the gaps) — there is no speech in it.

## 14. Transcription (audio in, canonical transcript out)

```
Audio ──▶ [ transcription provider ] ──▶ canonical segments ──▶ TranscriptionJob (staged)
                                                                     │  lead created / chosen
                                                                     ▼
                                              attach ──▶ Transcript + Call audio ──▶ existing pipeline
```

The intake flow is *upload audio → Transcribe → confirm sale details → Save &
Score*, so a job exists **before** the sale does. Jobs are persisted
(`transcription_jobs`), which also gives an audit trail of what each provider
returned. The scoring engine never sees a provider; it only reads canonical
segments.

**Providers** (`services/transcription/providers.py`, one small class each):

* **`groq`** — live speech recognition via Groq's Whisper
  (`GROQ_STT_MODEL`, default `whisper-large-v3-turbo`), using the same
  `GROQ_API_KEY` as the LLM. Works even when `LLM_PROVIDER=mock`.
* **`embedded`** — offline, no recognition. Reads the transcript embedded in a
  recording made by the demo generator. It is labelled as such everywhere and
  exists so a demo still works with no network or key.

**Speakers come from channels, not guesses.** Call-centre audio is normally
dual-channel (agent left, customer right). Each channel is transcribed on its
own and attributed to its role, so speaker separation is deterministic. Mono
audio still works, but every line is `UNKNOWN` and checks that depend on who
spoke resolve to `UNCERTAIN` — a warning says so.

**Timestamps are corrected from the audio.** Whisper's segment times are
approximate (they snap to its 30-second windows) and it sometimes merges a
speaker's lines across the other person's turn. On dual-channel calls the
system measures each channel's actual speech activity, splits merged turns at
the other party's silence using word-level times, and clamps every segment
inward to the measured speech. It never widens a segment, so it cannot make a
line claim words from another turn. Measured against a 160-second scripted
call: median start error 0.10s, 90th percentile 0.53s (uncorrected: worst case
was 20s).

**Confidence** is anchored to Whisper's own reliability threshold
(`avg_logprob` below −1.0 is "unreliable", above about −0.3 is clean), mapped
linearly to 0–1. A dubious transcription lowers evaluation confidence, and a
LOW-confidence critical check becomes UNCERTAIN.

**Also:** likely non-speech ("Thank you." hallucinated on a silent channel) is
dropped and counted in the job's warnings; audio is capped at 30 MB
(`MAX_UPLOAD_BYTES`); HTTP 429/503 are retried once or twice within a bounded
wait; one-time codes and card numbers are redacted before the job is stored.

The "Transcribe Audio" button on a sale that already has a recording calls
`POST /leads/{id}/transcribe`.

## 15. Why RAG is intentionally not used

Nothing here needs retrieval. What a check compares against is either a fixed
script phrase kept in the rule itself, or a handful of structured fields looked
up by exact key (`RATE_CARD.peak_rate`, `LEAD.customer_email`). A vector store
would add infrastructure and a new failure mode — irrelevant retrieval — to
solve a problem the system does not have.

If a future version must check against a large unstructured policy manual, RAG
becomes a reasonable evaluator to add *behind the existing
`EvidenceInterpreter` interface*. It still would not touch the gate.

## 16. Running it

### PostgreSQL

```powershell
docker run -d --name cimet-qa-postgres `
  -e POSTGRES_PASSWORD=cimet -e POSTGRES_USER=cimet -e POSTGRES_DB=cimet_qa `
  -p 5433:5432 postgres:16
```

Any PostgreSQL 14+ works; point `DATABASE_URL` at it.

### Backend (Python 3.12)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

.\.venv\Scripts\python -m alembic upgrade head      # create the schema
.\.venv\Scripts\python -m app.seed.run_seed          # load demo data
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

API docs: <http://127.0.0.1:8000/docs>

Re-seed from scratch (drops all rows, including scoring history):

```powershell
.\.venv\Scripts\python -m app.seed.run_seed --reset
```

### Frontend (Node 18+)

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The dev server proxies `/api/*` to port 8000, so
start the backend first.

### Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q                  # SQLite, no server needed

# or against real PostgreSQL:
$env:TEST_DATABASE_URL="postgresql+psycopg://cimet:cimet@localhost:5433/cimet_qa_test"
.\.venv\Scripts\python -m pytest -q
```

## 17. Demo scenarios

Seven seeded Energy sales for **Aurora Energy Retail**, all synthetic. Rate
cards: 31.90 c/kWh until 2026-08-31, then 33.14 c/kWh.

| Lead | Scenario | What happens | Gate |
|---|---|---|---|
| `3613790` | Clean sale | Every critical check passes; QA score 100% | **APPROVED** |
| `3613827` | Rate mismatch | Agent quotes 31.9c against a 33.14c rate card | **HOLD** |
| `3613944` | Email mismatch | Agent reads back `bigpond.com`; CRM says `outlook.com` | **HOLD** |
| `3614071` | Ambiguous rate | Correct rate, but transcribed at 0.41 ASR confidence → LOW → critical UNCERTAIN | **HUMAN_REVIEW** |
| `3614158` | Agent corrects rate later | Two different rates stated, no precedence rule configured | **HUMAN_REVIEW** |
| `3614203` | Dead air | 15s silence gap; non-critical, so a coaching note only | **APPROVED** |
| `3614266` | Historical rule version | August call scored against checklist v1 + the older rate card | **APPROVED** |

Scenarios 4 and 5 are the interesting ones: the system is *not* wrong in
either, and it does not pretend to be right. Scenario 5 also shows the
extension point — configure `"conflict_precedence": "LAST"` on the rule and a
corrected rate resolves deterministically instead.

**Suggested demo path:** Dashboard → QA Review (see 3614071 at the top of the
queue) → open it → click the peak-rate evidence to highlight the transcript and
seek the audio → override it with `TRANSCRIPTION_ERROR` → watch the gate move
to APPROVED while the machine's UNCERTAIN stays on the record → check the Audit
Trail → Configuration to see v1/v2 history and why published versions are
read-only.

### Demo recordings (audio + timestamped transcripts)

Eleven synthetic Energy calls, generated locally with the two offline Windows
voices. Each is a **dual-channel** WAV (agent left, customer right) whose
transcript timestamps come from the measured speech, so they line up with the
audio exactly.

```powershell
cd backend
.\.venv\Scripts\python -m app.demo.generate          # -> backend/demo_calls/
.\.venv\Scripts\python -m app.demo.generate --list
```

This writes the recordings, a sidecar `.transcript.json` for each, and
`DEMO_SHEET.md` listing every file with its expected outcome and the sale
details to enter. The folder is git-ignored; the scripts are what is committed.
Generation takes about 25 seconds and needs Windows.

| File | Expected | Demonstrates |
|---|---|---|
| `01_clean_approve` | **APPROVED** | Every critical check passes, including the payment-mute sequence |
| `02_wrong_rate_hold` | **HOLD** | Agent quotes last year's rate |
| `03_no_disclaimer_hold` | **HOLD** | Recording disclaimer never read (absence after a full-scope search) |
| `04_email_mismatch_hold` | **HOLD** | Email read back with the wrong domain |
| `05_rate_corrected_review` | **HUMAN_REVIEW** | Wrong rate then corrected: contradictory evidence, no precedence rule |
| `06_life_support_unclear_review` | **HUMAN_REVIEW** | Hedged answer to a critical question is never guessed |
| `07_hedged_rate_review` | **HUMAN_REVIEW** | "Around thirty-three cents": right number, still unverifiable |
| `08_payment_not_muted_hold` | **HOLD** | Payment taken without muting the recording |
| `09_coaching_notes_approve` | **APPROVED** | 14s dead air and repeated interruptions are notes, not blockers |
| `10_objection_handled_approve` | **APPROVED** | Hesitant customer, gift card, objection handled |
| `11_flagship_messy_approve` | **APPROVED** | Long messy call modelled on a real recording: filler, ID verification, mute for payment, an OTP read aloud (redacted), cross-sell |

**Live demo flow:** Add Lead → choose a `.wav` → **Transcribe** (live Groq, or
the offline provider) → the sale details fill in from the file name and stay
editable → **Save & Score**. Every scenario's expected gate is asserted by the
test suite (`tests/test_demo_scenarios.py`) and was also verified end to end
through the running API.

### Demo data page (`DEMO_MODE=true`)

For showing a re-score. Browse leads, rate cards, transcripts, runs, evidence,
overrides, checklists and the audit trail; edit the *inputs* a sale is scored
against; reset everything.

* Editable: a lead's CRM fields, a rate card's rates and dates, a transcript
  line's text. **Read-only:** check results, evidence, overrides, checklist
  rules and the audit trail (published rules stay immutable; history stays
  history). No raw SQL.
* Every edit is written to the audit trail with before and after values.
* After editing, open the sale and press **Re-score**: a new run is created,
  the old one is untouched, and a **"Changes since run #N"** panel shows the
  gate and each check that moved — for example *HOLD → APPROVED* with
  `Peak Usage Rate Accuracy: FAIL → PASS`.
* The routes return 404 unless `DEMO_MODE=true`; the page is hidden too.

## 18. Current assumptions

* Scoring examples focus on Energy; the schema and UI already carry seven
  verticals and multiple retailers.
* One transcript per lead; the most recent is scored. Diarisation is assumed
  done upstream.
* Factual checks pre-filter candidate segments by keyword before extraction —
  a simple, auditable heuristic, not semantic search.
* Pasted transcripts get synthesised 2-second timings, so behaviour checks that
  depend on real timing should use an uploaded canonical transcript.
* Confidence levels are rule-based (comparison certainty discounted by ASR
  confidence), not statistically calibrated.
* Australian conventions for dates (day-first) and phone numbers.
* No authentication — every actor field is free text supplied by the caller.

## 19. Known limitations

* **No authentication or authorisation.** Anyone who can reach the API can
  score or override anything. This is the first thing to add before any real
  deployment.
* The UI was verified by building it, typechecking it, and exercising every
  endpoint it calls through the running dev server and its proxy. **It was not
  visually verified in a browser** — no browser automation was available in
  the environment it was built in. Please click through it and report anything
  that looks wrong.
* **Live transcription needs dual-channel audio for full checking.** Mono
  recordings transcribe but leave speakers `UNKNOWN`, so speaker-dependent
  checks return UNCERTAIN (there is no acoustic diarisation).
* **Groq's free tier is tight** (8,000 tokens/minute for the chat model; an
  hourly audio-seconds budget for Whisper). Under your policy a check that
  errors can never approve, so an exhausted quota routes otherwise-clean sales
  to HUMAN_REVIEW. Coaching checks send only the minimum (objection handling
  only when a concern was raised; rapport only the opening and closing), and
  rate limits are retried, but bulk scoring needs a paid tier.
* **Live speech recognition is not perfect, and the gate is built to absorb that
  safely.** Run against Groq Whisper, the clean demo call reaches APPROVED and a
  call with a wrong disclosure still reaches HOLD, but a fast, messy call can
  lose decimals ("33 cents" for 33.14), merge turns or miss a word. Every such
  error we observed moved a sale to a *more cautious* gate (HOLD or
  HUMAN_REVIEW), never toward APPROVED, because a value that is missing or
  different can only fail or be uncertain. What ASR cannot rule out is a
  mis-heard figure that happens to equal the CRM value, so a reviewer can jump to
  the exact audio moment behind every check. For a guaranteed walkthrough use the
  **embedded** provider (all 11 recordings reach their intended gate). No
  vocabulary "prompt" is sent to Whisper: one leaked its own words into the
  transcript, and a compliance transcript must contain only what was said.
* Demo audio is generated with Windows speech synthesis, so it can only be
  (re)generated on Windows. Whisper timestamps are corrected from the audio but
  remain approximate on very noisy recordings.
* The seed's `--reset` deletes scoring history; it is a demo convenience, not
  an operational tool.

## 20. The CIMET adapter layer — what changes tomorrow

When CIMET provides the real checklist, CRM schema, transcript schema, audio
and sandbox payloads, these are the **only** files that need to change:

1. **`backend/app/seed/checks.py`** — the real checklist becomes rows. Each
   rule is `check_type` + `evaluation_method` + `expected_source` +
   `evaluation_config`. No new Python unless a genuinely new *kind* of
   comparison appears.
2. **`backend/app/services/rules/sources.py`** — map CIMET's CRM field names
   into the authoritative context (`build_authoritative_context`). This is
   where `LEAD.attributes.nmi` gets pointed at whatever CIMET actually calls
   it.
3. **`backend/app/services/ingestion/transcript.py`** — add a parser for
   CIMET's transcript envelope alongside the canonical and pasted parsers. It
   only has to emit `ParsedSegment`s.
4. **`backend/app/services/storage/`** — implement the `FileStorage` protocol
   against CIMET's object store, if audio does not live on local disk.
5. **`backend/app/core/enums.py`** — extend `EvaluationMethod` (and register
   the evaluator in `services/scoring/registry.py`) only if a real rule needs
   a comparison the current nine methods cannot express.

Everything else — the gate, the evidence engine, scoring-run history, the audit
trail, the review queue, the whole UI — is domain-agnostic and should not need
to move.

## 21. Future extensions

* Authentication, roles (agent / team leader / QA reviewer / admin) and
  per-role queue filtering.
* A transcription provider adapter behind the seam described in §14.
* Per-retailer gate policy configuration (e.g. "more than N coaching notes also
  blocks").
* Calibrating confidence against reviewer override rates — the audit trail
  already captures exactly the data needed to measure where the engine is
  over- and under-confident.
* Agent- and team-level coaching reports from `CheckResult` history.
