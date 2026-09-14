import React, { useState, useEffect, useRef } from 'react';
import {
  Search,
  Command,
  X,
  Users,
  Radio,
  Sparkles,
  Database,
  Languages,
  FileText,
  Award,
  ShieldCheck,
  Terminal,
  ArrowRight,
  Clock,
  CheckCircle2,
  Cpu
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { MeetingItem } from '../types';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  activeTab: string;
  onSelectTab: (tab: any) => void;
  meetings: MeetingItem[];
  onSelectMeeting: (id: string) => void;
  theme: 'dark' | 'light';
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  activeTab,
  onSelectTab,
  meetings,
  onSelectMeeting,
  theme
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setQuery('');
      setSelectedIndex(0);
    }
  }, [isOpen]);

  // Keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (isOpen) onClose();
        else {
          // Trigger handled from parent or toggle
        }
      } else if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const navItems = [
    { key: 'meetings', label: 'Meetings & Audio Ingestion', category: 'Core Pipeline', icon: Users, desc: 'Batch audio intake, 500MB upload, chunking' },
    { key: 'live_stream', label: 'Real-Time Live Stream', category: 'Core Pipeline', icon: Radio, desc: 'WebSocket live transcription & partial diarization' },
    { key: 'intelligence', label: 'Multi-Agent Intelligence (ACE)', category: 'Core Pipeline', icon: Sparkles, desc: '13-module blackboard, summary, action items' },
    { key: 'queries', label: 'Ask ABCI-MI (Grounded Q&A)', category: 'Knowledge & Analytics', icon: Search, desc: 'Cross-meeting grounded semantic queries' },
    { key: 'knowledge', label: 'Knowledge Warehouse (SKW)', category: 'Knowledge & Analytics', icon: Database, desc: 'Semantic Knowledge Web, canonical objects' },
    { key: 'translations', label: 'Translations (17 Locales)', category: 'Knowledge & Analytics', icon: Languages, desc: 'Indic languages, code-switched synthesis' },
    { key: 'reports', label: 'Reports & Exports', category: 'Governance & Platform', icon: FileText, desc: 'Structured PDF, Markdown & JSON reports' },
    { key: 'benchmarks', label: 'Research & SOTA Benchmarks', category: 'Governance & Platform', icon: Award, desc: 'AMI, VoxConverse & AISHELL WER/DER' },
    { key: 'security', label: 'Security & Audit Governance', category: 'Governance & Platform', icon: ShieldCheck, desc: 'RBAC roles, HS256 tokens, audit ledger' },
    { key: 'api_console', label: 'API Console (47 Endpoints)', category: 'Governance & Platform', icon: Terminal, desc: 'Interactive REST API tester' },
  ];

  const filteredNav = navItems.filter(item =>
    item.label.toLowerCase().includes(query.toLowerCase()) ||
    item.desc.toLowerCase().includes(query.toLowerCase()) ||
    item.category.toLowerCase().includes(query.toLowerCase())
  );

  const filteredMeetings = meetings.filter(m =>
    m.title.toLowerCase().includes(query.toLowerCase()) ||
    m.description.toLowerCase().includes(query.toLowerCase()) ||
    m.primary_language.toLowerCase().includes(query.toLowerCase())
  );

  const allResults = [
    ...filteredNav.map(item => ({ type: 'nav' as const, item })),
    ...filteredMeetings.map(m => ({ type: 'meeting' as const, item: m }))
  ];

  const handleSelect = (result: typeof allResults[0]) => {
    if (result.type === 'nav') {
      onSelectTab(result.item.key);
    } else {
      onSelectMeeting(result.item.id);
      onSelectTab('intelligence');
    }
    onClose();
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 sm:pt-28 px-4 bg-slate-950/70 backdrop-blur-md">
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: -10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -10 }}
          transition={{ duration: 0.15 }}
          className={`w-full max-w-2xl rounded-2xl border shadow-2xl overflow-hidden ${
            theme === 'dark'
              ? 'bg-slate-900 border-slate-800 text-slate-100 shadow-indigo-950/30'
              : 'bg-white border-slate-200 text-slate-900 shadow-slate-300/40'
          }`}
        >
          {/* Search Input Bar */}
          <div className={`flex items-center gap-3 px-4 py-3.5 border-b ${theme === 'dark' ? 'border-slate-800' : 'border-slate-200'}`}>
            <Search className={`w-5 h-5 shrink-0 ${theme === 'dark' ? 'text-indigo-400' : 'text-indigo-600'}`} />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              placeholder="Type to search modules, meetings, reports, or press ESC to close..."
              className={`w-full bg-transparent text-sm font-medium focus:outline-none placeholder:text-slate-400`}
            />
            {query && (
              <button
                onClick={() => setQuery('')}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            )}
            <kbd className={`px-2 py-0.5 text-[10px] font-mono rounded border ${theme === 'dark' ? 'bg-slate-800 border-slate-700 text-slate-300' : 'bg-slate-100 border-slate-200 text-slate-600'}`}>
              ESC
            </kbd>
          </div>

          {/* Results List */}
          <div className="max-h-96 overflow-y-auto p-2 space-y-1">
            {allResults.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-400">
                No matching framework views or meeting records found for "{query}".
              </div>
            ) : (
              <>
                {filteredNav.length > 0 && (
                  <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Framework Modules ({filteredNav.length})
                  </div>
                )}
                {filteredNav.map((item, idx) => {
                  const Icon = item.icon;
                  const isCurrent = activeTab === item.key;
                  return (
                    <button
                      key={item.key}
                      onClick={() => handleSelect({ type: 'nav', item })}
                      className={`w-full flex items-center justify-between p-2.5 rounded-xl text-left transition-all ${
                        theme === 'dark'
                          ? 'hover:bg-slate-800/90 text-slate-200'
                          : 'hover:bg-slate-100 text-slate-800'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`p-2 rounded-lg ${theme === 'dark' ? 'bg-slate-800 text-indigo-400' : 'bg-indigo-50 text-indigo-600'}`}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <div className="truncate">
                          <div className="text-xs font-semibold flex items-center gap-2">
                            <span>{item.label}</span>
                            {isCurrent && (
                              <span className="text-[10px] px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-400 font-mono">
                                current
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-400 truncate">{item.desc}</div>
                        </div>
                      </div>
                      <ArrowRight className="w-3.5 h-3.5 text-slate-400 shrink-0 ml-2" />
                    </button>
                  );
                })}

                {filteredMeetings.length > 0 && (
                  <>
                    <div className="px-3 pt-3 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400 border-t mt-2">
                      Recent Meeting Sessions ({filteredMeetings.length})
                    </div>
                    {filteredMeetings.map(m => (
                      <button
                        key={m.id}
                        onClick={() => handleSelect({ type: 'meeting', item: m })}
                        className={`w-full flex items-center justify-between p-2.5 rounded-xl text-left transition-all ${
                          theme === 'dark'
                            ? 'hover:bg-slate-800/90 text-slate-200'
                            : 'hover:bg-slate-100 text-slate-800'
                        }`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div className={`p-2 rounded-lg ${theme === 'dark' ? 'bg-slate-800 text-teal-400' : 'bg-teal-50 text-teal-600'}`}>
                            <Users className="w-4 h-4" />
                          </div>
                          <div className="truncate">
                            <div className="text-xs font-semibold truncate">{m.title}</div>
                            <div className="text-[11px] text-slate-400 flex items-center gap-2">
                              <span className="uppercase font-mono text-[10px]">{m.primary_language}</span>
                              <span>&bull;</span>
                              <span>{m.duration_minutes || 0} mins</span>
                              <span>&bull;</span>
                              <span className="capitalize">{m.status}</span>
                            </div>
                          </div>
                        </div>
                        <span className="text-[10px] text-indigo-400 font-medium">Open Intel &rarr;</span>
                      </button>
                    ))}
                  </>
                )}
              </>
            )}
          </div>

          {/* Quick Footer */}
          <div className={`px-4 py-2.5 border-t text-[11px] text-slate-400 flex items-center justify-between ${theme === 'dark' ? 'border-slate-800 bg-slate-950/50' : 'border-slate-200 bg-slate-50'}`}>
            <div className="flex items-center gap-3">
              <span>Navigate: <kbd className="px-1 font-mono">↑</kbd><kbd className="px-1 font-mono">↓</kbd></span>
              <span>Select: <kbd className="px-1 font-mono">↵</kbd></span>
            </div>
            <span className="font-mono text-[10px] text-indigo-400">Open-MOSS / ACE Engine v1.0</span>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
