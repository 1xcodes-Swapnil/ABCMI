import React from 'react';
import {
  Sparkles,
  Radio,
  Cpu,
  Layers,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Database,
  Activity,
  Workflow
} from 'lucide-react';

interface SystemStatusBarProps {
  theme: 'dark' | 'light';
  activeMeetingTitle?: string;
  totalMeetingsCount: number;
  totalKnowledgeObjects: number;
}

export const SystemStatusBar: React.FC<SystemStatusBarProps> = ({
  theme,
  activeMeetingTitle,
  totalMeetingsCount,
  totalKnowledgeObjects
}) => {
  return (
    <div
      id="system-status-telemetry-bar"
      className={`rounded-2xl border p-3.5 mb-6 transition-all shadow-xs ${
        theme === 'dark'
          ? 'bg-slate-900/60 border-slate-800/80 text-slate-200'
          : 'bg-white border-slate-200/90 text-slate-800'
      }`}
    >
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
        {/* Left Core Engine Architecture */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* Primary Model */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-xl border font-medium ${
              theme === 'dark'
                ? 'bg-indigo-950/40 border-indigo-800/50 text-indigo-300'
                : 'bg-indigo-50 border-indigo-200 text-indigo-800'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span className="font-semibold">Primary:</span>
            <span className="font-mono text-[11px]">Open-MOSS Transcribe-Diarize</span>
          </div>

          {/* Diarizer */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-xl border font-medium ${
              theme === 'dark'
                ? 'bg-teal-950/40 border-teal-800/50 text-teal-300'
                : 'bg-teal-50 border-teal-200 text-teal-800'
            }`}
          >
            <Activity className="w-3.5 h-3.5 text-teal-400" />
            <span className="font-semibold">Diarization:</span>
            <span className="font-mono text-[11px]">PyAnnote 3.1</span>
          </div>

          {/* Fallback ASR */}
          <div
            className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-xl border font-medium ${
              theme === 'dark'
                ? 'bg-slate-950/60 border-slate-800 text-slate-400'
                : 'bg-slate-100 border-slate-200 text-slate-600'
            }`}
          >
            <span>Backup:</span>
            <span className="font-mono text-[11px]">Sarvam ASR (Fallback Only)</span>
          </div>

          {/* Execution Environment Mode */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-xl border text-[11px] font-mono ${
              theme === 'dark'
                ? 'bg-emerald-950/40 border-emerald-800/50 text-emerald-300'
                : 'bg-emerald-50 border-emerald-200 text-emerald-800'
            }`}
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>ENFORCEMENT: REAL/FIXTURE</span>
          </div>
        </div>

        {/* Right Active Pipeline Scope */}
        <div className="flex items-center gap-3 text-xs">
          {activeMeetingTitle && (
            <div className="flex items-center gap-1.5 truncate max-w-xs">
              <span className={`text-[11px] ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>Scope:</span>
              <span className="font-semibold truncate text-indigo-400">{activeMeetingTitle}</span>
            </div>
          )}

          <div className="hidden sm:flex items-center gap-2 border-l pl-3 border-slate-700/50">
            <span
              className={`px-2 py-0.5 rounded-md text-[10px] font-mono border ${
                theme === 'dark'
                  ? 'bg-slate-950 border-slate-800 text-slate-300'
                  : 'bg-slate-100 border-slate-200 text-slate-700'
              }`}
            >
              {totalMeetingsCount} Sessions
            </span>
            <span
              className={`px-2 py-0.5 rounded-md text-[10px] font-mono border ${
                theme === 'dark'
                  ? 'bg-slate-950 border-slate-800 text-slate-300'
                  : 'bg-slate-100 border-slate-200 text-slate-700'
              }`}
            >
              {totalKnowledgeObjects} KOs
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
