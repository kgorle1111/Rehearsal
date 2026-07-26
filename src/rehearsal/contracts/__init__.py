"""Frozen interface contracts — the shared spine every workstream builds against.

Per BUILD.md §4: these shapes are immutable once broadcast. A workstream that
wants a new field files a contract-change note; it does not add one locally
or redefine these types in its own package.

Binding summary of the fuller schemas in misc/docs/15-workstreams.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ErrorType(Enum):
    OMISSION = "omission"
    ADDITION = "addition"
    SUBSTITUTION = "substitution"
    DISTORTION = "distortion"
    EDITORIALIZATION = "editorialization"
    ROLE_EXCHANGE = "role_exchange"
    REGISTER_SHIFT = "register_shift"
    FALSE_FLUENCY = "false_fluency"
    FIRST_PERSON_VIOLATION = "first_person_violation"


class Severity(Enum):
    CRITICAL = "critical"
    NON_CRITICAL = "non_critical"


class Direction(Enum):
    EN_TO_ES = "en_to_es"
    ES_TO_EN = "es_to_en"


class SpeakerRole(Enum):
    CLINICIAN = "clinician"
    PATIENT = "patient"


class Provenance(Enum):
    EXTRACTOR = "extractor"
    GRADER = "grader"
    HUMAN = "human"


class Origin(Enum):
    AGENT_GENERATED = "agent_generated"
    SCRIPTED_FALLBACK = "scripted_fallback"
    FIXTURE = "fixture"


class TurnStatus(Enum):
    COMPLETE = "complete"
    ABANDONED = "abandoned"
    CAPTURE_LOST = "capture_lost"
    BLOB_CORRUPT = "blob_corrupt"


class ScoreStatus(Enum):
    COMPLETE = "complete"
    EXTRACTOR_ONLY = "extractor_only"
    PARTIAL = "partial"
    FAILED = "failed"


class ReviewState(Enum):
    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    SIGNED = "signed"


class SessionEventType(Enum):
    TURN_STARTED = "turn_started"
    PARTIAL_TRANSCRIPT = "partial_transcript"
    TURN_COMMITTED = "turn_committed"
    SCORE_READY = "score_ready"
    COACH_INTERJECTION = "coach_interjection"
    SESSION_ENDED = "session_ended"


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Finding:
    """The atom of scoring output. misc/docs/06-scoring-engine.md"""

    type: ErrorType
    severity: Severity
    note: str
    provenance: Provenance
    source_span: Span | None = None
    rendering_span: Span | None = None
    extractor_name: str | None = None
    confidence: float | None = None  # grader only; extractors do not guess


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """One interpreted turn. misc/docs/03-system-architecture.md, 11-backend-api.md"""

    turn_id: str
    session_id: str
    direction: Direction
    source_utterance: str
    source_lang: str
    rendering_transcript: str
    audio_blob_hash: str | None = None
    timestamps: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScoreRecord:
    """The scorer's output for a turn. misc/docs/06-scoring-engine.md, 08-evals.md"""

    turn_id: str
    findings: tuple[Finding, ...]
    extractor_findings: tuple[Finding, ...]
    model_findings: tuple[Finding, ...]
    grader_prompt_version: str
    model_versions: dict[str, str]
    seed: int
    status: ScoreStatus = ScoreStatus.COMPLETE


@dataclass(frozen=True, slots=True)
class Medication:
    name: str
    dose: str
    unit: str
    route: str
    frequency_per_day: int
    duration: str


@dataclass(frozen=True, slots=True)
class SymptomTimelineEntry:
    offset: str
    symptom: str


@dataclass(frozen=True, slots=True)
class Allergy:
    substance: str


@dataclass(frozen=True, slots=True)
class ClinicalState:
    """Drives the patient agent. misc/docs/07-data-and-scenarios.md"""

    condition: str
    medications: tuple[Medication, ...]
    symptom_timeline: tuple[SymptomTimelineEntry, ...]
    allergies: tuple[Allergy, ...]
    emotional_state: str
    health_literacy: str
    language_variety: str
    onset: str


@dataclass(frozen=True, slots=True)
class TermManifestEntry:
    term_id: str
    kind: str
    en: str
    es: str
    critical: bool
    acceptable_renderings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScenarioReview:
    status: str
    reviewer: str | None = None


@dataclass(frozen=True, slots=True)
class ScenarioRecord:
    """misc/docs/07-data-and-scenarios.md"""

    scenario_id: str
    schema_version: str
    clinical_state: ClinicalState
    difficulty: dict[str, object]
    term_manifest: tuple[TermManifestEntry, ...]
    review: ScenarioReview


@dataclass(frozen=True, slots=True)
class SessionEvent:
    """Real-time channel envelope. misc/docs/11-backend-api.md"""

    type: SessionEventType
    session_id: str
    seq: int
    payload: dict[str, object] = field(default_factory=dict)
