import React, { useState, useMemo } from 'react';
import {
  Sparkles,
  CheckCircle2,
  ListTodo,
  TrendingUp,
  AlertTriangle,
  FileCheck,
  User,
  Clock,
  ThumbsUp,
  Flame,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Radio,
  Activity,
  Volume2,
  Play,
  Pause,
  Edit3,
  Check,
  X,
  Search,
  Filter,
  Layers,
  Eye,
  AlertCircle,
  Gauge,
  HelpCircle,
  Languages,
  Workflow,
  GitBranch,
  Cpu,
  BarChart3,
  PieChart,
  Network,
  Zap,
  ShieldCheck,
  Database,
  XCircle
} from 'lucide-react';
import { MeetingIntelligence, ActionItemDef, SpeakerSegment, WordToken } from '../types';

interface IntelligenceViewerProps {
  intelligence: MeetingIntelligence | undefined;
  meetingTitle: string;
  onToggleActionItem?: (actionId: string) => void;
}

// Fallback speaker segments in case a custom meeting doesn't have pre-populated segments
const DEFAULT_FALLBACK_SEGMENTS: SpeakerSegment[] = [
  {
    id: 'seg-def-1',
    speaker: 'Speaker 1 (Lead)',
    speaker_id: 'spk_1',
    start_time: '00:00:15',
    end_time: '00:00:45',
    start_seconds: 15,
    end_seconds: 45,
    text: 'Welcome everyone. Today we are aligning on the architecture benchmarks and multi-agent blackboard requirements.',
    confidence: 0.96,
    acoustic_confidence: 0.98,
    language_code: 'en',
    language_label: 'English',
    has_overlap: false,
    needs_review: false,
    verified: true,
    words: [
      { word: 'Welcome', confidence: 0.98, start_ms: 15000, end_ms: 15400 },
      { word: 'everyone.', confidence: 0.99, start_ms: 15450, end_ms: 15900 },
      { word: 'Today', confidence: 0.97, start_ms: 16100, end_ms: 16400 },
      { word: 'we', confidence: 0.98, start_ms: 16450, end_ms: 16600 },
      { word: 'are', confidence: 0.99, start_ms: 16650, end_ms: 16800 },
      { word: 'aligning', confidence: 0.95, start_ms: 16850, end_ms: 17300 },
      { word: 'on', confidence: 0.98, start_ms: 17350, end_ms: 17500 },
      { word: 'the', confidence: 0.99, start_ms: 17550, end_ms: 17700 },
      { word: 'architecture', confidence: 0.96, start_ms: 17750, end_ms: 18400 },
      { word: 'benchmarks', confidence: 0.94, start_ms: 18450, end_ms: 19100 },
      { word: 'and', confidence: 0.97, start_ms: 19150, end_ms: 19300 },
      { word: 'multi-agent', confidence: 0.95, start_ms: 19350, end_ms: 20000 },
      { word: 'blackboard', confidence: 0.93, start_ms: 20050, end_ms: 20600 },
      { word: 'requirements.', confidence: 0.97, start_ms: 20650, end_ms: 21300 }
    ]
  },
  {
    id: 'seg-def-2',
    speaker: 'Speaker 2',
    speaker_id: 'spk_2',
    start_time: '00:00:46',
    end_time: '00:01:18',
    start_seconds: 46,
    end_seconds: 78,
    text: 'Humne Sarvam-1 model ko vLLM pe deploy kar diya hai, latency under 40ms aa rahi hai with Indic tokenizer.',
    confidence: 0.93,
    acoustic_confidence: 0.95,
    language_code: 'hi-en',
    language_label: 'Hinglish (Code-Switching)',
    has_overlap: false,
    needs_review: false,
    verified: true,
    words: [
      { word: 'Humne', confidence: 0.96, start_ms: 46000, end_ms: 46400 },
      { word: 'Sarvam-1', confidence: 0.91, start_ms: 46450, end_ms: 47100 },
      { word: 'model', confidence: 0.97, start_ms: 47150, end_ms: 47500 },
      { word: 'ko', confidence: 0.98, start_ms: 47550, end_ms: 47750 },
      { word: 'vLLM', confidence: 0.88, start_ms: 47800, end_ms: 48300 },
      { word: 'pe', confidence: 0.97, start_ms: 48350, end_ms: 48550 },
      { word: 'deploy', confidence: 0.96, start_ms: 48600, end_ms: 49100 },
      { word: 'kar', confidence: 0.98, start_ms: 49150, end_ms: 49350 },
      { word: 'diya', confidence: 0.97, start_ms: 49400, end_ms: 49700 },
      { word: 'hai,', confidence: 0.98, start_ms: 49750, end_ms: 50000 },
      { word: 'latency', confidence: 0.94, start_ms: 50300, end_ms: 50800 },
      { word: 'under', confidence: 0.96, start_ms: 50850, end_ms: 51200 },
      { word: '40ms', confidence: 0.90, start_ms: 51250, end_ms: 51750 },
      { word: 'aa', confidence: 0.95, start_ms: 51800, end_ms: 52000 },
      { word: 'rahi', confidence: 0.97, start_ms: 52050, end_ms: 52350 },
      { word: 'hai', confidence: 0.98, start_ms: 52400, end_ms: 52650 },
      { word: 'with', confidence: 0.97, start_ms: 52700, end_ms: 52950 },
      { word: 'Indic', confidence: 0.95, start_ms: 53000, end_ms: 53400 },
      { word: 'tokenizer.', confidence: 0.94, start_ms: 53450, end_ms: 54100 }
    ]
  },
  {
    id: 'seg-def-3',
    speaker: 'Speaker 3 [Remote Audio]',
    speaker_id: 'spk_3',
    start_time: '00:01:20',
    end_time: '00:01:45',
    start_seconds: 80,
    end_seconds: 105,
    text: '[acoustic reverberation / low packet rate] ...Qdrant vector collections mein sharding policy configure karni hogi for tenant isolation.',
    confidence: 0.64,
    acoustic_confidence: 0.58,
    language_code: 'hi-en',
    language_label: 'Hinglish (Degraded Acoustic)',
    has_overlap: true,
    needs_review: true,
    verified: false,
    words: [
      { word: '[acoustic', confidence: 0.44, start_ms: 80000, end_ms: 80600 },
      { word: 'reverberation', confidence: 0.41, start_ms: 80650, end_ms: 81400 },
      { word: '/', confidence: 0.50, start_ms: 81450, end_ms: 81600 },
      { word: 'low', confidence: 0.48, start_ms: 81650, end_ms: 82000 },
      { word: 'packet', confidence: 0.43, start_ms: 82050, end_ms: 82500 },
      { word: 'rate]', confidence: 0.42, start_ms: 82550, end_ms: 83000 },
      { word: '...Qdrant', confidence: 0.68, start_ms: 83400, end_ms: 84000 },
      { word: 'vector', confidence: 0.74, start_ms: 84050, end_ms: 84500 },
      { word: 'collections', confidence: 0.72, start_ms: 84550, end_ms: 85200 },
      { word: 'mein', confidence: 0.88, start_ms: 85250, end_ms: 85500 },
      { word: 'sharding', confidence: 0.69, start_ms: 85550, end_ms: 86100 },
      { word: 'policy', confidence: 0.78, start_ms: 86150, end_ms: 86600 },
      { word: 'configure', confidence: 0.75, start_ms: 86650, end_ms: 87200 },
      { word: 'karni', confidence: 0.84, start_ms: 87250, end_ms: 87600 },
      { word: 'hogi', confidence: 0.86, start_ms: 87650, end_ms: 88000 },
      { word: 'for', confidence: 0.91, start_ms: 88050, end_ms: 88300 },
      { word: 'tenant', confidence: 0.77, start_ms: 88350, end_ms: 88800 },
      { word: 'isolation.', confidence: 0.79, start_ms: 88850, end_ms: 89450 }
    ]
  }
];

