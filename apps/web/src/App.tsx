import { useState, type ChangeEvent } from 'react';
import './App.css';

type Screen = 'login' | 'fleet' | 'workspace';
type WorkspaceTab = 'mission' | 'run' | 'chat' | 'context';
type ProjectTone = 'active' | 'sleeping' | 'shipping';
type SignalTone = 'ready' | 'warning' | 'danger' | 'neutral';
type WorkKind = 'task' | 'story' | 'bug' | 'epic';

interface QuotaWindow {
  label: string;
  state: string;
  detail: string;
  burn: number;
  tone: SignalTone;
}

interface Project {
  id: string;
  name: string;
  tone: ProjectTone;
  mission: string;
  engine: string;
  surface: string;
  nextWake: string;
  lastPayload: string;
  readiness: string;
}

interface PillarCard {
  label: string;
  metric: string;
  detail: string;
  tone: SignalTone;
}

interface TimelineItem {
  time: string;
  title: string;
  detail: string;
  tone: SignalTone;
}

interface TerminalLine {
  kind: 'prompt' | 'log' | 'warn' | 'success';
  text: string;
}

interface DetectionItem {
  label: string;
  detail: string;
  tone: SignalTone;
}

interface DocumentItem {
  name: string;
  tag: string;
  summary: string;
  chunks: number;
  status: string;
}

interface DecisionItem {
  title: string;
  tag: string;
  note: string;
}

interface MemoryNote {
  id: number;
  title: string;
  tag: string;
  body: string;
}

interface ChatMessage {
  id: number;
  role: 'operator' | 'jr';
  text: string;
}

interface PayloadItem {
  title: string;
  state: string;
  detail: string;
  artifacts: string[];
}

interface AccessItem {
  label: string;
  status: string;
  detail: string;
  tone: SignalTone;
}

interface SurfaceItem {
  name: string;
  detail: string;
  tone: SignalTone;
}

interface BoardItem {
  kind: WorkKind;
  title: string;
  meta: string;
}

interface BoardColumn {
  title: string;
  items: BoardItem[];
}

interface ContextCluster {
  label: string;
  links: number;
  source: string;
}

interface RecallItem {
  title: string;
  source: string;
  score: string;
  excerpt: string;
}

interface ContextChunk {
  title: string;
  excerpt: string;
  tags: string[];
}

interface WorkspaceModel {
  strapline: string;
  objective: string;
  outcome: string;
  constraints: string[];
  boardColumns: BoardColumn[];
  pillars: PillarCard[];
  scheduler: TimelineItem[];
  signals: TimelineItem[];
  runTimeline: TimelineItem[];
  terminalLines: TerminalLine[];
  detections: DetectionItem[];
  actionQueue: string[];
  documents: DocumentItem[];
  decisions: DecisionItem[];
  linkedContexts: ContextCluster[];
  activeRetrieval: RecallItem[];
  chunkLibrary: Record<string, ContextChunk[]>;
  graphClusters: string[];
  memoryNotes: MemoryNote[];
  payloads: PayloadItem[];
  access: AccessItem[];
  surfaces: SurfaceItem[];
}

const workspaceTabs: Array<{ id: WorkspaceTab; label: string; copy: string }> = [
  { id: 'mission', label: 'Mission', copy: 'Board and flow' },
  { id: 'run', label: 'Run', copy: 'Live monitoring' },
  { id: 'chat', label: 'Chat', copy: 'Talk to the agent' },
  { id: 'context', label: 'Context', copy: 'PRD, notes, decisions' },
];

const quotaWindows: QuotaWindow[] = [
  {
    label: 'Gemini Pro daily window',
    state: 'Cooling down',
    detail: '500 / 500 actions consumed. Wake signal in 02h 45m.',
    burn: 100,
    tone: 'danger',
  },
  {
    label: 'Claude Code cycle',
    state: 'Near limit',
    detail: '45 / 50 messages used. Reserve for code review only.',
    burn: 90,
    tone: 'warning',
  },
  {
    label: 'OpenCode Minimax',
    state: 'Primary lane',
    detail: 'Healthy budget. Current workspace routed here.',
    burn: 36,
    tone: 'ready',
  },
  {
    label: 'OpenCode GLM fallback',
    state: 'Standby',
    detail: 'Cold lane held for retries and low-risk tasks.',
    burn: 12,
    tone: 'neutral',
  },
];

const projectCatalog: Project[] = [
  {
    id: 'atlas',
    name: 'Atlas Launchpad',
    tone: 'active',
    mission: 'Build the launch surface from the PRD and prepare a proof-ready delivery.',
    engine: 'OpenCode / Minimax',
    surface: 'Web + API',
    nextWake: 'Live now',
    lastPayload: 'Staging proof packet 12 min ago',
    readiness: '4 blockers resolved, 1 gate open',
  },
  {
    id: 'relay',
    name: 'Relay Desk',
    tone: 'sleeping',
    mission: 'Resume an internal service flow after provider limits reset.',
    engine: 'Gemini Pro cooldown',
    surface: 'Desktop + notifications',
    nextWake: '02h 45m',
    lastPayload: 'Needs staging secret before resume',
    readiness: 'Sleeping safely with resume checkpoint',
  },
  {
    id: 'foundry',
    name: 'Foundry Ops',
    tone: 'shipping',
    mission: 'Prepare a verified handoff with artifacts and rollback notes.',
    engine: 'Claude Code validation lane',
    surface: 'API + deploy target',
    nextWake: 'Awaiting approval',
    lastPayload: 'Production proof packet queued',
    readiness: 'Delivery bundle complete',
  },
];

const globalSignals: TimelineItem[] = [
  {
    time: '14:32',
    title: 'Atlas Launchpad switched engines',
    detail: 'Gemini window expired. Control moved to OpenCode Minimax without operator input.',
    tone: 'warning',
  },
  {
    time: '14:11',
    title: 'Foundry Ops sealed a release packet',
    detail: 'Proof screenshots, logs, and rollback notes attached to the delivery bundle.',
    tone: 'ready',
  },
  {
    time: '13:56',
    title: 'Relay Desk entered cooldown mode',
    detail: 'Loop paused after quota event. Resume checkpoint and wake schedule persisted.',
    tone: 'neutral',
  },
];

