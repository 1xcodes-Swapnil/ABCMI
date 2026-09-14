import React, { useState, useRef } from 'react';
import {
  Plus,
  Upload,
  Play,
  Pause,
  CheckCircle2,
  Clock,
  AlertCircle,
  FileAudio,
  Loader2,
  Sparkles,
  Calendar,
  Users,
  RefreshCw,
  Search,
  Filter,
  ArrowRight,
  Sliders,
  Volume2,
  Layers,
  FileText,
  Trash2,
  ChevronDown,
  ChevronUp,
  Tag,
  Globe,
  Radio,
  FileCheck,
  Zap,
  X,
  UserCheck,
  AlertTriangle,
  RotateCcw
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { MeetingItem, MeetingStatus } from '../types';

interface MeetingsTesterProps {
  meetings: MeetingItem[];
  selectedMeetingId: string;
  onSelectMeeting: (id: string) => void;
  onCreateMeeting: (
    title: string,
    description: string,
    language: string,
    details?: {
      category?: string;
      tags?: string[];
      participants?: string[];
      duration_minutes?: number;
      scheduled_start?: string;
      audio_file?: File;
      auto_process?: boolean;
    }
  ) => void;
  onUploadAudio: (meetingId: string, file: File) => void;
  onProcessMeeting: (meetingId: string) => void;
  onViewIntelligence?: (meetingId: string) => void;
  onDeleteMeeting?: (meetingId: string) => void;
  theme?: 'dark' | 'light';
}

export const MeetingsTester: React.FC<MeetingsTesterProps> = ({
  meetings,
  selectedMeetingId,
  onSelectMeeting,
  onCreateMeeting,
  onUploadAudio,
  onProcessMeeting,
  onViewIntelligence,
  onDeleteMeeting,
  theme = 'dark'
}) => {
  // Intake Card State
  const [isIntakeExpanded, setIsIntakeExpanded] = useState(false);
  
  // New Meeting Form Fields
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [language, setLanguage] = useState('en');
  const [category, setCategory] = useState('Architecture & Engineering');
  const [durationMinutes, setDurationMinutes] = useState(45);
  const [participantInput, setParticipantInput] = useState('');
  const [participants, setParticipants] = useState<string[]>([
    'Sneha (Lead)',
    'Om (Research)',
    'Neetigya (ML Ops)'
  ]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [autoProcess, setAutoProcess] = useState(true);

  // Uploading and Interaction States
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragActiveId, setDragActiveId] = useState<string | null>(null);
  const [intakeDragActive, setIntakeDragActive] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | MeetingStatus>('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  
  // Audio playback preview state per meeting
  const [playingMeetingId, setPlayingMeetingId] = useState<string | null>(null);

  // Delete Confirmation State
  const [meetingToDelete, setMeetingToDelete] = useState<MeetingItem | null>(null);
  const [deleteToast, setDeleteToast] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Preset Meeting Templates for Quick Ingestion
  const PRESET_TEMPLATES = [
    {
      name: 'BIVA Act: Sneha, Om & Neetigya',
      title: 'BIVA Multilingual Corpus Review & Open-MOSS Diarization',
      desc: 'Deep-dive meeting discussing Indian crime statistics dataset filtering, Tamil/Hindi code-switching, and PyAnnote speaker reconciliation.',
      lang: 'hinglish',
      category: 'Corpus & Annotation',
      duration: 138,
      speakers: ['Sneha (Lead)', 'Om (Researcher)', 'Neetigya (ML Ops)']
    },
    {
      name: 'Phase 4.26 MOSS Verification',
      title: 'Open-MOSS vs Sarvam Saaras ASR Benchmark Sync',
      desc: 'Real end-to-end telemetry comparison on Tesla T4, evaluating CER, WER, and speaker attribution fidelity.',
      lang: 'en',
      category: 'Research & Benchmarks',
      duration: 52,
      speakers: ['Dr. Aris (Audio Lead)', 'Kiran (ML Ops)', 'Priya (Data Lead)']
    },
    {
      name: 'Tamil-English Technical Review',
      title: 'Tanglish Speech Synthesis & Code-Switch Evaluation',
      desc: 'Evaluating conversational Tanglish phoneme recognition and Blackboard consensus mechanisms.',
      lang: 'tanglish',
      category: 'Multilingual AI',
      duration: 35,
      speakers: ['Karthik (NLP Lead)', 'Ananya (Eval Lead)']
    }
  ];

  const handleApplyPreset = (preset: typeof PRESET_TEMPLATES[0]) => {
    setTitle(preset.title);
    setDescription(preset.desc);
    setLanguage(preset.lang);
    setCategory(preset.category);
    setDurationMinutes(preset.duration);
    setParticipants(preset.speakers);
    setIsIntakeExpanded(true);
  };

  const handleAddParticipant = () => {
    if (!participantInput.trim()) return;
    if (!participants.includes(participantInput.trim())) {
      setParticipants([...participants, participantInput.trim()]);
    }
    setParticipantInput('');
  };

  const handleRemoveParticipant = (p: string) => {
    setParticipants(participants.filter(item => item !== p));
  };

  const handleIntakeFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    
    // Check max size (500MB)
    const maxSizeBytes = 500 * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      alert('Error: File size exceeds the maximum limit of 500 MB.');
      return;
    }

    setSelectedFile(file);
    // If title is empty, infer from filename
    if (!title.trim()) {
      const cleanName = file.name
        .replace(/\.[^/.]+$/, '')
        .replace(/[._-]/g, ' ')
        .trim();
      setTitle(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
    }
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    onCreateMeeting(title, description || 'Meeting session initialized for multilingual speech understanding.', language, {
      category,
      participants: participants.length > 0 ? participants : ['Primary Speaker'],
      duration_minutes: durationMinutes,
      audio_file: selectedFile || undefined,
      auto_process: autoProcess && !!selectedFile
    });

    // Reset Form
    setTitle('');
    setDescription('');
    setSelectedFile(null);
    setIsIntakeExpanded(false);
  };

  const handleCardFileDrop = (meetingId: string, files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];

    const maxSizeBytes = 500 * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      alert('Error: File size exceeds the maximum limit of 500 MB.');
      return;
    }

    setUploadingId(meetingId);
    setUploadProgress(20);
    const interval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 95) {
          clearInterval(interval);
          setTimeout(() => {
            onUploadAudio(meetingId, file);
            setUploadingId(null);
            setUploadProgress(0);
          }, 350);
          return 100;
        }
        return prev + 25;
      });
    }, 120);
  };

  const confirmDelete = () => {
    if (meetingToDelete && onDeleteMeeting) {
      const deletedTitle = meetingToDelete.title;
      onDeleteMeeting(meetingToDelete.id);
      setMeetingToDelete(null);
      setDeleteToast(`Meeting "${deletedTitle}" removed successfully.`);
      setTimeout(() => setDeleteToast(null), 4000);
    }
  };

  const getStatusBadge = (status: MeetingStatus) => {
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3 mr-1" /> Synthesized
          </span>
        );
      case 'processing':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-500/15 text-indigo-400 border border-indigo-500/30 animate-pulse">
            <Loader2 className="w-3 h-3 mr-1 animate-spin" /> Open-MOSS Ingestion
          </span>
        );
      case 'live':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400 mr-1.5 animate-ping" /> Live Stream
          </span>
        );
      case 'paused':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
            <Clock className="w-3 h-3 mr-1" /> Paused
          </span>
        );
      case 'scheduled':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">
            <Calendar className="w-3 h-3 mr-1" /> Scheduled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-500/15 text-slate-400 border border-slate-500/30">
            <FileAudio className="w-3 h-3 mr-1" /> Ready for Intake
          </span>
        );
    }
  };

  const filteredMeetings = meetings.filter(m => {
    const matchesSearch =
      m.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.primary_language.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (m.category && m.category.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesStatus = statusFilter === 'all' || m.status === statusFilter;
    const matchesCategory = categoryFilter === 'all' || m.category === categoryFilter;
    return matchesSearch && matchesStatus && matchesCategory;
  });

  return (
    <div id="meetings-tester-container" className="space-y-6">
      {/* Toast Notification */}
      <AnimatePresence>
        {deleteToast && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="p-3 rounded-xl bg-slate-900 border border-rose-800/80 text-rose-300 text-xs flex items-center justify-between shadow-xl shadow-slate-950/60"
          >
            <div className="flex items-center gap-2">
              <Trash2 className="w-4 h-4 text-rose-400" />
              <span>{deleteToast}</span>
            </div>
            <button
              type="button"
              onClick={() => setDeleteToast(null)}
              className="text-slate-400 hover:text-white p-1"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top Banner & Quick Controls */}
      <div
        className={`rounded-2xl border p-6 transition-all ${
          theme === 'dark'
            ? 'bg-slate-900/80 border-slate-800 text-slate-100 shadow-xl shadow-slate-950/40'
            : 'bg-white border-slate-200 text-slate-900 shadow-sm'
        }`}
      >
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="p-2.5 rounded-xl bg-indigo-500/15 text-indigo-400 border border-indigo-500/30">
                <Users className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-lg font-bold tracking-tight flex items-center gap-2">
                  Meeting Sessions &amp; Audio Intake
                  <span className="text-[10px] px-2 py-0.5 rounded-md font-mono bg-indigo-950 text-indigo-400 border border-indigo-900">
                    ADR-004 &bull; 500MB
                  </span>
                </h2>
                <p className={`text-xs ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>
                  Ingest multi-speaker audio recordings (WAV/MP3/M4A), define speaker rosters, execute Open-MOSS acoustic diarization, or remove existing sessions.
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              id="btn-toggle-intake-card"
              type="button"
              onClick={() => setIsIntakeExpanded(!isIntakeExpanded)}
              className={`inline-flex items-center justify-center px-4 py-2.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer ${
                isIntakeExpanded
                  ? 'bg-indigo-950 border-indigo-700 text-indigo-300 shadow-inner'
                  : 'bg-indigo-600 hover:bg-indigo-500 text-white border-indigo-600 shadow-md shadow-indigo-600/25 active:scale-95'
              }`}
            >
              <Plus className={`w-4 h-4 mr-1.5 transition-transform duration-200 ${isIntakeExpanded ? 'rotate-45' : ''}`} />
              <span>{isIntakeExpanded ? 'Close Intake Form' : 'Add Meeting (+)'}</span>
            </button>
          </div>
        </div>

        {/* Preset Quick Ingestion Chips */}
        <div className="mt-4 pt-3.5 border-t border-slate-800/60 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Quick Presets:
          </span>
          {PRESET_TEMPLATES.map((p, idx) => (
            <button
              key={`preset-${idx}`}
              type="button"
              onClick={() => handleApplyPreset(p)}
              className="px-2.5 py-1 rounded-lg bg-slate-950/80 hover:bg-slate-800 border border-slate-800 hover:border-indigo-800/60 text-slate-300 text-[11px] transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
              <span>{p.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* RECREATED MEETING INTAKE WORKBENCH CARD */}
      <AnimatePresence>
        {isIntakeExpanded && (
          <motion.div
            id="meeting-intake-card"
            initial={{ opacity: 0, height: 0, scale: 0.98 }}
            animate={{ opacity: 1, height: 'auto', scale: 1 }}
            exit={{ opacity: 0, height: 0, scale: 0.98 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div
              className={`rounded-2xl border p-6 space-y-6 shadow-2xl ${
                theme === 'dark'
                  ? 'bg-slate-900 border-indigo-500/50 shadow-indigo-950/30 text-slate-100'
                  : 'bg-white border-indigo-400 shadow-indigo-100 text-slate-900'
              }`}
            >
              {/* Intake Header */}
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/30">
                    <Plus className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold flex items-center gap-2">
                      Meeting Intake &amp; Audio Ingestion Studio
                    </h3>
                    <p className="text-xs text-slate-400">
                      Define meeting parameters, upload meeting audio, and configure AI processing options.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setIsIntakeExpanded(false)}
                  className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Intake Form */}
              <form onSubmit={handleCreateSubmit} className="space-y-5">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                  {/* Left 2 Cols: Metadata Details */}
                  <div className="lg:col-span-2 space-y-4">
                    {/* Meeting Title */}
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-300">
                        Meeting Name / Title <span className="text-rose-400">*</span>
                      </label>
                      <input
                        id="input-intake-title"
                        type="text"
                        required
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        placeholder="e.g., BIVA Multilingual Act & Speaker Diarization Analysis"
                        className={`w-full rounded-xl px-4 py-2.5 text-xs border focus:outline-none transition-all ${
                          theme === 'dark'
                            ? 'bg-slate-950 border-slate-800 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500'
                            : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-indigo-600'
                        }`}
                      />
                    </div>

                    {/* Description & Agenda */}
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-300">
                        Session Agenda &amp; Discussion Objectives
                      </label>
                      <textarea
                        id="input-intake-description"
                        rows={2}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Outline discussion items, topics covered, or specific meeting context..."
                        className={`w-full rounded-xl px-4 py-2 text-xs border focus:outline-none transition-all ${
                          theme === 'dark'
                            ? 'bg-slate-950 border-slate-800 text-slate-100 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500'
                            : 'bg-slate-50 border-slate-200 text-slate-900 focus:border-indigo-600'
                        }`}
                      />
                    </div>

                    {/* Language and Category Selectors */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-bold mb-1.5 text-slate-300 flex items-center gap-1">
                          <Globe className="w-3.5 h-3.5 text-indigo-400" />
                          Spoken Language / Dialect
                        </label>
                        <select
                          id="select-intake-language"
                          value={language}
                          onChange={(e) => setLanguage(e.target.value)}
                          className={`w-full rounded-xl px-3.5 py-2.5 text-xs border focus:outline-none ${
                            theme === 'dark'
                              ? 'bg-slate-950 border-slate-800 text-slate-200 focus:border-indigo-500'
                              : 'bg-slate-50 border-slate-200 text-slate-800 focus:border-indigo-600'
                          }`}
                        >
                          <optgroup label="Code-Switched (Indic + English)">
                            <option value="hinglish">Hinglish / हिंग्लिश (hi-en)</option>
                            <option value="tanglish">Tanglish / தாங்கிலிஷ் (ta-en)</option>
                            <option value="spanglish">Spanglish (es-en)</option>
                          </optgroup>
                          <optgroup label="Global Languages">
                            <option value="en">English (Global en-US/en-IN)</option>
                            <option value="es">Spanish / Español (es)</option>
                            <option value="fr">French / Français (fr)</option>
                            <option value="de">German / Deutsch (de)</option>
                            <option value="ja">Japanese / 日本語 (ja)</option>
                            <option value="zh">Mandarin / 中文 (zh)</option>
                            <option value="ru">Russian / Русский (ru)</option>
                            <option value="ar">Arabic / العربية (ar)</option>
                          </optgroup>
                          <optgroup label="Indic Locales">
                            <option value="hi">Hindi / हिन्दी (hi)</option>
                            <option value="ta">Tamil / தமிழ் (ta)</option>
                            <option value="te">Telugu / తెలుగు (te)</option>
                            <option value="kn">Kannada / ಕನ್ನಡ (kn)</option>
                            <option value="ml">Malayalam / മലയാളം (ml)</option>
                            <option value="bn">Bengali / বাংলা (bn)</option>
                            <option value="mr">Marathi / मराठी (mr)</option>
                            <option value="gu">Gujarati / ગુજરાતી (gu)</option>
                            <option value="pa">Punjabi / ਪੰਜਾਬੀ (pa)</option>
                          </optgroup>
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs font-bold mb-1.5 text-slate-300 flex items-center gap-1">
                          <Tag className="w-3.5 h-3.5 text-indigo-400" />
                          Meeting Domain / Category
                        </label>
                        <select
                          id="select-intake-category"
                          value={category}
                          onChange={(e) => setCategory(e.target.value)}
                          className={`w-full rounded-xl px-3.5 py-2.5 text-xs border focus:outline-none ${
                            theme === 'dark'
                              ? 'bg-slate-950 border-slate-800 text-slate-200 focus:border-indigo-500'
                              : 'bg-slate-50 border-slate-200 text-slate-800 focus:border-indigo-600'
                          }`}
                        >
                          <option value="Architecture & Engineering">Architecture &amp; Engineering</option>
                          <option value="Corpus & Annotation">Corpus &amp; Annotation</option>
                          <option value="Research & Benchmarks">Research &amp; Benchmarks</option>
                          <option value="Multilingual AI">Multilingual AI</option>
                          <option value="Product & Strategy">Product &amp; Strategy</option>
                          <option value="Executive Review">Executive Review</option>
                        </select>
                      </div>
                    </div>

                    {/* Participants Roster */}
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-300 flex items-center gap-1">
                        <Users className="w-3.5 h-3.5 text-indigo-400" />
                        Expected Speakers / Participants
                      </label>
                      <div className="flex items-center gap-2 mb-2">
                        <input
                          id="input-intake-participant"
                          type="text"
                          value={participantInput}
                          onChange={(e) => setParticipantInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              handleAddParticipant();
                            }
                          }}
                          placeholder="Type speaker name and press Add or Enter..."
                          className={`flex-1 rounded-xl px-3.5 py-2 text-xs border focus:outline-none ${
                            theme === 'dark'
                              ? 'bg-slate-950 border-slate-800 text-slate-200 focus:border-indigo-500'
                              : 'bg-slate-50 border-slate-200 text-slate-800 focus:border-indigo-600'
                          }`}
                        />
                        <button
                          type="button"
                          onClick={handleAddParticipant}
                          className="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 cursor-pointer"
                        >
                          Add Speaker
                        </button>
                      </div>

                      {/* Participant Chips */}
                      <div className="flex flex-wrap gap-1.5">
                        {participants.map((p, idx) => (
                          <span
                            key={`part-${idx}`}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-950 border border-slate-800 text-slate-300 text-xs"
                          >
                            <span className="w-2 h-2 rounded-full bg-teal-400" />
                            <span>{p}</span>
                            <button
                              type="button"
                              onClick={() => handleRemoveParticipant(p)}
                              className="text-slate-500 hover:text-rose-400 ml-0.5 cursor-pointer"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Right 1 Col: Audio Upload & Direct Ingestion Zone */}
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-300 flex items-center justify-between">
                        <span className="flex items-center gap-1">
                          <FileAudio className="w-3.5 h-3.5 text-indigo-400" />
                          Meeting Audio Payload (Max 500 MB)
                        </span>
                        {selectedFile && (
                          <span className="text-[11px] text-teal-400 font-mono font-bold">
                            {(selectedFile.size / (1024 * 1024)).toFixed(1)} MB
                          </span>
                        )}
                      </label>

                      {/* Drag and Drop Zone */}
                      <div
                        onDragOver={(e) => {
                          e.preventDefault();
                          setIntakeDragActive(true);
                        }}
                        onDragLeave={() => setIntakeDragActive(false)}
                        onDrop={(e) => {
                          e.preventDefault();
                          setIntakeDragActive(false);
                          handleIntakeFileSelect(e.dataTransfer.files);
                        }}
                        onClick={() => fileInputRef.current?.click()}
                        className={`border-2 border-dashed rounded-2xl p-5 text-center cursor-pointer transition-all flex flex-col items-center justify-center min-h-[160px] ${
                          intakeDragActive
                            ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300 scale-[1.02]'
                            : selectedFile
                            ? 'border-teal-500/60 bg-teal-950/20 text-teal-200'
                            : 'border-slate-700 hover:border-indigo-500 bg-slate-950/60 text-slate-400'
                        }`}
                      >
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept="audio/*,video/*,.mp3,.wav,.m4a,.flac,.aac"
                          className="hidden"
                          onChange={(e) => handleIntakeFileSelect(e.target.files)}
                        />

                        {selectedFile ? (
                          <div className="space-y-2">
                            <div className="w-10 h-10 rounded-full bg-teal-500/20 text-teal-400 flex items-center justify-center mx-auto border border-teal-500/40">
                              <FileCheck className="w-5 h-5" />
                            </div>
                            <div className="text-xs font-bold text-white max-w-[220px] truncate">
                              {selectedFile.name}
                            </div>
                            <p className="text-[11px] text-teal-400">
                              Ready for Open-MOSS Ingestion (Click to change)
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            <div className="w-10 h-10 rounded-full bg-indigo-500/15 text-indigo-400 flex items-center justify-center mx-auto border border-indigo-500/30">
                              <Upload className="w-5 h-5" />
                            </div>
                            <div className="text-xs font-bold text-slate-200">
                              Drop audio file here or click to browse
                            </div>
                            <p className="text-[11px] text-slate-500">
                              Supports WAV, MP3, M4A, FLAC up to 500 MB
                            </p>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Auto-Process Option */}
                    <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 space-y-2">
                      <label className="flex items-center space-x-2.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={autoProcess}
                          onChange={(e) => setAutoProcess(e.target.checked)}
                          className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                        />
                        <span className="text-xs font-semibold text-slate-200">
                          Auto-trigger Open-MOSS Diarization upon upload
                        </span>
                      </label>
                      <p className="text-[11px] text-slate-500 pl-6">
                        Runs acoustic chunking, speaker reconciliation, and multi-agent synthesis immediately.
                      </p>
                    </div>

                    {/* Submit Actions */}
                    <div className="pt-2 flex items-center justify-end gap-2.5">
                      <button
                        type="button"
                        onClick={() => setIsIntakeExpanded(false)}
                        className="px-4 py-2.5 rounded-xl text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        id="btn-submit-intake"
                        type="submit"
                        disabled={!title.trim()}
                        className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold shadow-lg shadow-indigo-600/30 transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <Zap className="w-3.5 h-3.5" />
                        <span>Initialize &amp; Ingest Meeting</span>
                      </button>
                    </div>
                  </div>
                </div>
              </form>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search meetings by title, speaker, domain, or language..."
            className={`w-full pl-9 pr-4 py-2.5 rounded-xl text-xs border focus:outline-none transition-all ${
              theme === 'dark'
                ? 'bg-slate-900/90 border-slate-800 text-slate-200 placeholder:text-slate-500 focus:border-indigo-500'
                : 'bg-white border-slate-200 text-slate-800 placeholder:text-slate-400 focus:border-indigo-600'
            }`}
          />
        </div>

        {/* Status Filter Chips and Remove Selected Action */}
        <div className="flex items-center gap-2 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
          <div className="flex items-center gap-1.5">
            {(['all', 'completed', 'processing', 'created'] as const).map(status => (
              <button
                key={`filter-${status}`}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium capitalize border transition-all shrink-0 cursor-pointer ${
                  statusFilter === status
                    ? 'bg-indigo-600 text-white border-indigo-600 font-semibold shadow-xs'
                    : theme === 'dark'
                    ? 'bg-slate-900/60 text-slate-400 border-slate-800 hover:text-slate-200 hover:border-slate-700'
                    : 'bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200'
                }`}
              >
                {status === 'all' ? `All (${meetings.length})` : status}
              </button>
            ))}
          </div>

          {/* Remove Selected Button if a meeting is selected */}
          {selectedMeetingId && onDeleteMeeting && (
            <button
              id="btn-remove-selected-meeting"
              type="button"
              onClick={() => {
                const target = meetings.find(m => m.id === selectedMeetingId);
                if (target) setMeetingToDelete(target);
              }}
              className="px-3 py-1.5 rounded-xl text-xs font-medium bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 border border-rose-800/60 hover:border-rose-700 transition-all flex items-center gap-1.5 shrink-0 cursor-pointer"
              title="Remove currently selected meeting session"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-400" />
              <span>Remove Selected</span>
            </button>
          )}
        </div>
      </div>

      {/* Empty State when no meetings */}
      {filteredMeetings.length === 0 && (
        <div className="text-center py-12 px-4 rounded-2xl border border-dashed border-slate-800 bg-slate-950/40 space-y-4">
          <div className="w-12 h-12 rounded-full bg-slate-900 border border-slate-800 text-slate-500 flex items-center justify-center mx-auto">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">No meeting sessions found</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              {searchQuery || statusFilter !== 'all'
                ? 'Try adjusting your search query or status filter.'
                : 'All meetings have been removed or none created yet.'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setIsIntakeExpanded(true)}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-md shadow-indigo-600/30 transition-colors inline-flex items-center gap-1.5 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create New Meeting Session</span>
          </button>
        </div>
      )}

      {/* RECREATED MEETING CARDS LIST */}
      <div className="grid grid-cols-1 gap-4">
        {filteredMeetings.map((m) => {
          const isSelected = selectedMeetingId === m.id;
          const isUploading = uploadingId === m.id;
          const isDragActive = dragActiveId === m.id;
          const isPlaying = playingMeetingId === m.id;

          return (
            <div
              key={m.id}
              id={`meeting-card-${m.id}`}
              onClick={() => onSelectMeeting(m.id)}
              className={`rounded-2xl border p-5 transition-all cursor-pointer relative overflow-hidden ${
                isSelected
                  ? theme === 'dark'
                    ? 'bg-slate-900 border-indigo-500 ring-2 ring-indigo-500/30 shadow-xl shadow-indigo-950/40'
                    : 'bg-white border-indigo-500 ring-2 ring-indigo-500/30 shadow-md shadow-indigo-100'
                  : theme === 'dark'
                  ? 'bg-slate-900/70 border-slate-800/80 hover:bg-slate-900 hover:border-slate-700'
                  : 'bg-white border-slate-200 hover:border-slate-300 hover:shadow-xs'
              }`}
            >
              {/* Selected Accent Line */}
              {isSelected && (
                <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-teal-400" />
              )}

              <div className="space-y-4">
                {/* Card Top Row */}
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-base font-bold text-white tracking-tight truncate">
                        {m.title}
                      </h3>
                      {getStatusBadge(m.status)}
                      <span
                        className={`uppercase px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold border ${
                          theme === 'dark'
                            ? 'bg-slate-950 border-slate-800 text-indigo-300'
                            : 'bg-slate-100 border-slate-200 text-indigo-700'
                        }`}
                      >
                        {m.primary_language}
                      </span>
                      {m.category && (
                        <span className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-950 text-slate-400 border border-slate-800">
                          {m.category}
                        </span>
                      )}
                    </div>

                    <p className={`text-xs max-w-4xl line-clamp-2 ${theme === 'dark' ? 'text-slate-400' : 'text-slate-600'}`}>
                      {m.description}
                    </p>
                  </div>

                  {/* Top Right Quick Actions */}
                  <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
                    {onViewIntelligence && m.status === 'completed' && (
                      <button
                        type="button"
                        onClick={() => onViewIntelligence(m.id)}
                        className="px-3 py-1.5 rounded-xl bg-purple-950/80 hover:bg-purple-900 border border-purple-800/80 text-purple-200 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                        title="View Multi-Agent Intelligence & Decisions"
                      >
                        <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                        <span>View Intel</span>
                      </button>
                    )}

                    {/* Prominent Remove Meeting Option */}
                    {onDeleteMeeting && (
                      <button
                        id={`btn-remove-meeting-${m.id}`}
                        type="button"
                        onClick={() => setMeetingToDelete(m)}
                        className="px-2.5 py-1.5 rounded-xl bg-slate-950/80 hover:bg-rose-950/80 text-slate-400 hover:text-rose-300 border border-slate-800 hover:border-rose-800/80 text-xs font-medium flex items-center gap-1.5 transition-all cursor-pointer group"
                        title="Remove this meeting session"
                      >
                        <Trash2 className="w-3.5 h-3.5 text-slate-500 group-hover:text-rose-400 transition-colors" />
                        <span>Remove</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Card Middle: Speaker & Time Telemetry Strip */}
                <div className="flex flex-wrap items-center justify-between gap-4 py-2 px-3 rounded-xl bg-slate-950/60 border border-slate-800/60 text-xs">
                  <div className="flex flex-wrap items-center gap-4 text-slate-400 font-mono">
                    <span className="flex items-center gap-1.5 text-slate-300">
                      <Clock className="w-3.5 h-3.5 text-indigo-400" />
                      <span>{m.duration_minutes || 45} mins</span>
                    </span>

                    <span className="flex items-center gap-1.5 text-slate-300">
                      <Users className="w-3.5 h-3.5 text-teal-400" />
                      <span>{m.participants?.length || 1} Speakers</span>
                      <span className="text-[11px] text-slate-500 truncate max-w-[240px]">
                        ({m.participants?.join(', ') || 'Lead Speaker'})
                      </span>
                    </span>

                    <span className="flex items-center gap-1.5 text-slate-500 text-[11px]">
                      <Calendar className="w-3.5 h-3.5" />
                      <span>{new Date(m.created_at).toLocaleDateString()}</span>
                    </span>
                  </div>

                  {/* Audio Status Pill */}
                  <div>
                    {m.audio_uploaded ? (
                      <span className="inline-flex items-center gap-1.5 text-teal-400 text-xs font-semibold">
                        <FileCheck className="w-3.5 h-3.5" />
                        <span className="truncate max-w-[180px]">{m.audio_file_name || 'Audio Payload Attached'}</span>
                        {m.audio_file_size_mb && <span className="font-mono text-[11px]">({m.audio_file_size_mb} MB)</span>}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-amber-400 text-xs">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span>No audio uploaded</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Bottom: Interactive Ingestion & Action Deck */}
                <div
                  className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-1"
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Audio Upload / Re-Upload Zone */}
                  <div className="flex-1">
                    <div
                      onDragOver={(e) => {
                        e.preventDefault();
                        setDragActiveId(m.id);
                      }}
                      onDragLeave={() => setDragActiveId(null)}
                      onDrop={(e) => {
                        e.preventDefault();
                        setDragActiveId(null);
                        handleCardFileDrop(m.id, e.dataTransfer.files);
                      }}
                      className={`relative px-4 py-2.5 rounded-xl border border-dashed text-xs flex items-center justify-between gap-2 transition-all ${
                        isDragActive
                          ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300'
                          : m.audio_uploaded
                          ? 'border-teal-500/40 bg-teal-950/20 text-teal-300 hover:border-teal-500'
                          : theme === 'dark'
                          ? 'border-slate-700 bg-slate-950/80 hover:border-indigo-500 text-slate-300'
                          : 'border-slate-300 bg-slate-50 hover:border-indigo-600 text-slate-700'
                      }`}
                    >
                      <div className="flex items-center gap-2 truncate">
                        <Upload className="w-4 h-4 text-indigo-400 shrink-0" />
                        <label className="cursor-pointer font-medium truncate">
                          <span>{m.audio_uploaded ? 'Re-upload Audio File (WAV/MP3/M4A)' : 'Upload Audio Payload (Max 500 MB)'}</span>
                          <input
                            type="file"
                            accept="audio/*,video/*,.mp3,.wav,.m4a,.flac,.aac"
                            className="hidden"
                            onChange={(e) => handleCardFileDrop(m.id, e.target.files)}
                          />
                        </label>
                      </div>

                      {/* Simulated Audio Playback Waveform if uploaded */}
                      {m.audio_uploaded && (
                        <button
                          type="button"
                          onClick={() => setPlayingMeetingId(isPlaying ? null : m.id)}
                          className="px-2.5 py-1 rounded-lg bg-teal-950 hover:bg-teal-900 border border-teal-800/80 text-teal-300 text-[11px] font-semibold flex items-center gap-1 shrink-0 cursor-pointer"
                        >
                          {isPlaying ? (
                            <>
                              <Pause className="w-3 h-3" />
                              <span>Pause</span>
                            </>
                          ) : (
                            <>
                              <Play className="w-3 h-3 fill-current" />
                              <span>Play Audio</span>
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Process Action Button */}
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      id={`btn-process-meeting-${m.id}`}
                      disabled={m.status === 'processing'}
                      onClick={() => onProcessMeeting(m.id)}
                      className={`px-4 py-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-md cursor-pointer ${
                        m.status === 'processing'
                          ? 'bg-indigo-600/50 text-white cursor-not-allowed'
                          : m.status === 'completed'
                          ? 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600'
                          : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-600/25 active:scale-95'
                      }`}
                    >
                      {m.status === 'processing' ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          <span>Open-MOSS Synthesizing...</span>
                        </>
                      ) : m.status === 'completed' ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5" />
                          <span>Re-run ACE Pipeline</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>Run Open-MOSS Pipeline</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Upload Progress Bar */}
                {isUploading && (
                  <div className="pt-2 border-t border-slate-800 animate-in fade-in duration-200">
                    <div className="flex items-center justify-between text-xs font-mono mb-1.5 text-indigo-400">
                      <span className="flex items-center gap-1.5">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        Chunking &amp; Ingesting Audio Payload into Buffer...
                      </span>
                      <span>{uploadProgress}%</span>
                    </div>
                    <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
                      <div
                        className="bg-gradient-to-r from-indigo-500 via-purple-500 to-teal-400 h-2 rounded-full transition-all duration-300"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* CONFIRM DELETE MODAL */}
      <AnimatePresence>
        {meetingToDelete && (
          <div
            id="modal-confirm-remove-meeting"
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-slate-900 border border-slate-800 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-5 text-slate-100"
            >
              <div className="flex items-start gap-3.5">
                <div className="p-3 rounded-xl bg-rose-500/15 text-rose-400 border border-rose-500/30 shrink-0">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-base font-bold text-white">
                    Remove Meeting Session?
                  </h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Are you sure you want to remove <span className="text-white font-semibold">&ldquo;{meetingToDelete.title}&rdquo;</span>?
                  </p>
                </div>
              </div>

              {/* Summary Details Box */}
              <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800/80 text-xs space-y-2 font-mono">
                <div className="flex justify-between text-slate-400">
                  <span>Language:</span>
                  <span className="text-indigo-300 uppercase">{meetingToDelete.primary_language}</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Duration:</span>
                  <span className="text-slate-200">{meetingToDelete.duration_minutes || 45} mins</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Status:</span>
                  <span className="text-slate-200 capitalize">{meetingToDelete.status}</span>
                </div>
                {meetingToDelete.audio_uploaded && (
                  <div className="flex justify-between text-slate-400">
                    <span>Attached Audio:</span>
                    <span className="text-teal-400 truncate max-w-[180px]">
                      {meetingToDelete.audio_file_name || 'Audio Payload'}
                    </span>
                  </div>
                )}
              </div>

              <p className="text-[11px] text-rose-400/90 leading-normal">
                Notice: This will remove this meeting session from your active ABCI-MI registry along with its temporary in-memory diarization graph and transcripts.
              </p>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  id="btn-cancel-remove-meeting"
                  type="button"
                  onClick={() => setMeetingToDelete(null)}
                  className="px-4 py-2.5 rounded-xl text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  id="btn-confirm-remove-meeting"
                  type="button"
                  onClick={confirmDelete}
                  className="px-4 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-lg shadow-rose-600/30 transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Yes, Remove Meeting</span>
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
