import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Play,
  Pause,
  RotateCcw,
  FastForward,
  Layers,
  Cpu,
  Volume2,
  Users,
  FileCheck,
  Brain,
  ShieldCheck,
  Database,
  Terminal,
  Activity,
  ArrowRight,
  Check,
  X,
  Maximize2,
  Minimize2,
  ExternalLink,
  ChevronRight,
  Flame,
  Radio,
  Share2,
  Sliders,
  Zap,
  Info
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { MeetingItem, MeetingIntelligence } from '../types';

export interface PipelineStageDef {
  id: string;
  stageNumber: number;
  title: string;
  shortName: string;
  agentOrEngine: string;
  icon: 'audio' | 'diarize' | 'asr' | 'speaker' | 'blackboard' | 'consensus' | 'indexing';
  description: string;
  estimatedDurationMs: number;
  subTasks: string[];
  metrics: { label: string; value: string; hint?: string }[];
  logTemplates: string[];
}

export interface PipelineExecutionLog {
  id: string;
  timestamp: string;
  stageId: string;
  level: 'info' | 'success' | 'warning' | 'diar' | 'asr' | 'agent';
  message: string;
}

export const PIPELINE_STAGES: PipelineStageDef[] = [
  {
    id: 'stage-1-ingest',
    stageNumber: 1,
    title: 'Audio Ingestion & VAD Chunking',
    shortName: 'Payload Ingest',
    agentOrEngine: 'ADR-004 Ingestion Buffer',
    icon: 'audio',
    description: 'Validates audio payload, normalises sample rate to 16kHz mono PCM, and computes energy-based Voice Activity Detection (VAD) slices.',
    estimatedDurationMs: 1200,
    subTasks: [
      'Format & header validation (WAV / MP3 / M4A / FLAC)',
      '16kHz PCM downsampling & stereo-to-mono downmix',
      'VAD energy thresholding & 30s sliding chunk windowing',
      'ADR-004 cryptographic buffer integrity verification'
    ],
    metrics: [
      { label: 'Sample Rate', value: '16.0 kHz', hint: 'Mono 16-bit PCM' },
      { label: 'Chunk Windows', value: '30s / 10s step', hint: 'Overlap 33%' },
      { label: 'Ingest Latency', value: '42 ms', hint: 'Direct stream buffer' }
    ],
    logTemplates: [
      'Payload format identified and verified against ADR-004 specification.',
      'Audio resampled to 16,000 Hz single-channel PCM stream.',
      'VAD acoustic energy segmenter detected 28 speech bursts.',
      'Audio chunk buffers allocated into high-speed memory cache.'
    ]
  },
  {
    id: 'stage-2-diarization',
    stageNumber: 2,
    title: 'Open-MOSS Acoustic Diarization',
    shortName: 'Diarization',
    agentOrEngine: 'PyAnnote 3.1 + Open-MOSS',
    icon: 'diarize',
    description: 'Extracts x-vector acoustic speaker embeddings, performs spectral clustering, and maps overlapping speaker turns.',
    estimatedDurationMs: 1800,
    subTasks: [
      'PyAnnote 3.1 neural speaker embedding computation',
      'Constrained spectral clustering & turn boundary segmentation',
      'Multi-speaker overlap detection & acoustic separation',
      'Diarization Error Rate (DER) optimization target < 8.2%'
    ],
    metrics: [
      { label: 'Primary Diarizer', value: 'Open-MOSS / PyAnnote', hint: 'v3.1 Neural' },
      { label: 'DER Target', value: '6.4%', hint: 'Benchmark: < 8.2%' },
      { label: 'Identified Clusters', value: '3 Speakers', hint: 'K-Means Spectral' }
    ],
    logTemplates: [
      'Initialized PyAnnote 3.1 acoustic feature extractor on GPU (Tesla T4).',
      'Generated 512-dim d-vector embeddings across 148 temporal windows.',
      'Spectral clustering converged with silhouette score 0.892.',
      'Diarization turn boundaries synchronized: 3 speaker clusters registered.'
    ]
  },
  {
    id: 'stage-3-asr',
    stageNumber: 3,
    title: 'Multilingual ASR & Code-Switch Decoding',
    shortName: 'ASR Decoding',
    agentOrEngine: 'Sarvam-1 / Whisper Conformer',
    icon: 'asr',
    description: 'Transcribes phonemes into multilingual text with token-level language identification (English, Hindi, Hinglish, Tanglish).',
    estimatedDurationMs: 2200,
    subTasks: [
      'Multilingual acoustic feature frame decoding',
      'Indic / Code-switch language identifier (LID) token classification',
      'Word-level phonetic timestamp and acoustic confidence tagging',
      'Punctuation restoration and casing normalization'
    ],
    metrics: [
      { label: 'ASR Engine', value: 'Sarvam Saaras Indic', hint: 'vLLM Accelerated' },
      { label: 'Predicted WER', value: '4.8%', hint: 'Word Error Rate' },
      { label: 'Real-Time Factor', value: '0.18x', hint: 'Ultra-fast decoding' }
    ],
    logTemplates: [
      'Dispatched acoustic chunks to Sarvam Saaras Indic multilingual ASR pipeline.',
      'Detected code-switching transitions: Hindi Devanagari ↔ Latin Script.',
      'Generated 412 word tokens with microsecond alignment timestamps.',
      'ASR inference complete with mean acoustic confidence 96.4%.'
    ]
  },
  {
    id: 'stage-4-speaker-grounding',
    stageNumber: 4,
    title: 'Speaker Roster Reconciliation',
    shortName: 'Speaker Grounding',
    agentOrEngine: 'Acoustic Identity Grounder',
    icon: 'speaker',
    description: 'Binds acoustic speaker clusters to expected participant profiles, meeting host roles, and organizational directories.',
    estimatedDurationMs: 1400,
    subTasks: [
      'Probabilistic voiceprint matching against participant roster',
      'Turn-taking cadence and conversational dominance analysis',
      'Host & guest role disambiguation',
      'Unresolved voice segments tagged for verification review'
    ],
    metrics: [
      { label: 'Roster Match', value: '100% (3/3)', hint: 'High confidence' },
      { label: 'Attribution Fidelity', value: '98.7%', hint: 'Role binding' },
      { label: 'Overlaps Resolved', value: '14 segments', hint: 'Dual-speaker' }
    ],
    logTemplates: [
      'Cross-referencing speaker cluster SPK_01 with participant metadata.',
      'Attributed SPK_01 → Sneha (Lead) [Acoustic confidence: 99.1%].',
      'Attributed SPK_02 → Om (Researcher) [Acoustic confidence: 97.4%].',
      'Attributed SPK_03 → Neetigya (ML Ops) [Acoustic confidence: 96.8%].'
    ]
  },
  {
    id: 'stage-5-blackboard',
    stageNumber: 5,
    title: 'ACE Blackboard Multi-Agent Orchestration',
    shortName: 'ACE Blackboard',
    agentOrEngine: 'Distributed Specialist Agents',
    icon: 'blackboard',
    description: 'Parallel specialist agents post hypotheses to the shared blackboard: decisions, action deliverables, topics, and risk factors.',
    estimatedDurationMs: 2400,
    subTasks: [
      'Blackboard shared memory bus initialization',
      'Decision Extraction Agent: consensus level classification',
      'Action Item & Ownership Agent: assignee & deadline binding',
      'Risk & Topic Analysis Agent: sentiment & threat level assessment'
    ],
    metrics: [
      { label: 'Active Agents', value: '4 Specialists', hint: 'Autonomous loop' },
      { label: 'Blackboard Writes', value: '18 Hypotheses', hint: 'Shared memory' },
      { label: 'Agent Latency', value: '185 ms', hint: 'Concurrent dispatch' }
    ],
    logTemplates: [
      'Blackboard workspace allocated: session uuid initialized.',
      '[DecisionAgent] Proposed 2 consensus decisions with unanimous backing.',
      '[ActionAgent] Extracted 3 action deliverables with assigned deadlines.',
      '[RiskAgent] Identified timeline dependency risk: severity MEDIUM.'
    ]
  },
  {
    id: 'stage-6-consensus',
    stageNumber: 6,
    title: 'Consensus Reconciliation & Fact-Checking',
    shortName: 'Consensus Voting',
    agentOrEngine: 'Blackboard Arbiter & Verifier',
    icon: 'consensus',
    description: 'Arbiter executes multi-agent consensus voting, resolves conflicting entity claims, and filters hallucinations.',
    estimatedDurationMs: 1600,
    subTasks: [
      'Cross-agent voting matrix evaluation and weighted consensus',
      'Transcript grounding check against word token confidence',
      'Contested statement disambiguation and conflict resolution',
      'Executive summary & key takeaway synthesis'
    ],
    metrics: [
      { label: 'Consensus Score', value: '98.2%', hint: 'Arbiter consensus' },
      { label: 'Contested Items', value: '0', hint: 'All claims verified' },
      { label: 'Hallucination Check', value: 'PASS', hint: 'Grounding verified' }
    ],
    logTemplates: [
      'Arbiter initiated weighted consensus reconciliation on Blackboard.',
      'Verified action item assignees against organizational directory.',
      'Multi-agent consensus converged with 98.2% statistical confidence.',
      'Synthesized final executive summary and strategic takeaways.'
    ]
  },
  {
    id: 'stage-7-indexing',
    stageNumber: 7,
    title: 'Knowledge Graph Indexing & Artifact Ready',
    shortName: 'Graph Indexing',
    agentOrEngine: 'RFC-009 Vector & Audit Store',
    icon: 'indexing',
    description: 'Constructs canonical Knowledge Objects with version lineage, generates vector embeddings, and writes security audit logs.',
    estimatedDurationMs: 1400,
    subTasks: [
      'Canonical Knowledge Object (KO) schema generation (RFC-009)',
      '768-dim semantic dense embedding computation',
      'Cross-meeting entity graph linking & vector warehouse index',
      'Cryptographic SHA-256 audit ledger entry commit'
    ],
    metrics: [
      { label: 'Knowledge Objects', value: '+4 Created', hint: 'RFC-009 Schema' },
      { label: 'Embedding Vector', value: '768-dim Indic', hint: 'Dense retrieval' },
      { label: 'Audit Hash', value: 'ADR-008 Verified', hint: 'Immutable log' }
    ],
    logTemplates: [
      'Generated canonical Knowledge Objects with RFC-009 version lineage.',
      'Indexed 768-dim dense semantic embeddings into vector search engine.',
      'Committed cryptographic audit trail: PIPELINE_ORCHESTRATION_TRIGGER.',
      'Meeting intelligence artifacts compiled and broadcast to UI channels.'
    ]
  }
];