const workspaceData: Record<string, WorkspaceModel> = {
  atlas: {
    strapline: 'Runs keep going even when the cockpit is closed.',
    objective: 'Build the launch flow from the PRD, keep the run visible, and prepare proof before handoff.',
    outcome: 'A working surface, a clear run history, and a proof packet for review.',
    constraints: [
      'Keep the run headless by default.',
      'Record engine switches, wake schedules, and deploy steps.',
      'Treat the cockpit as a mirror of runtime state.',
    ],
    boardColumns: [
      {
        title: 'Backlog',
        items: [
          { kind: 'epic', title: 'Launch page v1', meta: '4 stories' },
          { kind: 'story', title: 'Pricing section', meta: 'Ready' },
        ],
      },
      {
        title: 'In progress',
        items: [
          { kind: 'story', title: 'Hero and CTA flow', meta: 'OpenCode' },
          { kind: 'task', title: 'Shadow deploy replay', meta: 'Running' },
        ],
      },
      {
        title: 'Review',
        items: [{ kind: 'bug', title: 'Footer proof missing', meta: 'Needs capture' }],
      },
      {
        title: 'Done',
        items: [{ kind: 'task', title: 'Provider route switch', meta: 'Logged' }],
      },
    ],
    pillars: [
      {
        label: 'Reflex engine',
        metric: 'OpenCode Minimax',
        detail: 'Primary route after the last Gemini cooldown event.',
        tone: 'ready',
      },
      {
        label: 'Body execution',
        metric: '3 surfaces attached',
        detail: 'Browser lane, deploy shell, and scheduler are all reporting heartbeat.',
        tone: 'ready',
      },
      {
        label: 'Mind continuity',
        metric: '18 recalled facts',
        detail: 'Decision log and project memory are loaded into the live context plan.',
        tone: 'neutral',
      },
    ],
    scheduler: [
      {
        time: 'Now',
        title: 'Active execution lane',
        detail: 'OpenCode Minimax is holding the live build loop.',
        tone: 'ready',
      },
      {
        time: '02h 45m',
        title: 'Gemini window resets',
        detail: 'Retry lane becomes available for low-cost exploration.',
        tone: 'warning',
      },
      {
        time: '04:00 UTC',
        title: 'Quiet shipping window',
        detail: 'Deployment proofs can be generated without alert noise.',
        tone: 'neutral',
      },
    ],
    signals: [
      {
        time: '14:32',
        title: 'Engine policy triggered',
        detail: 'Automatic route change after a quota exhaustion event.',
        tone: 'warning',
      },
      {
        time: '14:28',
        title: 'Proof capture completed',
        detail: 'Viewport screenshots and event log snapshots sealed for review.',
        tone: 'ready',
      },
      {
        time: '14:07',
        title: 'Manual input not required',
        detail: 'The run kept moving because all policy gates stayed green.',
        tone: 'neutral',
      },
    ],
    runTimeline: [
      {
        time: '14:32',
        title: 'Route workspace to Minimax',
        detail: 'Budget-aware switch completed without losing run memory.',
        tone: 'warning',
      },
      {
        time: '14:20',
        title: 'Generate landing skeleton',
        detail: 'Primary layout, copy blocks, and CTA hierarchy landed in the shadow environment.',
        tone: 'ready',
      },
      {
        time: '14:12',
        title: 'Replay design constraints',
        detail: 'Brand limits, deployment policy, and proof rules pulled into the run plan.',
        tone: 'neutral',
      },
      {
        time: '13:54',
        title: 'Queue staging verification',
        detail: 'Artifact capture requested before any external release note is drafted.',
        tone: 'ready',
      },
    ],
    terminalLines: [
      { kind: 'prompt', text: 'selffork@forge:~$ opencode --model minimax' },
      { kind: 'log', text: '[orchestrator] resumed workspace atlas after provider cooldown event' },
      { kind: 'log', text: '[planner] generated launch-page backlog from PRD and policy ledger' },
      { kind: 'warn', text: '[router] gemini-pro daily quota exhausted, moving exploration lane to standby' },
      { kind: 'success', text: '[proof] viewport captures, deploy checks, and rollback notes archived' },
    ],
    detections: [
      { label: 'Primary CTA visible', detail: '98.1% confidence on target button group.', tone: 'ready' },
      { label: 'Pricing rail aligned', detail: 'Hero to pricing transition validated in responsive mode.', tone: 'ready' },
      { label: 'Footer proof pending', detail: 'Final screenshot will be captured after copy freeze.', tone: 'warning' },
    ],
    actionQueue: [
      'Seal mobile screenshot set',
      'Replay deploy on shadow target',
      'Draft operator-facing payload summary',
    ],
    documents: [
      {
        name: 'Launch_PRD.md',
        tag: 'Mission',
        summary: 'Source brief for the launch flow, conversion goals, and proof expectations.',
        chunks: 18,
        status: 'Indexed',
      },
      {
        name: 'Decision_Ledger.md',
        tag: 'Continuity',
        summary: 'Captured non-negotiables for autonomy, delivery gates, and notification policy.',
        chunks: 9,
        status: 'Indexed',
      },
      {
        name: 'Payload_Rubric.md',
        tag: 'Delivery',
        summary: 'What must exist before the run may call itself done.',
        chunks: 6,
        status: 'Indexed',
      },
    ],
    decisions: [
      {
        title: 'Headless core stays primary',
        tag: 'Architecture',
        note: 'The cockpit mirrors state but never owns execution or orchestration.',
      },
      {
        title: 'Quota changes are visible events',
        tag: 'Scheduler',
        note: 'Provider exhaustion becomes a timeline event instead of silent failure.',
      },
      {
        title: 'Proof before praise',
        tag: 'Delivery',
        note: 'Every release note needs artifacts, checks, and rollback data attached.',
      },
    ],
    linkedContexts: [
      { label: 'launch flow', links: 6, source: 'Launch_PRD.md' },
      { label: 'quota routing', links: 4, source: 'Decision_Ledger.md' },
      { label: 'proof rubric', links: 5, source: 'Payload_Rubric.md' },
      { label: 'shadow deploy', links: 3, source: 'Launch_PRD.md' },
    ],
    activeRetrieval: [
      {
        title: 'Hero flow constraints',
        source: 'Launch_PRD.md',
        score: '0.92',
        excerpt: 'Keep the first screen simple, conversion-first, and easy to verify in screenshots.',
      },
      {
        title: 'Quota switch rule',
        source: 'Decision_Ledger.md',
        score: '0.88',
        excerpt: 'Provider exhaustion should be visible and should trigger a clean route change.',
      },
      {
        title: 'Proof requirement',
        source: 'Payload_Rubric.md',
        score: '0.84',
        excerpt: 'A run is only complete after screenshots, checks, and rollback notes are attached.',
      },
    ],
    chunkLibrary: {
      'Launch_PRD.md': [
        {
          title: 'Chunk 01 - scope',
          excerpt: 'Landing page should stay simple, conversion-first, and easy to verify in screenshots.',
          tags: ['hero', 'scope'],
        },
        {
          title: 'Chunk 02 - structure',
          excerpt: 'The flow moves from hero to proof to pricing without unnecessary branches.',
          tags: ['layout', 'pricing'],
        },
        {
          title: 'Chunk 03 - delivery',
          excerpt: 'Final handoff includes preview, artifacts, and a readable summary for the operator.',
          tags: ['handoff', 'proof'],
        },
      ],
      'Decision_Ledger.md': [
        {
          title: 'Chunk 01 - routing',
          excerpt: 'Quota changes trigger visible route switches instead of silent failure.',
          tags: ['quota', 'routing'],
        },
        {
          title: 'Chunk 02 - autonomy',
          excerpt: 'The cockpit mirrors runtime state but never owns execution.',
          tags: ['autonomy', 'policy'],
        },
      ],
      'Payload_Rubric.md': [
        {
          title: 'Chunk 01 - proof gate',
          excerpt: 'A task is not done until screenshots, checks, and rollback notes exist together.',
          tags: ['proof', 'done'],
        },
      ],
    },
    graphClusters: ['launch flow', 'quota routing', 'payload rubric', 'shadow deploy', 'notification policy'],
    memoryNotes: [
      {
        id: 1,
        title: 'Proof threshold',
        tag: 'delivery',
        body: 'A run is only complete when screenshots, checks, and rollback notes are bundled together.',
      },
      {
        id: 2,
        title: 'Escalation style',
        tag: 'policy',
        body: 'Only request operator attention when access, billing, or production safety is involved.',
      },
      {
        id: 3,
        title: 'Layout bias',
        tag: 'design',
        body: 'Prefer structured launch pages with distinct proof areas over generic card stacks.',
      },
    ],
    payloads: [
      {
        title: 'Staging proof packet',
        state: 'Ready',
        detail: 'Viewport captures, build log, route checks, and rollback notes collected in one bundle.',
        artifacts: ['desktop viewport', 'mobile viewport', 'build checksum', 'rollback note'],
      },
      {
        title: 'Operator handoff brief',
        state: 'Drafted',
        detail: 'Summarizes what changed, why it changed, and what remains blocked.',
        artifacts: ['delta summary', 'risk note', 'next wake window'],
      },
    ],
    access: [
      {
        label: 'Workspace secrets',
        status: '1 gated secret pending',
        detail: 'Delivery may continue; production release remains locked behind manual approval.',
        tone: 'warning',
      },
      {
        label: 'Scheduler policy',
        status: 'Guarded autonomy',
        detail: 'Silent retries allowed. Production actions still require an operator handoff.',
        tone: 'ready',
      },
      {
        label: 'Emergency controls',
        status: 'Instant kill path ready',
        detail: 'All live lanes can be paused without losing checkpoint history.',
        tone: 'danger',
      },
    ],
    surfaces: [
      { name: 'Browser lane', detail: 'Responsive viewport capture and visual checks.', tone: 'ready' },
      { name: 'Deploy shell', detail: 'Shadow target connected and replayable.', tone: 'ready' },
      { name: 'Notification relay', detail: 'Signals queued for handoff and done-state updates.', tone: 'neutral' },
    ],
  },
  relay: {
    strapline: 'Sleeping should still feel under control.',
    objective: 'Resume a paused service flow cleanly after provider windows reopen.',
    outcome: 'Continue from the saved checkpoint without rebuilding context by hand.',
    constraints: [
      'Keep cooldown logic visible and deterministic.',
      'Do not reopen blocked lanes automatically.',
      'Keep a clear wake-up trail after sleep.',
    ],
    boardColumns: [
      {
        title: 'Backlog',
        items: [{ kind: 'epic', title: 'Desk flow setup', meta: '3 stories' }],
      },
      {
        title: 'In progress',
        items: [{ kind: 'task', title: 'Cooldown checkpoint', meta: 'Paused' }],
      },
      {
        title: 'Review',
        items: [{ kind: 'bug', title: 'Credential gate', meta: 'Blocked' }],
      },
      {
        title: 'Done',
        items: [{ kind: 'story', title: 'Wake schedule saved', meta: 'Stored' }],
      },
    ],
    pillars: [
      {
        label: 'Reflex engine',
        metric: 'Cooldown state',
        detail: 'Route selection is paused until the daily window resets.',
        tone: 'warning',
      },
      {
        label: 'Body execution',
        metric: 'Checkpoint parked',
        detail: 'Terminal session and task queue are stored and replayable.',
        tone: 'neutral',
      },
      {
        label: 'Mind continuity',
        metric: 'Wake packet ready',
        detail: 'Recall summary prepared for the next autonomous loop.',
        tone: 'ready',
      },
    ],
    scheduler: [
      { time: '02h 45m', title: 'Primary wake signal', detail: 'Gemini lane becomes available again.', tone: 'warning' },
      { time: '03h 00m', title: 'Resume backlog replay', detail: 'Task queue rehydrates before model output begins.', tone: 'neutral' },
      { time: '03h 05m', title: 'Health ping', detail: 'A confirmation event is emitted before new actions run.', tone: 'ready' },
    ],
    signals: [
      { time: '13:56', title: 'Cooldown checkpoint saved', detail: 'Secrets, backlog, and run state persisted before sleep.', tone: 'neutral' },
      { time: '13:55', title: 'Secret request deferred', detail: 'Run is blocked cleanly without spamming the operator lane.', tone: 'warning' },
      { time: '13:52', title: 'Quota threshold breached', detail: 'Provider lockout detected from the active session stream.', tone: 'danger' },
    ],
    runTimeline: [
      { time: '13:56', title: 'Pause active lane', detail: 'Run entered safe sleep after writing checkpoint metadata.', tone: 'neutral' },
      { time: '13:49', title: 'Draft service triage rules', detail: 'Escalation tiers and ownership flows generated from PRD.', tone: 'ready' },
      { time: '13:37', title: 'Replay previous desk incidents', detail: 'Memory lane loaded the last resolution patterns into plan context.', tone: 'ready' },
    ],
    terminalLines: [
      { kind: 'prompt', text: 'selffork@forge:~$ gemini-cli resume relay-desk' },
      { kind: 'warn', text: '[router] provider quota exhausted, initiating cooldown protocol' },
      { kind: 'log', text: '[scheduler] wake task registered for 02h 45m from now' },
      { kind: 'success', text: '[checkpoint] task queue, memory summary, and secrets state persisted' },
    ],
    detections: [
      { label: 'Desktop modal tree stored', detail: 'UI snapshot archived for resume consistency checks.', tone: 'neutral' },
      { label: 'Access gate unresolved', detail: 'One credential is still intentionally missing.', tone: 'warning' },
    ],
    actionQueue: ['Wait for wake signal', 'Replay checkpoint', 'Resume triage wizard'],
    documents: [
      { name: 'Desk_PRD.md', tag: 'Mission', summary: 'Defines intake, escalation, and ownership flow.', chunks: 12, status: 'Indexed' },
      {
        name: 'Cooldown_Policy.md',
        tag: 'Scheduler',
        summary: 'Explains when the loop sleeps and how it resumes.',
        chunks: 7,
        status: 'Indexed',
      },
    ],
    decisions: [
      { title: 'Sleep state is explicit', tag: 'Runtime', note: 'Cooldown is a first-class state, not an error message.' },
      { title: 'One secret, one gate', tag: 'Access', note: 'Blocked credentials freeze only the affected lane.' },
    ],
    linkedContexts: [
      { label: 'wake packet', links: 4, source: 'Cooldown_Policy.md' },
      { label: 'desk triage', links: 5, source: 'Desk_PRD.md' },
      { label: 'credential gate', links: 3, source: 'Cooldown_Policy.md' },
    ],
    activeRetrieval: [
      {
        title: 'Cooldown resume rule',
        source: 'Cooldown_Policy.md',
        score: '0.94',
        excerpt: 'Reload checkpoint summary before generation resumes after sleep.',
      },
      {
        title: 'Escalation ownership',
        source: 'Desk_PRD.md',
        score: '0.85',
        excerpt: 'Credential gates should block only the affected release lane.',
      },
    ],
    chunkLibrary: {
      'Desk_PRD.md': [
        {
          title: 'Chunk 01 - intake',
          excerpt: 'Incoming requests are triaged by urgency, owner, and blocked dependencies.',
          tags: ['triage', 'intake'],
        },
        {
          title: 'Chunk 02 - ownership',
          excerpt: 'Only the blocked lane should stop; planning can continue safely around it.',
          tags: ['ownership', 'blocked'],
        },
      ],
      'Cooldown_Policy.md': [
        {
          title: 'Chunk 01 - sleep',
          excerpt: 'Checkpoint summary must be restored before the first token after wake.',
          tags: ['sleep', 'resume'],
        },
        {
          title: 'Chunk 02 - wake signal',
          excerpt: 'Wake windows are explicit scheduled events, not implied retries.',
          tags: ['wake', 'scheduler'],
        },
      ],
    },
    graphClusters: ['wake packet', 'desk triage', 'quota lockout', 'credential gate'],
    memoryNotes: [
      { id: 4, title: 'Resume rule', tag: 'policy', body: 'Reload the checkpoint summary before any new generation begins.' },
      { id: 5, title: 'Notification policy', tag: 'ops', body: 'Wake notices are concise and only fire on state transitions.' },
    ],
    payloads: [
      {
        title: 'Sleep packet',
        state: 'Stored',
        detail: 'Contains wake schedule, pending gates, and context recall summary.',
        artifacts: ['wake time', 'checkpoint hash', 'blocked scope'],
      },
    ],
    access: [
      {
        label: 'Credential gate',
        status: 'Awaiting operator input',
        detail: 'Only the release lane is blocked. Planning and recall remain safe.',
        tone: 'warning',
      },
      {
        label: 'Sleep policy',
        status: 'Deterministic',
        detail: 'Wake logic is persisted as a scheduled event with replay metadata.',
        tone: 'ready',
      },
    ],
    surfaces: [
      { name: 'Desktop lane', detail: 'Paused with modal snapshot and queue state.', tone: 'neutral' },
      { name: 'Notification relay', detail: 'Wake alert prepared for the next state change.', tone: 'ready' },
    ],
  },
  foundry: {
    strapline: 'Delivery should be easy to verify.',
    objective: 'Prepare the final handoff with proof artifacts and a short summary of changes.',
    outcome: 'A packet that shows the run is done without digging through raw logs.',
    constraints: [
      'All proof artifacts must exist before the packet is complete.',
      'Rollback and risk notes travel with the release summary.',
      'Do not trigger production actions automatically.',
    ],
    boardColumns: [
      {
        title: 'Backlog',
        items: [{ kind: 'story', title: 'Operator handoff note', meta: 'Queued' }],
      },
      {
        title: 'In progress',
        items: [{ kind: 'task', title: 'Assemble proof packet', meta: 'Claude lane' }],
      },
      {
        title: 'Review',
        items: [{ kind: 'bug', title: 'Approval gate pending', meta: 'Manual' }],
      },
      {
        title: 'Done',
        items: [{ kind: 'task', title: 'Shadow replay', meta: 'Passed' }],
      },
    ],
    pillars: [
      { label: 'Reflex engine', metric: 'Claude validation lane', detail: 'Final review route favors precision over speed.', tone: 'ready' },
      { label: 'Body execution', metric: 'Deploy shell ready', detail: 'Shadow replay finished. Production path remains gated.', tone: 'warning' },
      { label: 'Mind continuity', metric: 'Payload rubric loaded', detail: 'Proof expectations are part of the final summary pass.', tone: 'neutral' },
    ],
    scheduler: [
      { time: 'Now', title: 'Packet assembly', detail: 'Proof assets and release narrative are being sealed.', tone: 'ready' },
      { time: 'Manual gate', title: 'Production approval', detail: 'No automatic deploy path is open.', tone: 'danger' },
    ],
    signals: [
      { time: '14:11', title: 'Release packet drafted', detail: 'Verification set attached to the final narrative.', tone: 'ready' },
      { time: '14:02', title: 'Rollback notes refreshed', detail: 'Every artifact now has a corresponding revert hint.', tone: 'neutral' },
    ],
    runTimeline: [
      { time: '14:11', title: 'Seal proof packet', detail: 'Release-ready bundle assembled for operator review.', tone: 'ready' },
      { time: '13:58', title: 'Replay deploy in shadow lane', detail: 'Verification replay finished with clean system checks.', tone: 'ready' },
      { time: '13:41', title: 'Capture risk notes', detail: 'Known limits and safe follow-up steps attached to packet.', tone: 'warning' },
    ],
    terminalLines: [
      { kind: 'prompt', text: 'selffork@forge:~$ claude code validate foundry-ops' },
      { kind: 'log', text: '[validator] deploy replay succeeded on shadow target' },
      { kind: 'success', text: '[payload] proof packet assembled with screenshots, logs, and rollback plan' },
      { kind: 'warn', text: '[gate] production approval remains manual by policy' },
    ],
    detections: [
      { label: 'Deploy confirmation visible', detail: 'Final success state captured in shell output.', tone: 'ready' },
      { label: 'Production gate visible', detail: 'Manual approval reminder pinned in the packet footer.', tone: 'warning' },
    ],
    actionQueue: ['Review payload packet', 'Approve or reject release lane'],
    documents: [
      { name: 'Release_Rubric.md', tag: 'Delivery', summary: 'Definition of done for handoff packets.', chunks: 8, status: 'Indexed' },
      { name: 'Rollback_Guide.md', tag: 'Safety', summary: 'What to do if the operator rejects the release.', chunks: 5, status: 'Indexed' },
    ],
    decisions: [
      { title: 'Production stays human-gated', tag: 'Safety', note: 'Autonomy may prepare the packet but never bypass approval.' },
      { title: 'Narrative follows proof', tag: 'Delivery', note: 'Human-facing summaries are generated only after checks succeed.' },
    ],
    linkedContexts: [
      { label: 'release packet', links: 5, source: 'Release_Rubric.md' },
      { label: 'rollback path', links: 3, source: 'Rollback_Guide.md' },
      { label: 'approval gate', links: 4, source: 'Release_Rubric.md' },
    ],
    activeRetrieval: [
      {
        title: 'Definition of done',
        source: 'Release_Rubric.md',
        score: '0.91',
        excerpt: 'Proof packets must include checks, screenshots, and a short operator summary.',
      },
      {
        title: 'Rollback note',
        source: 'Rollback_Guide.md',
        score: '0.83',
        excerpt: 'Approval remains manual and the reverse path must stay attached to the packet.',
      },
    ],
    chunkLibrary: {
      'Release_Rubric.md': [
        {
          title: 'Chunk 01 - handoff',
          excerpt: 'The packet needs proof assets, checks, and a short operator-facing summary.',
          tags: ['handoff', 'summary'],
        },
        {
          title: 'Chunk 02 - review gate',
          excerpt: 'Approval stays manual even when the packet is complete.',
          tags: ['approval', 'gate'],
        },
      ],
      'Rollback_Guide.md': [
        {
          title: 'Chunk 01 - reverse path',
          excerpt: 'Every release note carries the rollback path next to the forward path.',
          tags: ['rollback', 'safety'],
        },
      ],
    },
    graphClusters: ['release packet', 'shadow replay', 'rollback notes', 'approval gate'],
    memoryNotes: [
      { id: 6, title: 'Approval style', tag: 'ops', body: 'The last mile is a packet review, not a blind trust exercise.' },
      { id: 7, title: 'Rollback discipline', tag: 'safety', body: 'Every release summary must carry the reverse path next to the forward path.' },
    ],
    payloads: [
      {
        title: 'Production proof packet',
        state: 'Queued for review',
        detail: 'Contains final screenshots, shadow replay transcript, and rollback guidance.',
        artifacts: ['success transcript', 'artifact digest', 'rollback checklist'],
      },
      {
        title: 'Operator summary note',
        state: 'Ready',
        detail: 'One-screen narrative of what changed and why the system considers it safe.',
        artifacts: ['change summary', 'residual risk', 'approval prompt'],
      },
    ],
    access: [
      {
        label: 'Approval gate',
        status: 'Manual only',
        detail: 'The final production lane cannot be triggered from autonomy alone.',
        tone: 'danger',
      },
      {
        label: 'Proof archive',
        status: 'Immutable',
        detail: 'Release packet is sealed and replayable.',
        tone: 'ready',
      },
    ],
    surfaces: [
      { name: 'Shadow deploy lane', detail: 'Replay complete with clean checks.', tone: 'ready' },
      { name: 'Approval inbox', detail: 'Waiting for operator decision.', tone: 'warning' },
    ],
  },
};

