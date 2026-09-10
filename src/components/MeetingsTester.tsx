import React, { useState } from 'react';
import {
  Plus,
  Upload,
  Play,
  CheckCircle2,
  Clock,
  AlertCircle,
  FileAudio,
  Loader2,
  Sparkles,
  Calendar,
  Users,
  RefreshCw
} from 'lucide-react';
import { MeetingItem, MeetingStatus } from '../types';

interface MeetingsTesterProps {
  meetings: MeetingItem[];
  selectedMeetingId: string;
  onSelectMeeting: (id: string) => void;
  onCreateMeeting: (title: string, description: string, language: string) => void;
  onUploadAudio: (meetingId: string, file: File) => void;
  onProcessMeeting: (meetingId: string) => void;
}

export const MeetingsTester: React.FC<MeetingsTesterProps> = ({
  meetings,
  selectedMeetingId,
  onSelectMeeting,
  onCreateMeeting,
  onUploadAudio,
  onProcessMeeting
}) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newLang, setNewLang] = useState('en');
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    onCreateMeeting(newTitle, newDesc, newLang);
    setNewTitle('');
    setNewDesc('');
    setShowCreateModal(false);
  };

  const handleFileDrop = (meetingId: string, files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    
    // Check max size (500MB)
    const maxSizeBytes = 500 * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      alert('Error: File size exceeds the maximum limit of 500 MB.');
      return;
    }
    
    setUploadingId(meetingId);
    setUploadProgress(15);
    const interval = setInterval(() => {
      setUploadProgress(prev => {
        if (prev >= 95) {
          clearInterval(interval);
          setTimeout(() => {
            onUploadAudio(meetingId, file);
            setUploadingId(null);
            setUploadProgress(0);
          }, 300);
          return 100;
        }
        return prev + 25;
      });
    }, 150);
  };

  const getStatusBadge = (status: MeetingStatus) => {
    switch (status) {
      case 'completed':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800"><CheckCircle2 className="w-3 h-3 mr-1" /> Ready</span>;
      case 'processing':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-950 text-indigo-400 border border-indigo-800 animate-pulse"><Loader2 className="w-3 h-3 mr-1 animate-spin" /> Processing</span>;
      case 'live':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-rose-950 text-rose-400 border border-rose-800 animate-pulse"><span className="w-1.5 h-1.5 rounded-full bg-rose-400 mr-1.5 animate-ping" /> Live</span>;
      case 'paused':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-950 text-amber-400 border border-amber-800"><Clock className="w-3 h-3 mr-1" /> Paused</span>;
      case 'scheduled':
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-950 text-blue-400 border border-blue-800"><Calendar className="w-3 h-3 mr-1" /> Scheduled</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-neutral-900 text-neutral-400 border border-neutral-800"><Clock className="w-3 h-3 mr-1" /> Created</span>;
    }
  };

  return (
    <div id="meetings-tester-container" className="space-y-6">
      {/* Header and Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-neutral-900/60 p-5 rounded-xl border border-neutral-800">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-400" />
            Meetings & Ingestion Pipeline
          </h2>
          <p className="text-xs text-neutral-400 mt-1">
            Create meeting sessions, upload batch audio/video recordings (up to 500 MB), and trigger the ACE Blackboard synthesis engine.
          </p>
        </div>
        <button
          id="btn-create-new-meeting"
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm transition-colors"
        >
          <Plus className="w-4 h-4 mr-1.5" />
          Initialize New Meeting
        </button>
      </div>

      {/* Creation Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-neutral-900 border border-neutral-800 rounded-xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
              <h3 className="text-sm font-bold text-white">Initialize Meeting Session</h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-neutral-400 hover:text-neutral-200 text-xs"
              >
                Cancel
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">Meeting Title *</label>
                <input
                  id="input-meeting-title"
                  type="text"
                  required
                  placeholder="e.g., Sprint Architecture Review"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">Description</label>
                <textarea
                  id="input-meeting-desc"
                  rows={3}
                  placeholder="Describe the context and goals..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-300 mb-1">Spoken Language</label>
                <select
                  id="select-meeting-lang"
                  value={newLang}
                  onChange={(e) => setNewLang(e.target.value)}
                  className="w-full bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-indigo-500"
                >
                  <optgroup label="Global Locales">
                    <option value="en">English (en)</option>
                    <option value="es">Spanish / Español (es)</option>
                    <option value="fr">French / Français (fr)</option>
                    <option value="de">German / Deutsch (de)</option>
                    <option value="zh">Mandarin / 中文 (zh)</option>
                    <option value="ja">Japanese / 日本語 (ja)</option>
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
                  <optgroup label="Code-Switched Dialects">
                    <option value="hinglish">Hinglish / हिंग्लिश (hi-en)</option>
                    <option value="tanglish">Tanglish / தாங்கிலிஷ் (ta-en)</option>
                    <option value="spanglish">Spanglish (es-en)</option>
                    <option value="franglais">Franglais (fr-en)</option>
                    <option value="arabiya-english">Arabiya-English (ar-en)</option>
                  </optgroup>
                </select>
              </div>
              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-3 py-1.5 rounded-lg text-xs text-neutral-400 hover:bg-neutral-800"
                >
                  Cancel
                </button>
                <button
                  id="btn-submit-create-meeting"
                  type="submit"
                  className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white"
                >
                  Create Session
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Meetings List View */}
      <div className="bg-neutral-950 rounded-xl border border-neutral-800 overflow-hidden">
        <div className="divide-y divide-neutral-900">
          {meetings.map((m) => {
            const isSelected = selectedMeetingId === m.id;
            const isUploading = uploadingId === m.id;

            return (
              <div
                key={m.id}
                id={`meeting-row-${m.id}`}
                onClick={() => onSelectMeeting(m.id)}
                className={`p-4 transition-all cursor-pointer flex flex-col md:flex-row md:items-center justify-between gap-4 ${
                  isSelected
                    ? 'bg-neutral-900/90 border-l-4 border-l-indigo-500'
                    : 'hover:bg-neutral-900/50'
                }`}
              >
                {/* Left Info Column */}
                <div className="space-y-1.5 flex-1 min-w-0">
                  <div className="flex items-center space-x-3">
                    <h3 className="text-sm font-bold text-white tracking-tight truncate">{m.title}</h3>
                    {getStatusBadge(m.status)}
                    <span className="uppercase px-1.5 py-0.5 rounded text-[10px] bg-neutral-900 text-neutral-400 border border-neutral-800 font-mono">
                      {m.primary_language}
                    </span>
                  </div>
                  <p className="text-xs text-neutral-400 truncate max-w-2xl">{m.description}</p>
                  
                  <div className="flex items-center gap-4 text-[11px] text-neutral-400 pt-1">
                    <span className="flex items-center">
                      <Clock className="w-3 h-3 mr-1 text-neutral-500" />
                      {m.duration_minutes || 0} mins
                    </span>
                    <span className="flex items-center">
                      <Users className="w-3 h-3 mr-1 text-neutral-500" />
                      {m.participants.length} participants
                    </span>
                    <span className="text-neutral-500 font-mono text-[10px]">
                      ID: {m.id}
                    </span>
                  </div>
                </div>

                {/* Right Ingestion & Actions Column */}
                <div className="flex items-center gap-3 shrink-0" onClick={(e) => e.stopPropagation()}>
                  {m.audio_uploaded ? (
                    <div className="flex items-center gap-3 bg-neutral-900 px-3 py-2 rounded-lg border border-neutral-800 text-xs">
                      <div className="flex items-center space-x-2 text-neutral-300">
                        <FileAudio className="w-4 h-4 text-indigo-400 shrink-0" />
                        <span className="truncate max-w-[140px] font-mono text-[11px]">{m.audio_file_name}</span>
                        <span className="text-[10px] text-neutral-500">({m.audio_file_size_mb} MB)</span>
                      </div>
                      {m.status === 'processing' ? (
                        <span className="text-[11px] text-indigo-400 flex items-center shrink-0">
                          <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                          ACE Pipeline...
                        </span>
                      ) : (
                        <button
                          id={`btn-reprocess-${m.id}`}
                          onClick={() => onProcessMeeting(m.id)}
                          className="px-2.5 py-1 rounded bg-indigo-950 hover:bg-indigo-900 text-indigo-300 border border-indigo-800 text-xs font-medium flex items-center transition-colors shrink-0"
                        >
                          <RefreshCw className="w-3 h-3 mr-1" />
                          {m.status === 'completed' ? 'Re-run' : 'Run Pipeline'}
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      {isUploading ? (
                        <div className="bg-neutral-900 px-3 py-2 rounded-lg border border-neutral-800 text-xs flex items-center space-x-2 w-48">
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400 shrink-0" />
                          <div className="w-full space-y-1">
                            <div className="flex justify-between text-[10px] text-neutral-400">
                              <span>Uploading</span>
                              <span>{uploadProgress}%</span>
                            </div>
                            <div className="w-full bg-neutral-950 rounded-full h-1 overflow-hidden">
                              <div className="bg-indigo-500 h-full transition-all duration-200" style={{ width: `${uploadProgress}%` }} />
                            </div>
                          </div>
                        </div>
                      ) : (
                        <label className="cursor-pointer px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-neutral-800 text-xs text-neutral-200 font-medium border border-neutral-800 flex items-center gap-1.5 transition-colors">
                          <Upload className="w-3.5 h-3.5 text-neutral-400" />
                          <span>Upload Recording (.mp3/.wav)</span>
                          <input
                            type="file"
                            accept="audio/*,video/*,.mp3,.wav,.m4a,.flac,.ogg,.mp4,.webm"
                            className="hidden"
                            onChange={(e) => handleFileDrop(m.id, e.target.files)}
                          />
                        </label>
                      )}
                    </div>
                  )}

                  <button
                    onClick={() => onSelectMeeting(m.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      isSelected
                        ? 'bg-indigo-600 text-white'
                        : 'bg-neutral-900 hover:bg-neutral-800 text-neutral-300 border border-neutral-800'
                    }`}
                  >
                    {isSelected ? 'Active Session' : 'Select'}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