interface MeetingPipelineTimelineProps {
  meeting: MeetingItem;
  isOpen: boolean;
  onClose: () => void;
  onViewIntelligence?: (meetingId: string) => void;
  onPipelineComplete?: (meetingId: string) => void;
  theme?: 'dark' | 'light';
  autoStart?: boolean;
}

export const MeetingPipelineTimeline: React.FC<MeetingPipelineTimelineProps> = ({
  meeting,
  isOpen,
  onClose,
  onViewIntelligence,
  onPipelineComplete,
  theme = 'dark',
  autoStart = true
}) => {
  // Playback & Stage State
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(autoStart);
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(1);
  const [stageProgress, setStageProgress] = useState<number>(0);
  const [isCompleted, setIsCompleted] = useState<boolean>(meeting.status === 'completed');
  const [selectedStageIndex, setSelectedStageIndex] = useState<number>(0);
  const [activeTab, setActiveTab] = useState<'timeline' | 'logs' | 'metrics'>('timeline');
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  // Execution Telemetry Logs
  const [logs, setLogs] = useState<PipelineExecutionLog[]>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<any>(null);

  // Initialize or Reset Pipeline
  const handleReset = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setCurrentStageIndex(0);
    setSelectedStageIndex(0);
    setStageProgress(0);
    setIsCompleted(false);
    setLogs([]);
    setIsPlaying(true);
  };

  // Add Log Entry Helper
  const addLog = (stageId: string, message: string, level: PipelineExecutionLog['level'] = 'info') => {
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0] + '.' + String(now.getMilliseconds()).padStart(3, '0');
    setLogs(prev => [
      ...prev,
      {
        id: `log-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
        timestamp: timeStr,
        stageId,
        level,
        message
      }
    ]);
  };

  // Scroll logs to bottom
  useEffect(() => {
    if (activeTab === 'logs') {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, activeTab]);

  // Main Progression Timer
  useEffect(() => {
    if (!isOpen) return;

    if (isCompleted) {
      return;
    }

    if (!isPlaying) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    const currentStage = PIPELINE_STAGES[currentStageIndex];
    if (!currentStage) {
      setIsCompleted(true);
      setIsPlaying(false);
      if (onPipelineComplete) onPipelineComplete(meeting.id);
      return;
    }

    // Set selected stage to current active
    setSelectedStageIndex(currentStageIndex);

    // Initial Stage Start Logs
    if (stageProgress === 0) {
      addLog(
        currentStage.id,
        `▶ [STAGE ${currentStage.stageNumber}/7] Initiating ${currentStage.title} via ${currentStage.agentOrEngine}`,
        'info'
      );
    }

    const intervalMs = 50;
    const totalDuration = currentStage.estimatedDurationMs / speedMultiplier;
    const progressIncrement = (intervalMs / totalDuration) * 100;

    timerRef.current = setInterval(() => {
      setStageProgress(prev => {
        const next = prev + progressIncrement;

        // Emit intermediate stage logs at key milestones
        if (prev < 30 && next >= 30) {
          addLog(currentStage.id, currentStage.logTemplates[0] || 'Executing baseline subtask...', 'info');
        } else if (prev < 60 && next >= 60) {
          addLog(currentStage.id, currentStage.logTemplates[1] || 'Synchronizing intermediate tensors...', 'diar');
        } else if (prev < 85 && next >= 85) {
          addLog(currentStage.id, currentStage.logTemplates[2] || 'Validating stage assertions...', 'asr');
        }

        if (next >= 100) {
          clearInterval(timerRef.current);
          addLog(
            currentStage.id,
            `✔ [STAGE ${currentStage.stageNumber}/7] ${currentStage.title} finished successfully.`,
            'success'
          );

          if (currentStageIndex < PIPELINE_STAGES.length - 1) {
            setCurrentStageIndex(currentStageIndex + 1);
            setStageProgress(0);
          } else {
            setIsCompleted(true);
            setIsPlaying(false);
            addLog('pipeline-end', '🎉 Open-MOSS End-to-End Pipeline execution completed with 100% consensus.', 'success');
            if (onPipelineComplete) {
              onPipelineComplete(meeting.id);
            }
          }
          return 100;
        }
        return next;
      });
    }, intervalMs);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isOpen, isPlaying, currentStageIndex, speedMultiplier, isCompleted]);

  if (!isOpen) return null;

  const currentStage = PIPELINE_STAGES[currentStageIndex] || PIPELINE_STAGES[PIPELINE_STAGES.length - 1];
  const inspectedStage = PIPELINE_STAGES[selectedStageIndex] || currentStage;
  const overallPercent = Math.min(
    100,
    Math.round(((currentStageIndex + (isCompleted ? 1 : stageProgress / 100)) / PIPELINE_STAGES.length) * 100)
  );

  const getStageIcon = (icon: PipelineStageDef['icon'], className: string = 'w-5 h-5') => {
    switch (icon) {
      case 'audio':
        return <Volume2 className={className} />;
      case 'diarize':
        return <Activity className={className} />;
      case 'asr':
        return <Radio className={className} />;
      case 'speaker':
        return <Users className={className} />;
      case 'blackboard':
        return <Brain className={className} />;
      case 'consensus':
        return <ShieldCheck className={className} />;
      case 'indexing':
        return <Database className={className} />;
      default:
        return <Layers className={className} />;
    }
  };

  return (
    <div
      id="modal-pipeline-timeline"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md overflow-y-auto"
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 12 }}
        transition={{ duration: 0.25, ease: 'easeOut' }}
        className={`w-full ${
          isExpanded ? 'max-w-7xl' : 'max-w-5xl'
        } rounded-3xl border shadow-2xl overflow-hidden flex flex-col max-h-[92vh] transition-all duration-300 ${
          theme === 'dark'
            ? 'bg-slate-900 border-indigo-500/40 text-slate-100 shadow-indigo-950/50'
            : 'bg-white border-slate-200 text-slate-900 shadow-indigo-100'
        }`}
      >
        {/* Modal Top Header Bar */}
        <div
          className={`px-6 py-4 border-b flex flex-wrap items-center justify-between gap-4 ${
            theme === 'dark' ? 'bg-slate-950/80 border-slate-800' : 'bg-slate-50 border-slate-200'
          }`}
        >
          <div className="flex items-center space-x-3.5">
            <div className="p-2.5 rounded-2xl bg-gradient-to-tr from-indigo-600 to-purple-600 text-white shadow-lg shadow-indigo-600/30">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold tracking-tight">End-to-End Pipeline Execution Timeline</h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-800/80 font-bold uppercase">
                  ADR-004 &bull; Open-MOSS
                </span>
                {isCompleted ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-950/60 px-2.5 py-0.5 rounded-full border border-emerald-800/60">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Pipeline Synthesized
                  </span>
                ) : isPlaying ? (
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-indigo-300 bg-indigo-950/60 px-2.5 py-0.5 rounded-full border border-indigo-800/60 animate-pulse">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" /> Stage {currentStageIndex + 1}/7 Active
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-400 bg-amber-950/60 px-2.5 py-0.5 rounded-full border border-amber-800/60">
                    <Clock className="w-3.5 h-3.5" /> Paused
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 truncate max-w-xl">
                Meeting: <span className="font-semibold text-slate-200">{meeting.title}</span> ({meeting.primary_language.toUpperCase()})
              </p>
            </div>
          </div>

          {/* Top Right Window & Speed Controls */}
          <div className="flex items-center gap-2">
            {/* Speed Multiplier */}
            <div className="hidden sm:flex items-center gap-1 px-2 py-1 rounded-xl bg-slate-900 border border-slate-800 text-xs font-mono">
              <span className="text-[11px] text-slate-400 mr-1 flex items-center gap-0.5">
                <FastForward className="w-3 h-3 text-indigo-400" /> Speed:
              </span>
              {[1, 2, 4, 8].map(s => (
                <button
                  key={`speed-${s}`}
                  type="button"
                  onClick={() => setSpeedMultiplier(s)}
                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold cursor-pointer transition-colors ${
                    speedMultiplier === s
                      ? 'bg-indigo-600 text-white'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>

            {/* Expand / Minimize Toggle */}
            <button
              type="button"
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-2 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors cursor-pointer"
              title={isExpanded ? 'Collapse view' : 'Expand full-width'}
            >
              {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>

            {/* Close Button */}
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              title="Close modal"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Global Progress Strip */}
        <div className="relative bg-slate-950 border-b border-slate-800/80 px-6 py-3">
          <div className="flex items-center justify-between text-xs font-mono mb-2">
            <div className="flex items-center gap-2">
              <span className="font-bold text-indigo-400">Total Execution:</span>
              <span className="text-slate-300 font-semibold">{overallPercent}%</span>
              <span className="text-slate-400">&bull;</span>
              <span className="text-slate-400">
                Active: <span className="text-teal-400 font-semibold">{currentStage.shortName}</span> ({currentStage.agentOrEngine})
              </span>
            </div>
            <div className="flex items-center gap-3 text-slate-400 text-[11px]">
              <span>Est. Total Latency: ~10.4s</span>
              <span>Hardware: Tesla T4 (vLLM)</span>
            </div>
          </div>

          <div className="w-full bg-slate-900 rounded-full h-2.5 overflow-hidden border border-slate-800 p-0.5">
            <motion.div
              className="bg-gradient-to-r from-indigo-500 via-purple-500 to-teal-400 h-full rounded-full transition-all duration-200"
              style={{ width: `${overallPercent}%` }}
            />
          </div>
        </div>

        {/* Horizontal Timeline Track */}
        <div className="px-6 py-4 border-b border-slate-800/80 bg-slate-950/40 overflow-x-auto">
          <div className="flex items-center justify-between min-w-[720px] gap-2">
            {PIPELINE_STAGES.map((stage, idx) => {
              const isPast = idx < currentStageIndex || isCompleted;
              const isCurrent = idx === currentStageIndex && !isCompleted;
              const isSelected = idx === selectedStageIndex;

              return (
                <div key={stage.id} className="flex-1 flex items-center">
                  <div
                    onClick={() => setSelectedStageIndex(idx)}
                    className={`relative flex-1 p-3 rounded-2xl border transition-all cursor-pointer select-none group ${
                      isSelected
                        ? 'ring-2 ring-indigo-500 border-indigo-400 bg-indigo-950/40 shadow-lg shadow-indigo-950/50'
                        : isCurrent
                        ? 'border-teal-500 bg-teal-950/20 text-teal-200 animate-pulse'
                        : isPast
                        ? 'border-emerald-800/60 bg-emerald-950/20 text-slate-200 hover:border-emerald-600'
                        : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    {/* Node Header */}
                    <div className="flex items-center justify-between mb-1.5">
                      <div
                        className={`w-7 h-7 rounded-xl flex items-center justify-center text-xs font-bold transition-all ${
                          isPast
                            ? 'bg-emerald-500 text-slate-950'
                            : isCurrent
                            ? 'bg-teal-400 text-slate-950 ring-4 ring-teal-500/20'
                            : 'bg-slate-800 text-slate-400'
                        }`}
                      >
                        {isPast ? <Check className="w-4 h-4 stroke-[3]" /> : stage.stageNumber}
                      </div>

                      <div className="text-[10px] font-mono">
                        {isPast ? (
                          <span className="text-emerald-400 font-semibold">DONE</span>
                        ) : isCurrent ? (
                          <span className="text-teal-300 font-bold">{Math.round(stageProgress)}%</span>
                        ) : (
                          <span className="text-slate-400">WAIT</span>
                        )}
                      </div>
                    </div>

                    {/* Stage Name & Tag */}
                    <div className="space-y-0.5">
                      <div className="text-xs font-bold truncate text-white">{stage.shortName}</div>
                      <div className="text-[10px] text-slate-400 truncate">{stage.agentOrEngine}</div>
                    </div>

                    {/* Progress Bar inside Node for Current Stage */}
                    {isCurrent && (
                      <div className="mt-2 w-full bg-slate-900 rounded-full h-1 overflow-hidden">
                        <div
                          className="bg-teal-400 h-full transition-all duration-150"
                          style={{ width: `${stageProgress}%` }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Connecting Arrow between Stages */}
                  {idx < PIPELINE_STAGES.length - 1 && (
                    <div className="px-1 text-slate-700 shrink-0">
                      <ChevronRight className={`w-4 h-4 ${idx < currentStageIndex ? 'text-emerald-500' : 'text-slate-700'}`} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Modal Main Body: Split View with Stage Details & Interactive Console */}
        <div className="flex-1 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 divide-y lg:divide-y-0 lg:divide-x divide-slate-800/80">
          {/* Left Column: Inspected Stage Deep-Dive (7 Cols) */}
          <div className="lg:col-span-7 p-6 space-y-6">
            {/* Stage Title and Summary */}
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3.5">
                <div className="p-3 rounded-2xl bg-indigo-950/80 text-indigo-400 border border-indigo-800/80 shrink-0">
                  {getStageIcon(inspectedStage.icon, 'w-6 h-6')}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold text-indigo-400 uppercase">
                      Stage {inspectedStage.stageNumber} of 7
                    </span>
                    <span className="text-slate-400">&bull;</span>
                    <span className="text-xs font-mono text-slate-400">{inspectedStage.agentOrEngine}</span>
                  </div>
                  <h3 className="text-lg font-bold text-white tracking-tight">{inspectedStage.title}</h3>
                  <p className="text-xs text-slate-300 mt-1 leading-relaxed">{inspectedStage.description}</p>
                </div>
              </div>

              <div className="text-right shrink-0">
                <span
                  className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold font-mono border ${
                    selectedStageIndex < currentStageIndex || isCompleted
                      ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
                      : selectedStageIndex === currentStageIndex
                      ? 'bg-teal-950/60 border-teal-800 text-teal-300 animate-pulse'
                      : 'bg-slate-950 border-slate-800 text-slate-400'
                  }`}
                >
                  {selectedStageIndex < currentStageIndex || isCompleted
                    ? 'COMPLETED'
                    : selectedStageIndex === currentStageIndex
                    ? `RUNNING (${Math.round(stageProgress)}%)`
                    : 'QUEUED'}
                </span>
              </div>
            </div>

            {/* Stage Telemetry Metrics Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {inspectedStage.metrics.map((m, idx) => (
                <div
                  key={`metric-${idx}`}
                  className="p-3.5 rounded-2xl bg-slate-950/80 border border-slate-800 space-y-1"
                >
                  <div className="text-[11px] font-medium text-slate-400">{m.label}</div>
                  <div className="text-sm font-mono font-bold text-teal-300">{m.value}</div>
                  {m.hint && <div className="text-[10px] text-slate-400">{m.hint}</div>}
                </div>
              ))}
            </div>

            {/* Subtasks Execution Checklist */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400" />
                Pipeline Sub-Tasks &amp; Architectural Assertions
              </h4>
              <div className="space-y-2">
                {inspectedStage.subTasks.map((task, idx) => {
                  const isTaskDone = selectedStageIndex < currentStageIndex || isCompleted || (selectedStageIndex === currentStageIndex && stageProgress > ((idx + 1) / inspectedStage.subTasks.length) * 90);
                  const isTaskActive = selectedStageIndex === currentStageIndex && !isTaskDone && stageProgress >= (idx / inspectedStage.subTasks.length) * 90;

                  return (
                    <div
                      key={`task-${idx}`}
                      className={`p-3 rounded-xl border text-xs flex items-center justify-between transition-all ${
                        isTaskDone
                          ? 'bg-emerald-950/15 border-emerald-800/40 text-slate-200'
                          : isTaskActive
                          ? 'bg-indigo-950/30 border-indigo-600/50 text-indigo-200 ring-1 ring-indigo-500/30'
                          : 'bg-slate-950/40 border-slate-800/60 text-slate-400'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <div
                          className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                            isTaskDone
                              ? 'bg-emerald-500 text-slate-950 font-bold'
                              : isTaskActive
                              ? 'bg-indigo-500 text-white animate-spin'
                              : 'bg-slate-800 text-slate-400'
                          }`}
                        >
                          {isTaskDone ? '✓' : isTaskActive ? '◌' : idx + 1}
                        </div>
                        <span className={isTaskDone ? 'font-medium' : isTaskActive ? 'font-bold' : ''}>
                          {task}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-slate-400">
                        {isTaskDone ? 'VERIFIED' : isTaskActive ? 'PROCESSING' : 'PENDING'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Quick Context Tip */}
            <div className="p-3.5 rounded-2xl bg-indigo-950/30 border border-indigo-900/60 text-xs text-indigo-200 flex items-start gap-2.5">
              <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div className="leading-relaxed">
                <span className="font-bold">Architectural Note:</span> Open-MOSS performs continuous acoustic-linguistic consensus with zero third-party cloud data leaks, ensuring complete on-premise confidentiality and RFC-009 vector fidelity.
              </div>
            </div>
          </div>

          {/* Right Column: Live Logs Terminal & Execution State (5 Cols) */}
          <div className="lg:col-span-5 p-6 flex flex-col justify-between space-y-4 bg-slate-950/60">
            {/* Tab Selector: Live Logs vs Stage Telemetry */}
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-3">
                <div className="flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-teal-400" />
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    Pipeline Execution Logs
                  </span>
                </div>
                <div className="text-[11px] font-mono text-slate-400">
                  {logs.length} events logged
                </div>
              </div>

              {/* Log Stream Window */}
              <div className="rounded-2xl border border-slate-800 bg-slate-950 p-3.5 font-mono text-[11px] h-[340px] overflow-y-auto space-y-2 select-text shadow-inner">
                {logs.length === 0 ? (
                  <div className="text-slate-400 text-center py-12 flex flex-col items-center justify-center space-y-2">
                    <Loader2 className="w-5 h-5 animate-spin text-indigo-400" />
                    <span>Awaiting pipeline trigger and telemetry logs...</span>
                  </div>
                ) : (
                  logs.map((log) => {
                    const levelColors = {
                      info: 'text-slate-300',
                      success: 'text-emerald-400 font-semibold',
                      warning: 'text-amber-400',
                      diar: 'text-teal-300',
                      asr: 'text-indigo-300',
                      agent: 'text-purple-300'
                    };

                    return (
                      <div key={log.id} className="leading-relaxed break-words hover:bg-slate-900/50 p-1 rounded">
                        <span className="text-slate-400 mr-2">[{log.timestamp}]</span>
                        <span className={levelColors[log.level]}>{log.message}</span>
                      </div>
                    );
                  })
                )}
                <div ref={logsEndRef} />
              </div>
            </div>

            {/* Bottom Actions Deck & Next Step Triggers */}
            <div className="pt-2 border-t border-slate-800/80 flex flex-col sm:flex-row items-center justify-between gap-3">
              {/* Playback Controls */}
              <div className="flex items-center gap-2 w-full sm:w-auto">
                <button
                  type="button"
                  onClick={() => setIsPlaying(!isPlaying)}
                  disabled={isCompleted}
                  className={`px-3 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                    isPlaying
                      ? 'bg-amber-950/80 hover:bg-amber-900 border border-amber-800 text-amber-200'
                      : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/30'
                  }`}
                >
                  {isPlaying ? (
                    <>
                      <Pause className="w-3.5 h-3.5" />
                      <span>Pause</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5 fill-current" />
                      <span>Resume</span>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleReset}
                  className="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                  title="Re-run pipeline from Stage 1"
                >
                  <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
                  <span>Re-Run</span>
                </button>
              </div>

              {/* View Output Artifacts when Completed */}
              <div className="w-full sm:w-auto">
                {isCompleted && onViewIntelligence ? (
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      onViewIntelligence(meeting.id);
                    }}
                    className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold shadow-lg shadow-emerald-600/30 flex items-center justify-center gap-2 transition-all cursor-pointer"
                  >
                    <Sparkles className="w-4 h-4" />
                    <span>View Meeting Intelligence</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={onClose}
                    className="w-full sm:w-auto px-4 py-2 rounded-xl text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors"
                  >
                    Close Modal
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
