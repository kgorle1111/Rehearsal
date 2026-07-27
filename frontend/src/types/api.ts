// 10-frontend-spec.md §5.5 notes this should be generated from backend Pydantic models via
// `make frontend-types`. WS-API has not landed yet (BUILD.md WS8 scope note), so this is
// hand-written directly off misc/docs/11-backend-api.md §4-§6 and will be replaced by the
// generator once the backend ships. ponytail: hand-authored ceiling, regenerate when WS-API lands.

export type SessionState =
  | 'configuring'
  | 'armed'
  | 'source_speaking'
  | 'awaiting_rendering'
  | 'rendering_capturing'
  | 'turn_closing'
  | 'paused'
  | 'debrief'
  | 'review'
  | 'complete'
  | 'aborted'
  | 'failed';

export type Direction = 'en->es' | 'es->en';
export type Speaker = 'clinician' | 'patient';
export type Severity = 'critical' | 'non_critical';
export type DegradeLevel = 0 | 1 | 2 | 3 | 4 | 5;

export type ErrorKind =
  | 'omission'
  | 'addition'
  | 'substitution'
  | 'distortion'
  | 'editorialization'
  | 'role_exchange'
  | 'register_shift'
  | 'false_fluency'
  | 'first_person_violation';

export interface Finding {
  finding_id: number;
  kind: ErrorKind;
  severity: Severity;
  origin: 'extractor' | 'model';
  src_start: number | null;
  src_end: number | null;
  span_start: number | null;
  span_end: number | null;
  confidence: number;
  note: string;
  overruled?: boolean;
}

export interface VerdictView {
  status: 'complete' | 'partial' | 'grader_unavailable';
  nCritical: number;
  nNonCritical: number;
  findings: Finding[];
  notAssessed: ErrorKind[];
}

export interface TextBlock {
  text: string;
  lang: 'en' | 'es';
}

export interface TurnView {
  index: number;
  speaker: Speaker;
  direction: Direction;
  source: TextBlock | null;
  rendering: TextBlock | null;
  partial: boolean;
  verdict: VerdictView | null;
  audioSha: string | null;
}

export interface Coach {
  turnIndex: number;
  kind: string;
  text: string;
  priority: string;
}

export interface SessionView {
  sessionId: string;
  state: SessionState;
  mode: 'practice' | 'assessment';
  scenario: { id: string; title: string; setting: string };
  turnIndex: number;
  turns: TurnView[];
  degrade: { level: DegradeLevel; max: DegradeLevel; reason: string | null };
  pendingCoach: Coach | null;
  lastSeq: number;
  textMode: boolean;
  unknownKinds: Record<string, number>;
}

export function emptySessionView(sessionId: string): SessionView {
  return {
    sessionId,
    state: 'configuring',
    mode: 'practice',
    scenario: { id: '', title: '', setting: '' },
    turnIndex: -1,
    turns: [],
    degrade: { level: 0, max: 0, reason: null },
    pendingCoach: null,
    lastSeq: 0,
    textMode: false,
    unknownKinds: {},
  };
}

// -- Session report (11-backend-api.md §4.5) --

export interface CoverageBlock {
  turnsTotal: number;
  turnsScoredFull: number;
  turnsScoredExtractorOnly: number;
  turnsUnscored: number;
  unscoredTurnIndices: number[];
  notAssessedCategories: ErrorKind[];
}

export interface SessionReport {
  sessionId: string;
  state: SessionState;
  degradeMax: DegradeLevel;
  coverage: CoverageBlock;
  totals: { critical: number; nonCritical: number; cleanTurns: number };
  turns: TurnView[];
  grader: { model: string; promptVer: string } | null;
  confidence: { measured: boolean; kappa: number | null; criticalRecall: number | null };
}