export const IntelligenceViewer: React.FC<IntelligenceViewerProps> = ({
  intelligence,
  meetingTitle,
  onToggleActionItem
}) => {
  const [activeSection, setActiveSection] = useState<
    'segments' | 'summary' | 'decisions' | 'action_items' | 'topics' | 'risks' | 'ace_blackboard' | 'analytics'
  >('segments');

  // Segments & Heatmap UI States
  const [segments, setSegments] = useState<SpeakerSegment[]>(() => {
    return intelligence?.speaker_segments && intelligence.speaker_segments.length > 0
      ? intelligence.speaker_segments
      : DEFAULT_FALLBACK_SEGMENTS;
  });

  const [selectedSpeaker, setSelectedSpeaker] = useState<string>('all');
  const [confidenceFilter, setConfidenceFilter] = useState<'all' | 'low' | 'medium_low' | 'overlap' | 'needs_review'>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [highlightedSegmentId, setHighlightedSegmentId] = useState<string | null>(null);
  const [activePlayingSegmentId, setActivePlayingSegmentId] = useState<string | null>(null);
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editText, setEditText] = useState<string>('');
  const [selectedWordToken, setSelectedWordToken] = useState<{ word: WordToken; speaker: string } | null>(null);

  // Sync state when intelligence prop updates
  React.useEffect(() => {
    if (intelligence?.speaker_segments && intelligence.speaker_segments.length > 0) {
      setSegments(intelligence.speaker_segments);
    } else {
      setSegments(DEFAULT_FALLBACK_SEGMENTS);
    }
  }, [intelligence]);

  // Derived statistics for confidence heatmap
  const confidenceStats = useMemo(() => {
    if (segments.length === 0) {
      return { avg: 0, highCount: 0, medCount: 0, lowCount: 0, overlapCount: 0, reviewNeededCount: 0 };
    }
    let totalConf = 0;
    let highCount = 0; // >= 0.90
    let medCount = 0;  // 0.75 - 0.89
    let lowCount = 0;  // < 0.75
    let overlapCount = 0;
    let reviewNeededCount = 0;

    segments.forEach((seg) => {
      totalConf += seg.confidence;
      if (seg.confidence >= 0.9) {
        highCount++;
      } else if (seg.confidence >= 0.75) {
        medCount++;
      } else {
        lowCount++;
      }
      if (seg.has_overlap) overlapCount++;
      if (seg.needs_review || seg.confidence < 0.75) reviewNeededCount++;
    });

    const avg = totalConf / segments.length;
    return {
      avg,
      highCount,
      medCount,
      lowCount,
      overlapCount,
      reviewNeededCount,
      highPct: Math.round((highCount / segments.length) * 100),
      medPct: Math.round((medCount / segments.length) * 100),
      lowPct: Math.round((lowCount / segments.length) * 100)
    };
  }, [segments]);

  // Unique list of speakers
  const speakers = useMemo(() => {
    const set = new Set<string>();
    segments.forEach((s) => set.add(s.speaker));
    return Array.from(set);
  }, [segments]);

  // Filtered segments
  const filteredSegments = useMemo(() => {
    return segments.filter((seg) => {
      // Speaker filter
      if (selectedSpeaker !== 'all' && seg.speaker !== selectedSpeaker) {
        return false;
      }
      // Confidence filter
      if (confidenceFilter === 'low' && seg.confidence >= 0.75) {
        return false;
      }
      if (confidenceFilter === 'medium_low' && seg.confidence >= 0.90) {
        return false;
      }
      if (confidenceFilter === 'overlap' && !seg.has_overlap) {
        return false;
      }
      if (confidenceFilter === 'needs_review' && !seg.needs_review && seg.confidence >= 0.75) {
        return false;
      }
      // Text query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesText = seg.text.toLowerCase().includes(q);
        const matchesSpeaker = seg.speaker.toLowerCase().includes(q);
        const matchesLang = seg.language_label.toLowerCase().includes(q);
        if (!matchesText && !matchesSpeaker && !matchesLang) {
          return false;
        }
      }
      return true;
    });
  }, [segments, selectedSpeaker, confidenceFilter, searchQuery]);

  // Toggle verification status on a segment
  const handleToggleVerify = (segmentId: string) => {
    setSegments((prev) =>
      prev.map((s) => {
        if (s.id === segmentId) {
          const isNowVerified = !s.verified;
          return {
            ...s,
            verified: isNowVerified,
            needs_review: isNowVerified ? false : s.needs_review
          };
        }
        return s;
      })
    );
  };

  // Start editing segment text
  const handleStartEdit = (seg: SpeakerSegment) => {
    setEditingSegmentId(seg.id);
    setEditText(seg.text);
  };

  // Save edited segment text
  const handleSaveEdit = (segmentId: string) => {
    setSegments((prev) =>
      prev.map((s) => {
        if (s.id === segmentId) {
          return {
            ...s,
            text: editText,
            verified: true,
            needs_review: false,
            confidence: Math.max(s.confidence, 0.95) // manual verification bumps confidence
          };
        }
        return s;
      })
    );
    setEditingSegmentId(null);
  };

  // Toggle playback simulation
  const handleTogglePlayback = (segmentId: string) => {
    if (activePlayingSegmentId === segmentId) {
      setActivePlayingSegmentId(null);
    } else {
      setActivePlayingSegmentId(segmentId);
      // Auto stop after 4 seconds
      setTimeout(() => {
        setActivePlayingSegmentId((cur) => (cur === segmentId ? null : cur));
      }, 4000);
    }
  };

  // Jump to first low confidence segment
  const handleJumpToLowConfidence = () => {
    const lowSeg = segments.find((s) => s.confidence < 0.75 || s.needs_review);
    if (lowSeg) {
      setHighlightedSegmentId(lowSeg.id);
      setSelectedSpeaker('all');
      setConfidenceFilter('all');
      const el = document.getElementById(`segment-card-${lowSeg.id}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  };

  // Helper for color coding confidence
  const getConfidenceBadge = (confidence: number) => {
    if (confidence >= 0.9) {
      return {
        bg: 'bg-emerald-950/80',
        text: 'text-emerald-400',
        border: 'border-emerald-800/80',
        label: 'High Confidence',
        color: '#10b981'
      };
    }
    if (confidence >= 0.75) {
      return {
        bg: 'bg-amber-950/80',
        text: 'text-amber-400',
        border: 'border-amber-800/80',
        label: 'Moderate Confidence',
        color: '#f59e0b'
      };
    }
    return {
      bg: 'bg-rose-950/90',
      text: 'text-rose-400',
      border: 'border-rose-800',
      label: 'Low / Review Needed',
      color: '#f43f5e'
    };
  };

  // Helper for speaker color tags
  const getSpeakerColor = (speaker: string) => {
    if (speaker.includes('Niti')) return 'bg-cyan-950 text-cyan-400 border-cyan-800';
    if (speaker.includes('Ayush')) return 'bg-indigo-950 text-indigo-400 border-indigo-800';
    if (speaker.includes('Sneha')) return 'bg-purple-950 text-purple-400 border-purple-800';
    if (speaker.includes('Bhavya')) return 'bg-amber-950 text-amber-400 border-amber-800';
    if (speaker.includes('Instructor')) return 'bg-rose-950 text-rose-400 border-rose-800';
    return 'bg-neutral-800 text-neutral-300 border-neutral-700';
  };

  if (!intelligence) {
    return (
      <div className="bg-neutral-900/60 p-8 rounded-xl border border-neutral-800 text-center space-y-3">
        <Sparkles className="w-8 h-8 text-neutral-600 mx-auto" />
        <h3 className="text-sm font-semibold text-white">No Intelligence Extracted Yet</h3>
        <p className="text-xs text-neutral-400 max-w-md mx-auto">
          Upload audio or select a meeting in &apos;completed&apos; status to review synthesis from the Adaptive Blackboard &amp; Collaboration Engine (ACE).
        </p>
      </div>
    );
  }

  return (
    <div id="intelligence-viewer" className="space-y-6">
      {/* Overview Card */}
      <div className="bg-neutral-900/60 p-5 rounded-xl border border-neutral-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-neutral-800 pb-4">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-white tracking-tight">{meetingTitle}</h2>
              <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-950 text-indigo-400 border border-indigo-800 flex items-center">
                <Sparkles className="w-3 h-3 mr-1" />
                Synthesis Confidence: {(intelligence.confidence_score * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-xs text-neutral-400 mt-0.5">
              Multi-Agent Acoustic &amp; Diarization Intelligence (RO-01 to RO-06 Verification Engine)
            </p>
          </div>

          {/* Mini Stats Badges */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="px-2.5 py-1 rounded bg-neutral-950 border border-neutral-800 text-neutral-300 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-cyan-400" />
              <strong>{segments.length}</strong> Segments
            </span>
            <span className="px-2.5 py-1 rounded bg-neutral-950 border border-neutral-800 text-neutral-300">
              <strong>{intelligence.decisions.length}</strong> Decisions
            </span>
            <span className="px-2.5 py-1 rounded bg-neutral-950 border border-neutral-800 text-neutral-300">
              <strong>{intelligence.action_items.length}</strong> Action Items
            </span>
            <span className="px-2.5 py-1 rounded bg-neutral-950 border border-neutral-800 text-neutral-300">
              <strong>{intelligence.risks.length}</strong> Risks
            </span>
          </div>
        </div>

        {/* Section Navigation Buttons */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <button
            id="tab-speaker-segments"
            onClick={() => setActiveSection('segments')}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'segments'
                ? 'bg-amber-500 text-black shadow-sm font-bold'
                : 'bg-neutral-950 text-neutral-300 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <Gauge className="w-3.5 h-3.5" />
            Speaker Segments &amp; Confidence Heatmap ({segments.length})
            {confidenceStats.lowCount > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-rose-600 text-white text-[10px] font-bold">
                {confidenceStats.lowCount} alert
              </span>
            )}
          </button>

          <button
            id="tab-summary"
            onClick={() => setActiveSection('summary')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'summary'
                ? 'bg-indigo-600 text-white'
                : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            Executive Summary
          </button>

          <button
            id="tab-decisions"
            onClick={() => setActiveSection('decisions')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'decisions'
                ? 'bg-indigo-600 text-white'
                : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            Decisions ({intelligence.decisions.length})
          </button>

          <button
            id="tab-action-items"
            onClick={() => setActiveSection('action_items')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'action_items'
                ? 'bg-indigo-600 text-white'
                : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <ListTodo className="w-3.5 h-3.5 text-indigo-400" />
            Action Items ({intelligence.action_items.length})
          </button>

          <button
            id="tab-topics"
            onClick={() => setActiveSection('topics')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'topics'
                ? 'bg-indigo-600 text-white'
                : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5 text-purple-400" />
            Topics &amp; Sentiment
          </button>

          <button
            id="tab-risks"
            onClick={() => setActiveSection('risks')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'risks'
                ? 'bg-indigo-600 text-white'
                : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
            Operational Risks ({intelligence.risks.length})
          </button>

          <button
            id="tab-ace-blackboard"
            onClick={() => setActiveSection('ace_blackboard')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'ace_blackboard'
                ? 'bg-indigo-600 text-white shadow-sm font-semibold'
                : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <Workflow className="w-3.5 h-3.5 text-cyan-400" />
            ACE Blackboard &amp; 13-Module Pipeline
          </button>

          <button
            id="tab-mae-analytics"
            onClick={() => setActiveSection('analytics')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 whitespace-nowrap ${
              activeSection === 'analytics'
                ? 'bg-indigo-600 text-white shadow-sm font-semibold'
                : 'bg-neutral-950 text-neutral-400 hover:bg-neutral-800 border border-neutral-800'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5 text-emerald-400" />
            Meeting Analytics Engine (MAE)
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION: SPEAKER SEGMENTS & CONFIDENCE HEATMAP */}
      {/* ========================================================================= */}
      {activeSection === 'segments' && (
        <div className="space-y-5">
          {/* Top Visual Heatmap & Confidence Gauge Dashboard */}
          <div className="bg-neutral-900/50 p-5 rounded-xl border border-neutral-800 space-y-5">
            {/* Top row: Gauge + Breakdown + Quick Audit Callout */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
              {/* Dial / Circular Gauge for Overall Confidence */}
              <div className="md:col-span-4 bg-neutral-950/70 p-4 rounded-xl border border-neutral-800 flex items-center space-x-4">
                <div className="relative w-20 h-20 flex items-center justify-center shrink-0">
                  <svg className="w-20 h-20 transform -rotate-90" viewBox="0 0 36 36">
                    <path
                      className="text-neutral-800"
                      strokeWidth="3.5"
                      stroke="currentColor"
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                    <path
                      className={`${
                        confidenceStats.avg >= 0.9
                          ? 'text-emerald-500'
                          : confidenceStats.avg >= 0.75
                          ? 'text-amber-500'
                          : 'text-rose-500'
                      }`}
                      strokeDasharray={`${confidenceStats.avg * 100}, 100`}
                      strokeWidth="3.5"
                      strokeLinecap="round"
                      stroke="currentColor"
                      fill="none"
                      d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    />
                  </svg>
                  <div className="absolute flex flex-col items-center justify-center text-center">
                    <span className="text-base font-extrabold text-white font-mono leading-none">
                      {(confidenceStats.avg * 100).toFixed(0)}%
                    </span>
                    <span className="text-[9px] text-neutral-400 uppercase font-semibold">Mean Conf</span>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-xs font-bold text-white flex items-center gap-1.5">
                    <Gauge className="w-3.5 h-3.5 text-amber-400" />
                    ASR Confidence Score
                  </div>
                  <p className="text-[11px] text-neutral-400 leading-snug">
                    Posterior acoustic &amp; linguistic confidence across {segments.length} speaker turns.
                  </p>
                  <span
                    className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                      confidenceStats.avg >= 0.9
                        ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                        : 'bg-amber-950 text-amber-400 border-amber-800'
                    }`}
                  >
                    {confidenceStats.avg >= 0.9 ? 'High Quality Index' : 'Moderate Quality Index'}
                  </span>
                </div>
              </div>

              {/* Distribution Breakdown Bar */}
              <div className="md:col-span-5 bg-neutral-950/70 p-4 rounded-xl border border-neutral-800 space-y-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-white">Segment Confidence Distribution</span>
                  <span className="text-[10px] text-neutral-500 font-mono">RO-06 Verification</span>
                </div>

                {/* Stacked Percentage Bar */}
                <div className="h-3.5 w-full bg-neutral-900 rounded-full overflow-hidden flex border border-neutral-800">
                  <div
                    style={{ width: `${confidenceStats.highPct}%` }}
                    className="bg-emerald-500 h-full transition-all duration-300 cursor-pointer hover:opacity-80"
                    title={`High (>90%): ${confidenceStats.highCount} segments (${confidenceStats.highPct}%)`}
                    onClick={() => setConfidenceFilter('all')}
                  />
                  <div
                    style={{ width: `${confidenceStats.medPct}%` }}
                    className="bg-amber-500 h-full transition-all duration-300 cursor-pointer hover:opacity-80"
                    title={`Moderate (75-90%): ${confidenceStats.medCount} segments (${confidenceStats.medPct}%)`}
                    onClick={() => setConfidenceFilter('medium_low')}
                  />
                  <div
                    style={{ width: `${confidenceStats.lowPct}%` }}
                    className="bg-rose-500 h-full transition-all duration-300 cursor-pointer hover:opacity-80"
                    title={`Low (<75%): ${confidenceStats.lowCount} segments (${confidenceStats.lowPct}%)`}
                    onClick={() => setConfidenceFilter('low')}
                  />
                </div>

                {/* Legend & Stats */}
                <div className="grid grid-cols-3 gap-2 text-[11px] pt-1">
                  <button
                    onClick={() => setConfidenceFilter('all')}
                    className="text-left group hover:opacity-80 transition-opacity"
                  >
                    <div className="flex items-center space-x-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0" />
                      <span className="text-neutral-400 text-[10px]">High (&gt;90%)</span>
                    </div>
                    <span className="font-bold text-white pl-4 text-xs font-mono">{confidenceStats.highCount} turns</span>
                  </button>

                  <button
                    onClick={() => setConfidenceFilter('medium_low')}
                    className="text-left group hover:opacity-80 transition-opacity"
                  >
                    <div className="flex items-center space-x-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500 shrink-0" />
                      <span className="text-neutral-400 text-[10px]">Med (75-90%)</span>
                    </div>
                    <span className="font-bold text-white pl-4 text-xs font-mono">{confidenceStats.medCount} turns</span>
                  </button>

                  <button
                    onClick={() => setConfidenceFilter('low')}
                    className="text-left group hover:opacity-80 transition-opacity"
                  >
                    <div className="flex items-center space-x-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500 shrink-0" />
                      <span className="text-neutral-400 text-[10px]">Low (&lt;75%)</span>
                    </div>
                    <span className="font-bold text-rose-400 pl-4 text-xs font-mono">{confidenceStats.lowCount} turns</span>
                  </button>
                </div>
              </div>

              {/* Quick Action / Review Alert Box */}
              <div className="md:col-span-3 bg-neutral-950/70 p-4 rounded-xl border border-neutral-800 flex flex-col justify-between space-y-3 h-full">
                <div className="space-y-1">
                  <div className="flex items-center space-x-1.5 text-xs font-bold text-amber-400">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>Human-in-the-Loop Review</span>
                  </div>
                  <p className="text-[11px] text-neutral-400 leading-snug">
                    {confidenceStats.lowCount > 0
                      ? `${confidenceStats.lowCount} low-confidence turn(s) flagged for acoustic verification.`
                      : 'All segments exceed benchmark confidence thresholds.'}
                  </p>
                </div>

                {confidenceStats.lowCount > 0 ? (
                  <button
                    id="btn-jump-low-confidence"
                    onClick={handleJumpToLowConfidence}
                    className="w-full py-1.5 px-3 rounded-lg bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    Jump to Low-Confidence Turn
                  </button>
                ) : (
                  <div className="text-[10px] text-emerald-400 font-semibold flex items-center gap-1 bg-emerald-950/40 p-1.5 rounded border border-emerald-900/50">
                    <CheckCircle2 className="w-3 h-3" />
                    All turns verified
                  </div>
                )}
              </div>
            </div>

            {/* Interactive Timeline Heatmap Ribbon */}
            <div className="space-y-2 pt-2 border-t border-neutral-800/80">
              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center space-x-2">
                  <Activity className="w-3.5 h-3.5 text-amber-400" />
                  <span className="font-semibold text-white">Interactive Session Heatmap Ribbon</span>
                  <span className="text-[10px] text-neutral-500 hidden sm:inline">
                    (Click any block to navigate to that segment)
                  </span>
                </div>
                <span className="text-[11px] font-mono text-neutral-400">
                  {segments[0]?.start_time || '00:00:00'} &rarr; {segments[segments.length - 1]?.end_time || '00:10:00'}
                </span>
              </div>

              {/* Heatmap Blocks Ribbon */}
              <div className="relative w-full bg-neutral-950 p-2 rounded-xl border border-neutral-800 flex gap-1.5 overflow-x-auto">
                {segments.map((seg, idx) => {
                  const confMeta = getConfidenceBadge(seg.confidence);
                  const isHighlighted = highlightedSegmentId === seg.id;
                  const isPlaying = activePlayingSegmentId === seg.id;

                  return (
                    <button
                      key={`heatmap-${seg.id}`}
                      onClick={() => {
                        setHighlightedSegmentId(seg.id);
                        const el = document.getElementById(`segment-card-${seg.id}`);
                        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      }}
                      className={`relative flex-1 min-w-[55px] h-9 rounded-lg transition-all duration-200 flex flex-col items-center justify-center p-1 border text-center ${
                        isHighlighted
                          ? 'ring-2 ring-amber-400 scale-105 z-10'
                          : 'hover:scale-102 hover:brightness-110'
                      } ${
                        seg.confidence >= 0.9
                          ? 'bg-emerald-950/70 border-emerald-800/80 text-emerald-300'
                          : seg.confidence >= 0.75
                          ? 'bg-amber-950/70 border-amber-800/80 text-amber-300'
                          : 'bg-rose-950/90 border-rose-700 text-rose-200 animate-pulse'
                      }`}
                      title={`${seg.speaker} (${seg.start_time} - ${seg.end_time}) | Confidence: ${(
                        seg.confidence * 100
                      ).toFixed(0)}% | ${seg.language_label}`}
                    >
                      <div className="text-[9px] font-mono font-bold leading-none truncate w-full">
                        {seg.start_time.substring(3)}
                      </div>
                      <div className="text-[10px] font-extrabold font-mono mt-0.5 leading-none">
                        {(seg.confidence * 100).toFixed(0)}%
                      </div>

                      {/* Overlap & Warning Indicators */}
                      {seg.has_overlap && (
                        <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-amber-400 ring-1 ring-black" />
                      )}
                      {isPlaying && (
                        <span className="absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Controls Bar: Speaker Filters, Confidence Toggles, Keyword Search */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-neutral-900/40 p-4 rounded-xl border border-neutral-800">
            {/* Left: Filter Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center space-x-1 text-xs text-neutral-400 mr-1">
                <Filter className="w-3.5 h-3.5 text-neutral-500" />
                <span className="font-semibold text-neutral-300">Filter:</span>
              </div>

              <button
                onClick={() => setConfidenceFilter('all')}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                  confidenceFilter === 'all'
                    ? 'bg-neutral-700 text-white font-semibold'
                    : 'bg-neutral-950 text-neutral-400 hover:text-white border border-neutral-800'
                }`}
              >
                All ({segments.length})
              </button>

              <button
                onClick={() => setConfidenceFilter('low')}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors flex items-center gap-1 ${
                  confidenceFilter === 'low'
                    ? 'bg-rose-900 text-rose-200 border border-rose-700 font-bold'
                    : 'bg-neutral-950 text-rose-400/90 hover:bg-neutral-800 border border-neutral-800'
                }`}
              >
                <AlertTriangle className="w-3 h-3 text-rose-400" />
                Low (&lt;75%) ({confidenceStats.lowCount})
              </button>

              <button
                onClick={() => setConfidenceFilter('medium_low')}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                  confidenceFilter === 'medium_low'
                    ? 'bg-amber-900 text-amber-200 border border-amber-700 font-bold'
                    : 'bg-neutral-950 text-amber-400/90 hover:bg-neutral-800 border border-neutral-800'
                }`}
              >
                Moderate &amp; Low (&lt;90%) ({confidenceStats.medCount + confidenceStats.lowCount})
              </button>

              <button
                onClick={() => setConfidenceFilter('overlap')}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors flex items-center gap-1 ${
                  confidenceFilter === 'overlap'
                    ? 'bg-indigo-900 text-indigo-200 border border-indigo-700 font-bold'
                    : 'bg-neutral-950 text-indigo-400 hover:bg-neutral-800 border border-neutral-800'
                }`}
              >
                <Layers className="w-3 h-3" />
                Overlapping Speech ({confidenceStats.overlapCount})
              </button>
            </div>

            {/* Right: Speaker Dropdown & Keyword Search */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Speaker Select */}
              <div className="relative">
                <select
                  value={selectedSpeaker}
                  onChange={(e) => setSelectedSpeaker(e.target.value)}
                  className="bg-neutral-950 text-neutral-200 text-xs rounded-lg border border-neutral-800 px-2.5 py-1.5 pr-7 focus:outline-none focus:border-indigo-500"
                >
                  <option value="all">All Speakers ({speakers.length})</option>
                  {speakers.map((spk) => (
                    <option key={spk} value={spk}>
                      {spk}
                    </option>
                  ))}
                </select>
              </div>

              {/* Search input */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-2.5 top-1/2 transform -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search in transcript..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="bg-neutral-950 text-neutral-200 text-xs rounded-lg border border-neutral-800 pl-8 pr-3 py-1.5 w-44 sm:w-56 focus:outline-none focus:border-indigo-500 placeholder-neutral-500"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2 top-1/2 transform -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
                  >
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Word Token Detail Inspector Drawer (if a word is clicked) */}
          {selectedWordToken && (
            <div className="bg-neutral-950 p-3.5 rounded-xl border border-indigo-900/60 flex items-center justify-between text-xs animate-in fade-in">
              <div className="flex items-center space-x-3">
                <span className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
                <div>
                  <span className="text-neutral-400 font-mono text-[11px]">Word Token Acoustic Inspection:</span>{' '}
                  <strong className="text-white font-mono text-sm px-1.5 py-0.5 bg-neutral-900 rounded border border-neutral-800">
                    &quot;{selectedWordToken.word.word}&quot;
                  </strong>{' '}
                  <span className="text-neutral-400 ml-2">
                    Speaker: <strong className="text-indigo-400">{selectedWordToken.speaker}</strong> &bull; Onset:{' '}
                    <span className="font-mono text-neutral-300">{selectedWordToken.word.start_ms}ms</span> &bull;
                    Offset: <span className="font-mono text-neutral-300">{selectedWordToken.word.end_ms}ms</span> &bull;
                    Duration:{' '}
                    <span className="font-mono text-neutral-300">
                      {selectedWordToken.word.end_ms - selectedWordToken.word.start_ms}ms
                    </span>
                  </span>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${
                    selectedWordToken.word.confidence >= 0.9
                      ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
                      : selectedWordToken.word.confidence >= 0.75
                      ? 'bg-amber-950 text-amber-400 border-amber-800'
                      : 'bg-rose-950 text-rose-400 border-rose-800'
                  }`}
                >
                  Word Confidence: {(selectedWordToken.word.confidence * 100).toFixed(0)}%
                </span>
                <button
                  onClick={() => setSelectedWordToken(null)}
                  className="text-neutral-500 hover:text-white p-1"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}

          {/* List of Speaker Segment Cards */}
          <div className="space-y-3.5">
            {filteredSegments.length === 0 ? (
              <div className="bg-neutral-900/40 p-8 rounded-xl border border-neutral-800 text-center space-y-2">
                <Search className="w-6 h-6 text-neutral-600 mx-auto" />
                <h4 className="text-xs font-semibold text-white">No Speaker Segments Match Filter</h4>
                <p className="text-[11px] text-neutral-400">
                  Try clearing your search query or switching confidence filters.
                </p>
                <button
                  onClick={() => {
                    setSelectedSpeaker('all');
                    setConfidenceFilter('all');
                    setSearchQuery('');
                  }}
                  className="text-xs text-indigo-400 hover:underline pt-1"
                >
                  Reset all filters
                </button>
              </div>
            ) : (
              filteredSegments.map((seg) => {
                const confMeta = getConfidenceBadge(seg.confidence);
                const isPlaying = activePlayingSegmentId === seg.id;
                const isEditing = editingSegmentId === seg.id;
                const isHighlighted = highlightedSegmentId === seg.id;
                const speakerColorClass = getSpeakerColor(seg.speaker);

                return (
                  <div
                    key={seg.id}
                    id={`segment-card-${seg.id}`}
                    className={`p-4 rounded-xl border transition-all duration-200 space-y-3 ${
                      isHighlighted
                        ? 'bg-neutral-900 border-amber-500 shadow-md ring-1 ring-amber-500/50'
                        : seg.confidence < 0.75
                        ? 'bg-neutral-900/60 border-rose-900/70 hover:border-rose-700'
                        : 'bg-neutral-900/40 border-neutral-800 hover:border-neutral-700'
                    }`}
                  >
                    {/* Segment Header */}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Speaker Badge */}
                        <span className={`px-2.5 py-0.5 rounded-md text-xs font-bold border flex items-center gap-1.5 ${speakerColorClass}`}>
                          <User className="w-3 h-3" />
                          {seg.speaker}
                        </span>

                        {/* Timestamp Range */}
                        <span className="text-[11px] font-mono text-neutral-400 bg-neutral-950 px-2 py-0.5 rounded border border-neutral-800/80 flex items-center gap-1">
                          <Clock className="w-3 h-3 text-neutral-500" />
                          {seg.start_time} - {seg.end_time} ({seg.end_seconds - seg.start_seconds}s)
                        </span>

                        {/* Language & Code-Switching Tag */}
                        <span className="text-[10px] font-medium text-neutral-400 bg-neutral-950 px-2 py-0.5 rounded border border-neutral-800/80 flex items-center gap-1">
                          <Languages className="w-3 h-3 text-indigo-400" />
                          {seg.language_label}
                        </span>

                        {/* Overlap Indicator */}
                        {seg.has_overlap && (
                          <span className="text-[10px] font-bold bg-amber-950 text-amber-300 border border-amber-800 px-2 py-0.5 rounded flex items-center gap-1">
                            <Layers className="w-3 h-3" />
                            Overlapping Speech (RO-04)
                          </span>
                        )}

                        {/* Human Verification Badge */}
                        {seg.verified && (
                          <span className="text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-900 px-2 py-0.5 rounded flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            Human Verified
                          </span>
                        )}
                      </div>

                      {/* Right: Confidence Metric & Micro-Gauge */}
                      <div className="flex items-center space-x-2">
                        {/* Acoustic Confidence */}
                        {seg.acoustic_confidence && (
                          <span className="text-[10px] text-neutral-500 font-mono hidden md:inline">
                            Acoustic: {(seg.acoustic_confidence * 100).toFixed(0)}%
                          </span>
                        )}

                        {/* Turn Confidence Gauge Pill */}
                        <div
                          className={`px-2.5 py-1 rounded-lg text-xs font-bold font-mono border flex items-center space-x-1.5 ${confMeta.bg} ${confMeta.text} ${confMeta.border}`}
                          title={`Confidence: ${(seg.confidence * 100).toFixed(1)}%`}
                        >
                          <Gauge className="w-3.5 h-3.5" />
                          <span>{(seg.confidence * 100).toFixed(0)}% Conf</span>
                        </div>
                      </div>
                    </div>

                    {/* Segment Utterance / Word Token Heatmap */}
                    {isEditing ? (
                      <div className="space-y-2 pt-1">
                        <textarea
                          value={editText}
                          onChange={(e) => setEditText(e.target.value)}
                          rows={2}
                          className="w-full bg-neutral-950 text-neutral-100 text-xs rounded-lg border border-neutral-700 p-2.5 focus:outline-none focus:border-amber-500 font-sans leading-relaxed"
                        />
                        <div className="flex items-center space-x-2 justify-end">
                          <button
                            onClick={() => setEditingSegmentId(null)}
                            className="px-2.5 py-1 rounded text-xs text-neutral-400 hover:text-white bg-neutral-950 border border-neutral-800"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleSaveEdit(seg.id)}
                            className="px-3 py-1 rounded text-xs font-semibold text-black bg-amber-400 hover:bg-amber-300 flex items-center gap-1 shadow-sm"
                          >
                            <Check className="w-3.5 h-3.5" />
                            Save Transcript Correction
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="bg-neutral-950/80 p-3 rounded-lg border border-neutral-800/80 space-y-2">
                        {/* Render Word-Level Token Heatmap if tokens exist, otherwise text */}
                        <div className="text-xs text-neutral-200 leading-relaxed font-sans flex flex-wrap gap-x-1.5 gap-y-1 items-center">
                          {seg.words && seg.words.length > 0 ? (
                            seg.words.map((w, wIdx) => {
                              const isLowWord = w.confidence < 0.75;
                              const isMedWord = w.confidence >= 0.75 && w.confidence < 0.9;
                              const isSelected = selectedWordToken?.word.word === w.word && selectedWordToken?.word.start_ms === w.start_ms;

                              return (
                                <span
                                  key={`word-tok-${seg.id}-${w.start_ms}-${w.word}-${wIdx}`}
                                  onClick={() => setSelectedWordToken({ word: w, speaker: seg.speaker })}
                                  className={`cursor-pointer px-1 py-0.5 rounded transition-all ${
                                    isSelected
                                      ? 'ring-2 ring-indigo-400 font-bold bg-indigo-950 text-indigo-200'
                                      : isLowWord
                                      ? 'bg-rose-950/90 text-rose-300 border border-rose-800/90 font-semibold underline decoration-rose-500 hover:bg-rose-900'
                                      : isMedWord
                                      ? 'bg-amber-950/50 text-amber-200/90 border border-amber-900/60 hover:bg-amber-950'
                                      : 'hover:bg-neutral-800 text-neutral-200'
                                  }`}
                                  title={`"${w.word}" | Word Confidence: ${(w.confidence * 100).toFixed(0)}% | Onset: ${w.start_ms}ms`}
                                >
                                  {w.word}
                                  {isLowWord && (
                                    <span className="ml-1 text-[9px] font-mono text-rose-400 font-extrabold">
                                      {(w.confidence * 100).toFixed(0)}%
                                    </span>
                                  )}
                                </span>
                              );
                            })
                          ) : (
                            <span>{seg.text}</span>
                          )}
                        </div>

                        {/* Low-confidence explanation hint */}
                        {seg.confidence < 0.75 && (
                          <div className="text-[11px] text-rose-400/90 font-medium flex items-center gap-1.5 pt-1 border-t border-rose-950/80">
                            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                            <span>
                              Acoustic confidence fell below 75% due to background acoustic interference or overlapping cross-talk. Please verify tokens.
                            </span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Segment Action Toolbar */}
                    <div className="flex items-center justify-between pt-1 text-xs">
                      {/* Audio Playback Simulation */}
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleTogglePlayback(seg.id)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-medium border flex items-center space-x-1.5 transition-colors ${
                            isPlaying
                              ? 'bg-cyan-950 text-cyan-300 border-cyan-800'
                              : 'bg-neutral-950 text-neutral-400 hover:text-white border-neutral-800'
                          }`}
                        >
                          {isPlaying ? (
                            <>
                              <Pause className="w-3 h-3 text-cyan-400" />
                              <span>Playing Turn...</span>
                              <span className="flex space-x-0.5 ml-1">
                                <span className="w-0.5 h-2 bg-cyan-400 animate-pulse" />
                                <span className="w-0.5 h-3 bg-cyan-400 animate-pulse delay-75" />
                                <span className="w-0.5 h-1.5 bg-cyan-400 animate-pulse delay-150" />
                              </span>
                            </>
                          ) : (
                            <>
                              <Play className="w-3 h-3 text-neutral-400" />
                              <span>Play Audio Segment</span>
                            </>
                          )}
                        </button>
                      </div>

                      {/* Edit & Verify Buttons */}
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleStartEdit(seg)}
                          className="px-2.5 py-1 rounded-lg text-[11px] font-medium bg-neutral-950 hover:bg-neutral-800 text-neutral-400 hover:text-neutral-200 border border-neutral-800 flex items-center space-x-1"
                        >
                          <Edit3 className="w-3 h-3" />
                          <span>Correct Text</span>
                        </button>

                        <button
                          onClick={() => handleToggleVerify(seg.id)}
                          className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border flex items-center space-x-1 transition-colors ${
                            seg.verified
                              ? 'bg-emerald-950 text-emerald-400 border-emerald-800 hover:bg-emerald-900'
                              : 'bg-neutral-950 text-neutral-300 hover:bg-neutral-800 border-neutral-800'
                          }`}
                        >
                          <CheckCircle2 className="w-3 h-3" />
                          <span>{seg.verified ? 'Verified ✓' : 'Confirm Accuracy'}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION: SUMMARY */}
      {/* ========================================================================= */}
      {activeSection === 'summary' && (
        <div className="space-y-4">
          <div className="bg-neutral-900/40 p-5 rounded-xl border border-neutral-800 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">Executive Summary</h3>
            <p className="text-sm text-neutral-200 leading-relaxed font-sans">
              {intelligence.executive_summary}
            </p>
          </div>

          <div className="bg-neutral-900/40 p-5 rounded-xl border border-neutral-800 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">Key Takeaways</h3>
            <ul className="space-y-2 text-xs text-neutral-300">
              {intelligence.key_takeaways.map((takeaway, idx) => (
                <li key={`takeaway-${takeaway.substring(0, 24)}-${idx}`} className="flex items-start space-x-2 bg-neutral-950 p-3 rounded-lg border border-neutral-800/80">
                  <span className="w-5 h-5 rounded-full bg-indigo-950 text-indigo-400 border border-indigo-800 flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    {idx + 1}
                  </span>
                  <span className="leading-relaxed">{takeaway}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION: DECISIONS */}
      {/* ========================================================================= */}
      {activeSection === 'decisions' && (
        <div className="space-y-3">
          {intelligence.decisions.map((dec) => {
            const consensusColors: Record<string, string> = {
              unanimous: 'bg-emerald-950 text-emerald-400 border-emerald-800',
              majority: 'bg-indigo-950 text-indigo-400 border-indigo-800',
              directive: 'bg-purple-950 text-purple-400 border-purple-800',
              contested: 'bg-amber-950 text-amber-400 border-amber-800'
            };

            return (
              <div key={dec.id} className="bg-neutral-900/40 p-4 rounded-xl border border-neutral-800 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${consensusColors[dec.consensus_level]}`}>
                    {dec.consensus_level} Consensus
                  </span>
                  <span className="text-[11px] text-neutral-500 font-mono">
                    Offset: {dec.timestamp_offset}s &bull; Confidence: {(dec.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-xs font-medium text-neutral-200">{dec.decision_text}</p>
                <div className="text-[11px] text-neutral-400 flex items-center gap-1">
                  <User className="w-3 h-3 text-neutral-500" />
                  Owner: <span className="text-neutral-300 font-semibold">{dec.decision_maker}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION: ACTION ITEMS */}
      {/* ========================================================================= */}
      {activeSection === 'action_items' && (
        <div className="space-y-3">
          {intelligence.action_items.map((act) => {
            const priorityColors: Record<string, string> = {
              critical: 'bg-rose-950 text-rose-400 border-rose-800',
              high: 'bg-amber-950 text-amber-400 border-amber-800',
              medium: 'bg-blue-950 text-blue-400 border-blue-800',
              low: 'bg-neutral-950 text-neutral-400 border-neutral-800'
            };

            const isDone = act.status === 'completed';

            return (
              <div
                key={act.id}
                className={`p-4 rounded-xl border transition-colors flex items-start justify-between gap-3 ${
                  isDone ? 'bg-neutral-950/60 border-neutral-800 opacity-75' : 'bg-neutral-900/40 border-neutral-800'
                }`}
              >
                <div className="flex items-start space-x-3">
                  <button
                    onClick={() => onToggleActionItem && onToggleActionItem(act.id)}
                    className={`w-5 h-5 rounded border mt-0.5 flex items-center justify-center transition-colors ${
                      isDone
                        ? 'bg-emerald-600 border-emerald-500 text-white'
                        : 'border-neutral-700 bg-neutral-950 hover:border-neutral-500'
                    }`}
                  >
                    {isDone && <CheckCircle2 className="w-3.5 h-3.5" />}
                  </button>
                  <div className="space-y-1">
                    <p className={`text-xs font-medium ${isDone ? 'line-through text-neutral-400' : 'text-neutral-200'}`}>
                      {act.description}
                    </p>
                    <div className="flex flex-wrap items-center gap-3 text-[11px] text-neutral-400">
                      <span className="flex items-center text-indigo-400 font-semibold">
                        <User className="w-3 h-3 mr-1" />
                        {act.assignee}
                      </span>
                      <span className="flex items-center text-neutral-500">
                        <Clock className="w-3 h-3 mr-1" />
                        Due: {new Date(act.due_date).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>

                <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border shrink-0 ${priorityColors[act.priority]}`}>
                  {act.priority}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION: TOPICS */}
      {/* ========================================================================= */}
      {activeSection === 'topics' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {intelligence.topics.map((t) => {
            const sentimentColors: Record<string, string> = {
              positive: 'text-emerald-400 bg-emerald-950 border-emerald-800',
              negative: 'text-rose-400 bg-rose-950 border-rose-800',
              neutral: 'text-neutral-400 bg-neutral-950 border-neutral-800',
              mixed: 'text-amber-400 bg-amber-950 border-amber-800'
            };

            return (
              <div key={t.id} className="bg-neutral-900/40 p-4 rounded-xl border border-neutral-800 space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-white">{t.name}</h4>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${sentimentColors[t.sentiment]}`}>
                    {t.sentiment}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[11px] text-neutral-400">
                  <span>Duration: {t.duration_seconds}s</span>
                  <span>Relevance: {(t.relevance * 100).toFixed(0)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION: RISKS */}
      {/* ========================================================================= */}
      {activeSection === 'risks' && (
        <div className="space-y-3">
          {intelligence.risks.map((risk) => (
            <div key={risk.id} className="bg-neutral-900/40 p-4 rounded-xl border border-neutral-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-rose-950 text-rose-400 border border-rose-800 flex items-center">
                  <ShieldAlert className="w-3 h-3 mr-1" />
                  {risk.severity} Severity Risk
                </span>
                <span className="text-[11px] text-neutral-500 font-mono">
                  Confidence: {(risk.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-xs font-semibold text-neutral-200">{risk.risk_text}</p>
              <div className="bg-neutral-950 p-2.5 rounded-lg border border-neutral-800/80 text-[11px] text-emerald-400/90 font-sans">
                <strong>Mitigation:</strong> {risk.mitigation_suggestion}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION: ACE BLACKBOARD & 13-MODULE PIPELINE TRACE */}
      {/* ========================================================================= */}
      {activeSection === 'ace_blackboard' && (
        <div className="space-y-6">
          {/* Header Summary */}
          <div className="bg-neutral-900/50 p-5 rounded-xl border border-neutral-800 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-neutral-800 pb-3">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <Workflow className="w-5 h-5 text-cyan-400" />
                  <h3 className="text-sm font-bold text-white">
                    Adaptive Collaboration Engine (ACE) &amp; 13-Module Pipeline Trace
                  </h3>
                </div>
                <p className="text-xs text-neutral-400">
                  Real-time event-driven orchestration log across the Semantic Knowledge Workspace (SKW) (PRD Chapter 3 &amp; SDD Chapter 12).
                </p>
              </div>

              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs font-bold font-mono">
                  UCS Confidence: {(intelligence.confidence_score * 100).toFixed(0)}%
                </span>
                <span className="px-2.5 py-1 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 text-xs font-bold font-mono">
                  Cycles: 4 Iterations
                </span>
              </div>
            </div>

            {/* 13 AI Modules Status Grid Table */}
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-neutral-300 uppercase tracking-wider">
                Specialized AI Module Execution Contracts (AIR-001 to AIR-070)
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-neutral-950 text-[10px] uppercase font-semibold text-neutral-400 border-b border-neutral-800">
                    <tr>
                      <th className="py-2 px-3">Module Name</th>
                      <th className="py-2 px-3">Technology / Model</th>
                      <th className="py-2 px-3">Primary Output</th>
                      <th className="py-2 px-3">Latency</th>
                      <th className="py-2 px-3">Confidence</th>
                      <th className="py-2 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-800/60 font-mono text-[11px] text-neutral-300">
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Activity className="w-3.5 h-3.5 text-cyan-400" />
                        1. Audio Intelligence Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">Silero VAD / Librosa</td>
                      <td className="py-2 px-3">Audio Profile &amp; SNR (+14.2dB)</td>
                      <td className="py-2 px-3">142ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.98</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Workflow className="w-3.5 h-3.5 text-indigo-400" />
                        2. Adaptive Collaboration Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">ACE Orchestrator / Redis</td>
                      <td className="py-2 px-3">Dynamic Execution Graph</td>
                      <td className="py-2 px-3">18ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.99</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                        3. Multilingual ASR Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">openai/whisper-large-v3</td>
                      <td className="py-2 px-3">Raw Multilingual Transcript</td>
                      <td className="py-2 px-3">1,120ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.94</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Languages className="w-3.5 h-3.5 text-amber-400" />
                        4. Code-Switch Intelligence
                      </td>
                      <td className="py-2 px-3 text-neutral-400">fastText LID / BiLSTM</td>
                      <td className="py-2 px-3">Intra-sentential Switch Events</td>
                      <td className="py-2 px-3">85ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.95</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <User className="w-3.5 h-3.5 text-cyan-400" />
                        5. Speaker Representation Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">pyannote/ECAPA-TDNN</td>
                      <td className="py-2 px-3">192-D Speaker Embeddings &amp; Diarization</td>
                      <td className="py-2 px-3">320ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.93</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Layers className="w-3.5 h-3.5 text-amber-400" />
                        6. Overlap Resolution Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">SpeechBrain SepFormer / TS-VAD</td>
                      <td className="py-2 px-3">Concurrent Stream Attribution (F1: 0.72)</td>
                      <td className="py-2 px-3">210ms</td>
                      <td className="py-2 px-3 text-amber-400">0.88</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-emerald-400" />
                        7. Timestamp Intelligence Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">WhisperX Forced Aligner</td>
                      <td className="py-2 px-3">Word Alignment (&lt;24ms offset)</td>
                      <td className="py-2 px-3">95ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.97</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <GitBranch className="w-3.5 h-3.5 text-purple-400" />
                        8. Context Intelligence Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">BERTopic / Qdrant Context Graph</td>
                      <td className="py-2 px-3">Conversational Memory &amp; Pronoun Resolution</td>
                      <td className="py-2 px-3">160ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.96</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Edit3 className="w-3.5 h-3.5 text-indigo-400" />
                        9. Transcript Intelligence Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">spaCy / Punctuation Restorer</td>
                      <td className="py-2 px-3">Canonical Transcript (Grammar + Formatting)</td>
                      <td className="py-2 px-3">110ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.97</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Gauge className="w-3.5 h-3.5 text-amber-400" />
                        10. Confidence Fusion Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">Platt Scaling / Weighted Fusion</td>
                      <td className="py-2 px-3">Unified Confidence Score (UCS: 0.95)</td>
                      <td className="py-2 px-3">45ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.98</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                        11. Verification Engine (VE)
                      </td>
                      <td className="py-2 px-3 text-neutral-400">Deterministic Rule Matrix</td>
                      <td className="py-2 px-3">Decision: ACCEPT (14 KOs Verified)</td>
                      <td className="py-2 px-3">60ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.99</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          VERIFIED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        12. Meeting Understanding Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">Semantic Intent / NLP Extractor</td>
                      <td className="py-2 px-3">3 Decisions, 3 Actions, 1 Risk, Summary</td>
                      <td className="py-2 px-3">280ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.95</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          COMPLETED
                        </span>
                      </td>
                    </tr>
                    <tr className="hover:bg-neutral-900/50">
                      <td className="py-2 px-3 font-semibold text-white flex items-center gap-1.5">
                        <Database className="w-3.5 h-3.5 text-indigo-400" />
                        13. Knowledge Memory Engine
                      </td>
                      <td className="py-2 px-3 text-neutral-400">PostgreSQL + Qdrant 768-D Vector</td>
                      <td className="py-2 px-3">Cross-Meeting Canonical Repository Indexed</td>
                      <td className="py-2 px-3">130ms</td>
                      <td className="py-2 px-3 text-emerald-400">0.98</td>
                      <td className="py-2 px-3">
                        <span className="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-bold">
                          INDEXED
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Verification Engine Decision States */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-2">
              <div className="bg-neutral-950 p-3 rounded-lg border border-emerald-900/60 space-y-1">
                <div className="flex items-center justify-between text-xs font-bold text-emerald-400">
                  <span className="flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> ACCEPT
                  </span>
                  <span className="font-mono">14 KOs</span>
                </div>
                <p className="text-[11px] text-neutral-400">
                  Passed all multi-agent consensus and confidence checks (UCS &ge; 0.90).
                </p>
              </div>

              <div className="bg-neutral-950 p-3 rounded-lg border border-amber-900/60 space-y-1">
                <div className="flex items-center justify-between text-xs font-bold text-amber-400">
                  <span className="flex items-center gap-1">
                    <Zap className="w-3.5 h-3.5" /> REVISE
                  </span>
                  <span className="font-mono">2 KOs</span>
                </div>
                <p className="text-[11px] text-neutral-400">
                  Selectively reprocessed through Context Intelligence for pronoun clarity.
                </p>
              </div>

              <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800 space-y-1 opacity-70">
                <div className="flex items-center justify-between text-xs font-bold text-neutral-400">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" /> DEFER
                  </span>
                  <span className="font-mono">0 KOs</span>
                </div>
                <p className="text-[11px] text-neutral-500">
                  Awaiting additional evidence from upstream modules.
                </p>
              </div>

              <div className="bg-neutral-950 p-3 rounded-lg border border-rose-900/60 space-y-1">
                <div className="flex items-center justify-between text-xs font-bold text-rose-400">
                  <span className="flex items-center gap-1">
                    <XCircle className="w-3.5 h-3.5" /> REJECT
                  </span>
                  <span className="font-mono">1 KO</span>
                </div>
                <p className="text-[11px] text-neutral-400">
                  Discarded acoustic artifact segment (low packet rate noise burst).
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION: MEETING ANALYTICS ENGINE (MAE) */}
      {/* ========================================================================= */}
      {activeSection === 'analytics' && (
        <div className="space-y-6">
          <div className="bg-neutral-900/50 p-5 rounded-xl border border-neutral-800 space-y-5">
            <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-emerald-400" />
                  Meeting Analytics Engine (MAE) Metrics (FR-150 to FR-159)
                </h3>
                <p className="text-xs text-neutral-400 mt-0.5">
                  Quantitative collaboration dynamics, participant dominance index, and productivity metrics.
                </p>
              </div>
              <span className="px-2.5 py-1 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs font-bold font-mono">
                Meeting Quality Score: 94 / 100
              </span>
            </div>

            {/* Metric Overview Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-1">
                <div className="text-[11px] font-bold text-neutral-400 uppercase">Participant Balance Index</div>
                <div className="text-xl font-bold text-white font-mono">0.86 <span className="text-xs font-normal text-emerald-400">/ 1.0</span></div>
                <p className="text-[10px] text-neutral-500">High turn-taking balance across 5 speakers.</p>
              </div>

              <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-1">
                <div className="text-[11px] font-bold text-neutral-400 uppercase">Decision Density</div>
                <div className="text-xl font-bold text-emerald-400 font-mono">1.3 <span className="text-xs font-normal text-neutral-400">per 10m</span></div>
                <p className="text-[10px] text-neutral-500">3 verified decisions in 23 minutes.</p>
              </div>

              <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-1">
                <div className="text-[11px] font-bold text-neutral-400 uppercase">Action Resolution Rate</div>
                <div className="text-xl font-bold text-indigo-400 font-mono">100%</div>
                <p className="text-[10px] text-neutral-500">All 3 tasks assigned with owner &amp; due date.</p>
              </div>

              <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-1">
                <div className="text-[11px] font-bold text-neutral-400 uppercase">Code-Switch Frequency</div>
                <div className="text-xl font-bold text-amber-400 font-mono">4.2 <span className="text-xs font-normal text-neutral-400">switches/m</span></div>
                <p className="text-[10px] text-neutral-500">Multilingual Hinglish / English transitions.</p>
              </div>
            </div>

            {/* Speaker Participation Breakdown Bars */}
            <div className="space-y-3 bg-neutral-950 p-4 rounded-xl border border-neutral-800">
              <h4 className="text-xs font-bold text-white flex items-center gap-2">
                <PieChart className="w-3.5 h-3.5 text-indigo-400" />
                Speaker Participation &amp; Dominance Breakdown
              </h4>

              <div className="space-y-2 text-xs">
                <div>
                  <div className="flex items-center justify-between text-[11px] text-neutral-300 mb-1">
                    <span>Ayush (Lead Analyst)</span>
                    <span className="font-mono text-neutral-400">32% (7.3 min)</span>
                  </div>
                  <div className="w-full bg-neutral-900 rounded-full h-2 overflow-hidden border border-neutral-800">
                    <div className="bg-indigo-500 h-full rounded-full" style={{ width: '32%' }} />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-neutral-300 mb-1">
                    <span>Niti (Visual Specialist)</span>
                    <span className="font-mono text-neutral-400">28% (6.4 min)</span>
                  </div>
                  <div className="w-full bg-neutral-900 rounded-full h-2 overflow-hidden border border-neutral-800">
                    <div className="bg-cyan-500 h-full rounded-full" style={{ width: '28%' }} />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-neutral-300 mb-1">
                    <span>Sneha (Documentation Coordinator)</span>
                    <span className="font-mono text-neutral-400">22% (5.0 min)</span>
                  </div>
                  <div className="w-full bg-neutral-900 rounded-full h-2 overflow-hidden border border-neutral-800">
                    <div className="bg-purple-500 h-full rounded-full" style={{ width: '22%' }} />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-neutral-300 mb-1">
                    <span>Instructor (Evaluator)</span>
                    <span className="font-mono text-neutral-400">12% (2.8 min)</span>
                  </div>
                  <div className="w-full bg-neutral-900 rounded-full h-2 overflow-hidden border border-neutral-800">
                    <div className="bg-rose-500 h-full rounded-full" style={{ width: '12%' }} />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-neutral-300 mb-1">
                    <span>Bhavya (Data Contributor)</span>
                    <span className="font-mono text-neutral-400">6% (1.4 min)</span>
                  </div>
                  <div className="w-full bg-neutral-900 rounded-full h-2 overflow-hidden border border-neutral-800">
                    <div className="bg-amber-500 h-full rounded-full" style={{ width: '6%' }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