const initialNotes = Object.fromEntries(
  Object.entries(workspaceData).map(([workspaceId, model]) => [workspaceId, model.memoryNotes]),
) as Record<string, MemoryNote[]>;

const initialDocuments = Object.fromEntries(
  Object.entries(workspaceData).map(([workspaceId, model]) => [workspaceId, model.documents]),
) as Record<string, DocumentItem[]>;

const initialChats: Record<string, ChatMessage[]> = {
  atlas: [
    { id: 1, role: 'operator', text: 'Keep the landing flow simple and ship with proof.' },
    { id: 2, role: 'jr', text: 'Tracking the live session. Board and run view will stay updated.' },
  ],
  relay: [
    { id: 3, role: 'operator', text: 'Wake this run cleanly after limits reset.' },
    { id: 4, role: 'jr', text: 'Checkpoint is parked. I will resume on the next window.' },
  ],
  foundry: [
    { id: 5, role: 'operator', text: 'Prepare the handoff and keep production gated.' },
    { id: 6, role: 'jr', text: 'Understood. I am packaging proofs and keeping approval manual.' },
  ],
};

const toneClass = (tone: SignalTone) => `tone-${tone}`;
const projectToneClass = (tone: ProjectTone) => `project-${tone}`;

function App() {
  const [screen, setScreen] = useState<Screen>('login');
  const [selectedProjectId, setSelectedProjectId] = useState<string>(projectCatalog[0].id);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('mission');
  const [focusedSourceName, setFocusedSourceName] = useState<string>('');
  const [draftNote, setDraftNote] = useState('');
  const [draftChat, setDraftChat] = useState('');
  const [projectNotes, setProjectNotes] = useState<Record<string, MemoryNote[]>>(initialNotes);
  const [projectDocuments, setProjectDocuments] = useState<Record<string, DocumentItem[]>>(initialDocuments);
  const [projectChats, setProjectChats] = useState<Record<string, ChatMessage[]>>(initialChats);

  const selectedProject = projectCatalog.find((project) => project.id === selectedProjectId) ?? projectCatalog[0];
  const selectedWorkspace = workspaceData[selectedProject.id];
  const activeNotes = projectNotes[selectedProject.id] ?? [];
  const activeDocuments = projectDocuments[selectedProject.id] ?? [];
  const activeChat = projectChats[selectedProject.id] ?? [];
  const selectedSourceName =
    activeDocuments.some((document) => document.name === focusedSourceName) ? focusedSourceName : activeDocuments[0]?.name ?? '';
  const selectedSource = activeDocuments.find((document) => document.name === selectedSourceName) ?? activeDocuments[0] ?? null;
  const selectedChunks = selectedSource ? selectedWorkspace.chunkLibrary[selectedSource.name] ?? [] : [];
  const previewChunks =
    selectedSource && selectedChunks.length === 0
      ? [
          {
            title: 'Chunk 01 - ingest',
            excerpt: selectedSource.summary,
            tags: ['uploaded', selectedSource.status.toLowerCase()],
          },
        ]
      : selectedChunks;

  const handleAuthenticate = () => setScreen('fleet');

  const handleOpenProject = (projectId: string) => {
    setSelectedProjectId(projectId);
    setActiveTab('mission');
    setFocusedSourceName('');
    setScreen('workspace');
  };

  const handleInjectNote = () => {
    const value = draftNote.trim();
    if (!value) {
      return;
    }

    const newNote: MemoryNote = {
      id: Date.now(),
      title: 'Fresh operator context',
      tag: 'live',
      body: value,
    };

    setProjectNotes((previous) => ({
      ...previous,
      [selectedProject.id]: [newNote, ...(previous[selectedProject.id] ?? [])],
    }));
    setDraftNote('');
  };

  const handleUploadDocuments = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) {
      return;
    }

    const uploaded = files.map((file) => ({
      name: file.name,
      tag: 'Upload',
      summary: 'Queued for chunking and linking.',
      chunks: Math.max(3, Math.ceil(file.size / 24000)),
      status: 'Indexing',
    }));

    setProjectDocuments((previous) => ({
      ...previous,
      [selectedProject.id]: [...uploaded, ...(previous[selectedProject.id] ?? [])],
    }));
    setFocusedSourceName(uploaded[0]?.name ?? '');

    event.target.value = '';
  };

  const handleFocusSource = (sourceName: string) => {
    setFocusedSourceName(sourceName);
    setActiveTab('context');
  };

  const handleSendChat = () => {
    const value = draftChat.trim();
    if (!value) {
      return;
    }

    const operatorMessage: ChatMessage = {
      id: Date.now(),
      role: 'operator',
      text: value,
    };

    const replyMap: Record<string, string> = {
      atlas: 'Got it. I will keep the session moving and reflect any state change here.',
      relay: 'Noted. I am watching the wake window and the saved checkpoint.',
      foundry: 'Understood. I will keep packaging the handoff and hold the approval gate.',
    };

    const jrMessage: ChatMessage = {
      id: Date.now() + 1,
      role: 'jr',
      text: replyMap[selectedProject.id] ?? 'Got it. I will track it in this workspace.',
    };

    setProjectChats((previous) => ({
      ...previous,
      [selectedProject.id]: [...(previous[selectedProject.id] ?? []), operatorMessage, jrMessage],
    }));
    setDraftChat('');
  };

  const renderLogin = () => (
    <div className="login-screen">
      <div className="login-shell">
        <section className="login-story panel panel-hero">
          <p className="eyebrow">Autonomous software operator</p>
          <h1>SelfFork</h1>
          <p className="hero-copy">See runs, tasks, context, and deliveries.</p>
        </section>

        <section className="login-panel panel">
          <p className="eyebrow">Operator access</p>
          <h2>Open cockpit</h2>

          <input className="auth-input" type="password" placeholder="Operator passphrase" />
          <button className="primary-button" type="button" onClick={handleAuthenticate}>
            Enter cockpit
          </button>
          <p className="micro-copy">Runs continue without this screen.</p>
        </section>
      </div>
    </div>
  );

  const renderFleet = () => (
    <div className="screen-shell">
      <section className="fleet-hero panel panel-hero banded">
        <div>
          <p className="eyebrow">Fleet</p>
          <h2>See what is running</h2>
          <p className="hero-copy compact">Runs, quotas, and proofs in one place.</p>
        </div>

        <div className="hero-pulse-grid">
          <div className="pulse-card">
            <span className="pulse-value">3</span>
            <span className="pulse-label">Workspaces</span>
          </div>
          <div className="pulse-card">
            <span className="pulse-value">2</span>
            <span className="pulse-label">Active or queued loops</span>
          </div>
          <div className="pulse-card">
            <span className="pulse-value">1</span>
            <span className="pulse-label">Manual production gate</span>
          </div>
        </div>
      </section>

      <section className="section-block">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Provider windows</p>
            <h3>Quota posture</h3>
          </div>
          <p className="section-note">Routing changes should be visible, not hidden.</p>
        </div>

        <div className="quota-grid">
          {quotaWindows.map((window) => (
            <article key={window.label} className="panel quota-card">
              <div className="quota-topline">
                <span>{window.label}</span>
                <span className={`state-pill ${toneClass(window.tone)}`}>{window.state}</span>
              </div>
              <div className="progress-track">
                <div className={`progress-fill ${toneClass(window.tone)}`} style={{ width: `${window.burn}%` }} />
              </div>
              <p className="section-note compact">{window.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="fleet-layout">
        <div className="project-grid">
          {projectCatalog.map((project) => (
            <button
              key={project.id}
              type="button"
              className={`panel project-card ${projectToneClass(project.tone)}`}
              onClick={() => handleOpenProject(project.id)}
            >
              <div className="project-card-header">
                <div>
                  <p className="project-title">{project.name}</p>
                  <p className="project-meta">{project.surface}</p>
                </div>
                <span className={`state-pill ${projectToneClass(project.tone)}`}>{project.nextWake}</span>
              </div>

              <div className="project-stat-row">
                <div>
                  <span className="mini-label">Live engine</span>
                  <strong>{project.engine}</strong>
                </div>
                <div>
                  <span className="mini-label">Latest packet</span>
                  <strong>{project.lastPayload}</strong>
                </div>
              </div>

              <div className="project-footer-row">
                <span>{project.mission}</span>
                <span>Open</span>
              </div>
            </button>
          ))}
        </div>

        <aside className="panel side-rail">
          <div className="section-heading-row tight">
            <div>
              <p className="section-kicker">Fleet feed</p>
              <h3>Recent events</h3>
            </div>
          </div>

          <div className="timeline-list">
            {globalSignals.map((signal) => (
              <div key={`${signal.time}-${signal.title}`} className="timeline-item">
                <span className="timeline-time">{signal.time}</span>
                <div>
                  <div className="timeline-title-row">
                    <strong>{signal.title}</strong>
                    <span className={`dot ${toneClass(signal.tone)}`} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </section>
    </div>
  );

  const renderMission = () => (
    <div className="workspace-grid mission-grid">
      <section className="panel feature-panel">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Mission board</p>
            <h3>{selectedProject.name}</h3>
          </div>
          <div className="mission-actions">
            <button type="button" className="mini-action">+ Task</button>
            <button type="button" className="mini-action">+ Story</button>
            <button type="button" className="mini-action">+ Bug</button>
            <button type="button" className="mini-action">+ Epic</button>
          </div>
        </div>

        <div className="mission-meta-row">
          <span className="mono-chip">{selectedProject.engine}</span>
          <span className="mono-chip">{selectedProject.nextWake}</span>
          <span className="mono-chip">{selectedProject.lastPayload}</span>
        </div>

        <div className="kanban-grid">
          {selectedWorkspace.boardColumns.map((column) => (
            <section key={column.title} className="kanban-column">
              <div className="kanban-column-header">
                <strong>{column.title}</strong>
                <span className="kanban-count">{column.items.length}</span>
              </div>

              <div className="kanban-stack">
                {column.items.map((item) => (
                  <article key={`${column.title}-${item.title}`} className="kanban-card">
                    <span className={`work-kind kind-${item.kind}`}>{item.kind}</span>
                    <strong>{item.title}</strong>
                    <small>{item.meta}</small>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>
    </div>
  );

  const renderRun = () => (
    <div className="workspace-grid runs-grid">
      <section className="panel terminal-panel">
        <div className="terminal-header">
          <div>
            <p className="section-kicker">Session</p>
            <h3>Live stream</h3>
          </div>
          <span className="mono-chip">watch only</span>
        </div>

        <div className="terminal-window">
          {selectedWorkspace.terminalLines.map((line) => (
            <div key={line.text} className={`terminal-line ${line.kind}`}>
              {line.text}
            </div>
          ))}
        </div>

        <div className="timeline-list compact-list run-timeline">
          {selectedWorkspace.runTimeline.map((step) => (
            <div key={`${step.time}-${step.title}`} className="timeline-item compact-item">
              <span className="timeline-time">{step.time}</span>
              <div>
                <div className="timeline-title-row">
                  <strong>{step.title}</strong>
                  <span className={`dot ${toneClass(step.tone)}`} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel feature-panel">
        <div className="section-heading-row tight">
          <div>
            <p className="section-kicker">Viewport</p>
            <h3>Live check</h3>
          </div>
        </div>

        <div className="vision-canvas">
          <div className="scan-layer" />
          <div className="vision-box target-box">
            <span className="vision-tag">TARGET</span>
            <span className="vision-label">Primary action cluster</span>
          </div>
          <div className="vision-box action-box">
            <span className="vision-tag">ACTION</span>
            <span className="vision-label">Verify / capture / seal</span>
          </div>
          <div className="cursor-marker" />
          <div className="vision-footer">
            <span>Viewport replay</span>
            <span>Latency 142 ms</span>
            <span>FPS 12.4</span>
          </div>
        </div>

        <div className="detection-list">
          {selectedWorkspace.detections.map((detection) => (
            <div key={detection.label} className="detection-item">
              <div className="timeline-title-row">
                <strong>{detection.label}</strong>
                <span className={`dot ${toneClass(detection.tone)}`} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel feature-panel">
        <div className="section-heading-row tight">
          <div>
            <p className="section-kicker">Watching</p>
            <h3>Observed now</h3>
          </div>
        </div>

        <div className="queue-list">
          {selectedWorkspace.surfaces.map((surface) => (
            <div key={surface.name} className="queue-item">
              {surface.name}
            </div>
          ))}
        </div>

        <div className="timeline-list compact-list run-watch-list">
          {selectedWorkspace.runTimeline.map((entry) => (
            <div key={`${entry.time}-${entry.title}-watch`} className="queue-item">
              {entry.time} {entry.title}
            </div>
          ))}
        </div>
      </section>
    </div>
  );

  const renderContext = () => (
    <div className="workspace-grid rag-grid">
      <section className="panel feature-panel wide">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Ingest</p>
            <h3>Add to project memory</h3>
          </div>
          <span className="mono-chip">RAG workspace</span>
        </div>

        <div className="ingest-row">
          <label className="upload-tile">
            <input className="hidden-input" type="file" multiple onChange={handleUploadDocuments} />
            <strong>Upload docs</strong>
            <span>PDF, MD, TXT</span>
          </label>

          <div className="note-composer">
            <textarea
              className="context-input"
              value={draftNote}
              onChange={(event) => setDraftNote(event.target.value)}
              placeholder="Add a note, decision, or reminder..."
            />
            <button type="button" className="primary-button context-save-button" onClick={handleInjectNote}>
              Save note
            </button>
          </div>
        </div>
      </section>

      <section className="panel feature-panel">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Sources</p>
            <h3>Indexed files</h3>
          </div>
          <span className="mono-chip">{activeDocuments.length}</span>
        </div>

        <div className="simple-stack">
          {activeDocuments.map((document) => (
            <button
              key={document.name}
              type="button"
              className={`source-card plain-card-button ${selectedSourceName === document.name ? 'active' : ''}`}
              onClick={() => handleFocusSource(document.name)}
            >
              <div className="timeline-title-row">
                <strong>{document.name}</strong>
                <span className="mono-chip">{document.tag}</span>
              </div>
              <div className="source-meta-row">
                <span>{document.chunks} chunks</span>
                <span>{document.status}</span>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="panel feature-panel">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Graph</p>
            <h3>Linked contexts</h3>
          </div>
        </div>

        <div className="graph-card-grid">
          {selectedWorkspace.linkedContexts.map((context) => (
            <button
              key={context.label}
              type="button"
              className={`graph-context-card plain-card-button ${selectedSourceName === context.source ? 'active' : ''}`}
              onClick={() => handleFocusSource(context.source)}
            >
              <strong>{context.label}</strong>
              <span>{context.links} links</span>
              <small>{context.source}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="panel feature-panel wide">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Source preview</p>
            <h3>{selectedSource?.name ?? 'No source selected'}</h3>
          </div>
          {selectedSource && <span className="mono-chip">{selectedSource.chunks} chunks</span>}
        </div>

        {selectedSource ? (
          <div className="source-preview-grid">
            <section className="source-preview-meta">
              <div className="simple-stack">
                <article className="source-detail-card">
                  <span className="mini-label">Status</span>
                  <strong>{selectedSource.status}</strong>
                </article>
                <article className="source-detail-card">
                  <span className="mini-label">Summary</span>
                  <p>{selectedSource.summary}</p>
                </article>
              </div>
            </section>

            <section className="chunk-list">
              {previewChunks.map((chunk) => (
                <article key={`${selectedSource.name}-${chunk.title}`} className="chunk-card">
                  <div className="timeline-title-row">
                    <strong>{chunk.title}</strong>
                    <span className="mono-chip">{selectedSource.tag}</span>
                  </div>
                  <p>{chunk.excerpt}</p>
                  <div className="chunk-tag-row">
                    {chunk.tags.map((tag) => (
                      <span key={`${chunk.title}-${tag}`} className="graph-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </article>
              ))}
            </section>
          </div>
        ) : (
          <div className="empty-state">Upload or select a source to inspect its chunks.</div>
        )}
      </section>

      <section className="panel feature-panel wide">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Active retrieval</p>
            <h3>What the run is pulling in</h3>
          </div>
        </div>

        <div className="retrieval-list">
          {selectedWorkspace.activeRetrieval.map((item) => (
            <button
              key={`${item.source}-${item.title}`}
              type="button"
              className={`retrieval-card plain-card-button ${selectedSourceName === item.source ? 'active' : ''}`}
              onClick={() => handleFocusSource(item.source)}
            >
              <div className="timeline-title-row">
                <strong>{item.title}</strong>
                <span className="mono-chip">{item.score}</span>
              </div>
              <span className="mini-label">{item.source}</span>
              <p>{item.excerpt}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="panel feature-panel wide">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Pinned notes</p>
            <h3>Operator memory</h3>
          </div>
          <span className="mono-chip">{activeNotes.length}</span>
        </div>

        <div className="simple-stack">
          {activeNotes.map((note) => (
            <article key={note.id} className="simple-note-card">
              <div className="timeline-title-row">
                <strong>{note.title}</strong>
                <span className="mono-chip">{note.tag}</span>
              </div>
              <p>{note.body}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );

  const renderChat = () => (
    <div className="workspace-grid chat-grid">
      <section className="panel feature-panel chat-panel">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Chat</p>
            <h3>Talk to the agent</h3>
          </div>
          <span className="mono-chip">live workspace</span>
        </div>

        <div className="chat-stream">
          {activeChat.map((message) => (
            <div
              key={message.id}
              className={`chat-row ${message.role === 'operator' ? 'chat-row-operator' : 'chat-row-jr'}`}
            >
              <article className={`chat-bubble ${message.role === 'operator' ? 'chat-bubble-operator' : 'chat-bubble-jr'}`}>
                <span className="chat-role">{message.role === 'operator' ? 'You' : 'SelfFork'}</span>
                <p>{message.text}</p>
              </article>
            </div>
          ))}
        </div>

        <div className="chat-quick-row">
          <button type="button" className="quick-chip" onClick={() => setDraftChat('What are you doing right now?')}>
            What are you doing?
          </button>
          <button type="button" className="quick-chip" onClick={() => setDraftChat('Add this to the board and keep going.')}>
            Add to board
          </button>
          <button type="button" className="quick-chip" onClick={() => setDraftChat('Summarize blockers for this workspace.')}>
            Summarize blockers
          </button>
        </div>

        <div className="chat-composer">
          <textarea
            className="context-input chat-input"
            value={draftChat}
            onChange={(event) => setDraftChat(event.target.value)}
            placeholder="Message the agent..."
          />
          <button type="button" className="primary-button chat-send" onClick={handleSendChat}>
            Send
          </button>
        </div>
      </section>
    </div>
  );

  const renderWorkspace = () => (
    <div className="workspace-shell">
      <section className="panel workspace-banner banded">
        <div className="workspace-banner-top">
          <button type="button" className="back-button" onClick={() => setScreen('fleet')}>
            Fleet
          </button>
          <span className={`state-pill ${projectToneClass(selectedProject.tone)}`}>{selectedProject.nextWake}</span>
        </div>

        <div className="workspace-hero">
          <div>
            <p className="eyebrow">{selectedProject.surface}</p>
            <h2>{selectedProject.name}</h2>
            <p className="hero-copy compact">{selectedWorkspace.strapline}</p>
          </div>
          <div className="workspace-side-meta">
            <div>
              <span className="mini-label">Live engine</span>
              <strong>{selectedProject.engine}</strong>
            </div>
            <div>
              <span className="mini-label">Last payload</span>
              <strong>{selectedProject.lastPayload}</strong>
            </div>
          </div>
        </div>

        <div className="workspace-tabs">
          {workspaceTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </section>

      <div className="workspace-canvas">
        {activeTab === 'mission' && renderMission()}
        {activeTab === 'run' && renderRun()}
        {activeTab === 'chat' && renderChat()}
        {activeTab === 'context' && renderContext()}
      </div>
    </div>
  );

  return (
    <div className="app-shell">
      {screen !== 'login' && (
        <header className="topbar">
          <button type="button" className="brand-button" onClick={() => setScreen('fleet')}>
            <span className="brand-mark" />
            <span>
              <strong>SelfFork</strong>
              <small>cockpit</small>
            </span>
          </button>

          <div className="topbar-meta">
            <span className="mono-chip">Core online</span>
            <span className="mono-chip">Proof-first</span>
          </div>
        </header>
      )}

      {screen === 'login' && renderLogin()}
      {screen === 'fleet' && renderFleet()}
      {screen === 'workspace' && renderWorkspace()}
    </div>
  );
}

export default App;
