import React from 'react';
import {
  Activity,
  CheckCircle2,
  Database,
  Layers,
  Radio,
  Sparkles,
  Cpu
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
      className={`border-b px-4 sm:px-6 py-2.5 mb-6 text-xs transition-colors ${
        theme === 'dark'
          ? 'bg-slate-900/40 border-slate-800/80 text-slate-400'
          : 'bg-slate-50/70 border-slate-200/90 text-slate-600'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-y-2 gap-x-4">
        {/* Left Side: Context & Engine Architecture */}
        <div className="flex items-center flex-wrap gap-2 text-xs">
          <span className="font-semibold text-slate-800 dark:text-slate-200">
            Pipeline Architecture
          </span>
          <span aria-hidden="true" className="text-slate-300 dark:text-slate-700">·</span>
          <span className="flex items-center gap-1 text-slate-700 dark:text-slate-300">
            <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
            Open-MOSS Transcribe-Diarize
          </span>
          <span aria-hidden="true" className="text-slate-300 dark:text-slate-700">·</span>
          <span className="flex items-center gap-1 text-slate-700 dark:text-slate-300">
            <Activity className="w-3.5 h-3.5 text-teal-500" />
            PyAnnote 3.1 Diarization
          </span>
          <span aria-hidden="true" className="text-slate-300 dark:text-slate-700">·</span>
          <span className="text-slate-500">
            1,024-token context stride
          </span>
        </div>

        {/* Right Side: Clean Unboxed Metrics */}
        <div className="flex items-center flex-wrap gap-3 font-mono text-[11px] tabular-nums">
          <div className="flex items-center gap-1">
            <span className="text-slate-500">Meetings:</span>
            <span className="font-semibold text-slate-900 dark:text-slate-100">{totalMeetingsCount}</span>
          </div>
          <span aria-hidden="true" className="text-slate-300 dark:text-slate-700">·</span>
          <div className="flex items-center gap-1">
            <span className="text-slate-500">Knowledge:</span>
            <span className="font-semibold text-slate-900 dark:text-slate-100">{totalKnowledgeObjects} KOs</span>
          </div>
          <span aria-hidden="true" className="text-slate-300 dark:text-slate-700">·</span>
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="text-emerald-600 dark:text-emerald-400 font-sans font-medium text-xs">Acoustic Pipeline Ready</span>
          </div>
        </div>
      </div>
    </div>
  );
};
