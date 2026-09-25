import React, { useState, useRef } from 'react';
import {
  X,
  User,
  Mail,
  Shield,
  Building,
  FileText,
  Clock,
  Phone,
  Globe,
  Upload,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Key,
  Lock,
  Activity,
  Eye,
  Check,
  Calendar,
  Layers,
  Terminal,
  RefreshCw,
  LogOut,
  Sliders
} from 'lucide-react';
import { AuthContext, AuditLogItem } from '../types';

interface ProfileSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  auth: AuthContext;
  onUpdateProfile: (updated: Partial<AuthContext>) => void;
  onResetProfile: () => void;
  theme: 'dark' | 'light';
  auditLogs?: AuditLogItem[];
}

const DEFAULT_AVATAR = '/src/assets/images/workspace_executive_avatar_1790188244518.jpg';

const AVATAR_PRESETS = [
  {
    id: 'executive',
    label: 'Executive Leader',
    url: '/src/assets/images/workspace_executive_avatar_1790188244518.jpg',
    color: 'from-indigo-500 to-purple-600'
  },
  {
    id: 'acoustic_ai',
    label: 'Acoustic AI Specialist',
    url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
    color: 'from-blue-500 to-cyan-500'
  },
  {
    id: 'security',
    label: 'Security Officer',
    url: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80',
    color: 'from-emerald-500 to-teal-500'
  },
  {
    id: 'researcher',
    label: 'Speech Scientist',
    url: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop&q=80',
    color: 'from-amber-500 to-rose-500'
  }
];

const ROLES_LIST: Array<{ role: AuthContext['role']; label: string; desc: string; permissions: string[] }> = [
  {
    role: 'admin',
    label: 'System Administrator',
    desc: 'Full administrative control over pipelines, security logs, benchmark runs, and user access.',
    permissions: ['Ingest & Diarize Audio', 'Manage Knowledge Base', 'View & Export Audit Logs', 'Execute System Health Probes', 'Configure RBAC']
  },
  {
    role: 'host',
    label: 'Meeting Host & Organizer',
    desc: 'Authorized to schedule sessions, stream live microphone audio, edit meeting roster, and export reports.',
    permissions: ['Ingest & Diarize Audio', 'Manage Knowledge Base', 'Export Meeting Intelligence', 'Run Grounded Queries']
  },
  {
    role: 'security_officer',
    label: 'Security & Compliance Officer',
    desc: 'Dedicated role for inspecting cryptographic audit trails, verifying zero-retention compliance, and export checks.',
    permissions: ['View & Export Audit Logs', 'Inspect API Telemetry', 'Verify SHA-256 Signatures', 'Enforce Compliance Filters']
  },
  {
    role: 'member',
    label: 'Team Member (Analyst)',
    desc: 'Read and query access to meeting intelligence, semantic search, and multi-language translations.',
    permissions: ['View Meeting Intelligence', 'Run Grounded Queries', 'Request Translations', 'Read Knowledge Objects']
  }
];

export const ProfileSettingsModal: React.FC<ProfileSettingsModalProps> = ({
  isOpen,
  onClose,
  auth,
  onUpdateProfile,
  onResetProfile,
  theme,
  auditLogs = []
}) => {
  if (!isOpen) return null;

  // Active View Tab
  const [activeTab, setActiveTab] = useState<'update' | 'observe' | 'remove'>('update');

  // Form State
  const [userName, setUserName] = useState(auth.user_name);
  const [userEmail, setUserEmail] = useState(auth.user_email);
  const [role, setRole] = useState<AuthContext['role']>(auth.role);
  const [department, setDepartment] = useState(auth.department || 'Acoustic AI & Speech Intelligence');
  const [bio, setBio] = useState(auth.bio || 'Principal Speech Systems Architect leading multi-speaker acoustic diarization & semantic knowledge extraction.');
  const [phone, setPhone] = useState(auth.phone || '+1 (555) 839-2041');
  const [timezone, setTimezone] = useState(auth.timezone || 'America/Los_Angeles (PST)');
  const [locale, setLocale] = useState(auth.locale || 'en-US');
  const [avatarUrl, setAvatarUrl] = useState(auth.avatar_url || DEFAULT_AVATAR);

  // Status & Feedback
  const [notificationMsg, setNotificationMsg] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);
  const [showTokenSecret, setShowTokenSecret] = useState(false);
  const [confirmResetOpen, setConfirmResetOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Flash Feedback Helper
  const showFeedback = (text: string, type: 'success' | 'error' | 'info' = 'success') => {
    setNotificationMsg({ type, text });
    setTimeout(() => {
      setNotificationMsg(null);
    }, 4000);
  };

  // Handle Save / Modify Profile
  const handleSaveProfile = (e?: React.FormEvent) => {
    if (e) e.preventDefault();

    if (!userName.trim()) {
      showFeedback('User name cannot be blank', 'error');
      return;
    }
    if (!userEmail.trim() || !userEmail.includes('@')) {
      showFeedback('Please provide a valid corporate email address', 'error');
      return;
    }

    onUpdateProfile({
      user_name: userName.trim(),
      user_email: userEmail.trim(),
      role,
      department: department.trim(),
      bio: bio.trim(),
      phone: phone.trim(),
      timezone,
      locale,
      avatarUrl: avatarUrl
    });

    showFeedback('Profile attributes updated and persisted successfully.');
  };

  // Handle Custom Image File Upload
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      showFeedback('Please select a valid image file (PNG, JPG, WebP)', 'error');
      return;
    }

    // Limit to 3MB
    if (file.size > 3 * 1024 * 1024) {
      showFeedback('Image file size exceeds 3MB limit', 'error');
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const dataUrl = event.target?.result as string;
      if (dataUrl) {
        setAvatarUrl(dataUrl);
        onUpdateProfile({ avatar_url: dataUrl });
        showFeedback('Custom profile picture uploaded and applied.');
      }
    };
    reader.readAsDataURL(file);
  };

  // Handle Remove Avatar
  const handleRemoveAvatar = () => {
    // Revert to empty string so it falls back to user initials or default
    setAvatarUrl('');
    onUpdateProfile({ avatar_url: '' });
    showFeedback('Profile picture removed. Reverted to system initials avatar.');
  };

  // Handle Clear Specific Field
  const handleClearField = (field: 'bio' | 'department' | 'phone') => {
    if (field === 'bio') {
      setBio('');
      onUpdateProfile({ bio: '' });
      showFeedback('User biography removed.');
    } else if (field === 'department') {
      setDepartment('');
      onUpdateProfile({ department: '' });
      showFeedback('Department field cleared.');
    } else if (field === 'phone') {
      setPhone('');
      onUpdateProfile({ phone: '' });
      showFeedback('Phone contact removed.');
    }
  };

  // Handle Full Reset to Defaults
  const handleExecuteReset = () => {
    onResetProfile();
    setUserName('Dr. Elena Vance');
    setUserEmail('elena.vance@enterprise-speech.ai');
    setRole('admin');
    setDepartment('Acoustic AI & Speech Intelligence');
    setBio('Principal Speech Systems Architect leading multi-speaker acoustic diarization & semantic knowledge extraction.');
    setPhone('+1 (555) 839-2041');
    setTimezone('America/Los_Angeles (PST)');
    setLocale('en-US');
    setAvatarUrl(DEFAULT_AVATAR);
    setConfirmResetOpen(false);
    showFeedback('Profile reset to factory defaults.');
  };

  // Role details of current selection
  const currentRoleInfo = ROLES_LIST.find(r => r.role === role) || ROLES_LIST[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-sm overflow-y-auto">
      <div
        id="profile-settings-modal"
        className={`w-full max-w-4xl rounded-2xl border shadow-2xl transition-all overflow-hidden my-auto ${
          theme === 'dark'
            ? 'bg-slate-900 border-slate-800 text-slate-100'
            : 'bg-white border-slate-200 text-slate-900'
        }`}
      >
        {/* Top Header Bar */}
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <User className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold tracking-tight text-slate-900 dark:text-white">
                Account &amp; Profile Settings
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Update credentials, modify avatar, observe live security telemetry, or manage profile removal
              </p>
            </div>
          </div>

          <button
            id="btn-close-profile-modal"
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Feedback Alert Toast */}
        {notificationMsg && (
          <div
            className={`px-6 py-2.5 text-xs flex items-center justify-between border-b ${
              notificationMsg.type === 'error'
                ? 'bg-rose-500/10 border-rose-500/30 text-rose-400'
                : notificationMsg.type === 'info'
                ? 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
            }`}
          >
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span className="font-medium">{notificationMsg.text}</span>
            </div>
            <button
              onClick={() => setNotificationMsg(null)}
              className="p-0.5 text-slate-400 hover:text-slate-200"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Quick User Identity Summary Ribbon */}
        <div className="px-6 py-3 bg-slate-50 dark:bg-slate-950/60 border-b border-slate-200 dark:border-slate-800 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt={userName}
                className="w-10 h-10 rounded-full object-cover border-2 border-indigo-500/50 shadow-sm"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="w-10 h-10 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-sm shadow-sm">
                {userName.substring(0, 2).toUpperCase()}
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-slate-900 dark:text-white">{userName}</span>
                <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-md bg-indigo-100 dark:bg-indigo-950/80 text-indigo-700 dark:text-indigo-300 font-semibold border border-indigo-200 dark:border-indigo-800">
                  {role}
                </span>
              </div>
              <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
                <span>{userEmail}</span>
                <span>&bull;</span>
                <span>{department}</span>
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center p-1 rounded-xl bg-slate-200/70 dark:bg-slate-900 border border-slate-300 dark:border-slate-800 text-xs font-semibold">
            <button
              id="tab-profile-update"
              type="button"
              onClick={() => setActiveTab('update')}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                activeTab === 'update'
                  ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >
              <Sliders className="w-3.5 h-3.5 text-indigo-400" />
              <span>Modify &amp; Update</span>
            </button>

            <button
              id="tab-profile-observe"
              type="button"
              onClick={() => setActiveTab('observe')}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                activeTab === 'observe'
                  ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-xs'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >
              <Eye className="w-3.5 h-3.5 text-emerald-400" />
              <span>Observe &amp; Telemetry</span>
            </button>

            <button
              id="tab-profile-remove"
              type="button"
              onClick={() => setActiveTab('remove')}
              className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                activeTab === 'remove'
                  ? 'bg-white dark:bg-slate-800 text-rose-600 dark:text-rose-400 shadow-xs'
                  : 'text-slate-600 dark:text-slate-400 hover:text-rose-500'
              }`}
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-500" />
              <span>Remove &amp; Reset</span>
            </button>
          </div>
        </div>

        {/* Tab 1: UPDATE & MODIFY */}
        {activeTab === 'update' && (
          <div className="p-6 space-y-6 max-h-[68vh] overflow-y-auto">
            {/* Avatar Management Section */}
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    Profile Avatar Picture
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Upload an avatar image, choose a high-resolution preset, or revert to system initials.
                  </p>
                </div>

                {avatarUrl && (
                  <button
                    type="button"
                    onClick={handleRemoveAvatar}
                    className="text-xs text-rose-500 hover:text-rose-400 font-medium flex items-center gap-1"
                    title="Remove profile image"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Remove Picture</span>
                  </button>
                )}
              </div>

              <div className="flex flex-col sm:flex-row items-center gap-6 pt-2">
                {/* Current Avatar with Hover Overlay */}
                <div className="relative group shrink-0">
                  {avatarUrl ? (
                    <img
                      src={avatarUrl}
                      alt={userName}
                      className="w-20 h-20 rounded-2xl object-cover border-2 border-indigo-500/40 shadow-md group-hover:opacity-85 transition-all"
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-700 text-white font-bold flex items-center justify-center text-xl shadow-md">
                      {userName.substring(0, 2).toUpperCase()}
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="absolute inset-0 flex items-center justify-center bg-black/60 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity text-white text-xs font-medium gap-1 cursor-pointer"
                    title="Upload new image"
                  >
                    <Upload className="w-4 h-4" />
                    <span>Upload</span>
                  </button>
                </div>

                <div className="space-y-2 flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm transition-colors cursor-pointer"
                    >
                      <Upload className="w-3.5 h-3.5" />
                      <span>Upload Custom Photo</span>
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handleFileUpload}
                      className="hidden"
                    />

                    <button
                      type="button"
                      onClick={() => {
                        setAvatarUrl(DEFAULT_AVATAR);
                        onUpdateProfile({ avatar_url: DEFAULT_AVATAR });
                        showFeedback('Executive avatar preset applied.');
                      }}
                      className="px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium transition-colors"
                    >
                      Use Executive Default
                    </button>
                  </div>

                  {/* Preset Quick Chips */}
                  <div className="pt-2">
                    <span className="text-[11px] text-slate-500 dark:text-slate-400 block mb-1.5">
                      Or pick from official persona presets:
                    </span>
                    <div className="flex flex-wrap items-center gap-2">
                      {AVATAR_PRESETS.map((preset) => (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => {
                            setAvatarUrl(preset.url);
                            onUpdateProfile({ avatar_url: preset.url });
                            showFeedback(`Applied "${preset.label}" avatar preset.`);
                          }}
                          className={`flex items-center gap-2 px-2.5 py-1 rounded-lg border text-xs font-medium transition-all ${
                            avatarUrl === preset.url
                              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 ring-1 ring-indigo-500/30'
                              : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
                          }`}
                        >
                          <img
                            src={preset.url}
                            alt={preset.label}
                            className="w-4 h-4 rounded-full object-cover"
                            referrerPolicy="no-referrer"
                          />
                          <span>{preset.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Core User Details Form */}
            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Full Name */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <User className="w-3.5 h-3.5 text-indigo-400" />
                      Full Name
                    </span>
                  </label>
                  <input
                    id="input-profile-name"
                    type="text"
                    value={userName}
                    onChange={(e) => setUserName(e.target.value)}
                    placeholder="e.g. Dr. Elena Vance"
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    required
                  />
                </div>

                {/* Corporate Email */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Mail className="w-3.5 h-3.5 text-indigo-400" />
                      Work Email
                    </span>
                  </label>
                  <input
                    id="input-profile-email"
                    type="email"
                    value={userEmail}
                    onChange={(e) => setUserEmail(e.target.value)}
                    placeholder="elena.vance@enterprise-speech.ai"
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    required
                  />
                </div>

                {/* Department */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                      <Building className="w-3.5 h-3.5 text-indigo-400" />
                      Department / Organization Unit
                    </label>
                    {department && (
                      <button
                        type="button"
                        onClick={() => handleClearField('department')}
                        className="text-[10px] text-slate-400 hover:text-rose-400"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                  <input
                    id="input-profile-department"
                    type="text"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="e.g. Acoustic AI & Speech Intelligence"
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                {/* Phone Contact */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                      <Phone className="w-3.5 h-3.5 text-indigo-400" />
                      Phone / Comm Line
                    </label>
                    {phone && (
                      <button
                        type="button"
                        onClick={() => handleClearField('phone')}
                        className="text-[10px] text-slate-400 hover:text-rose-400"
                      >
                        Clear
                      </button>
                    )}
                  </div>
                  <input
                    id="input-profile-phone"
                    type="text"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="+1 (555) 000-0000"
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>

                {/* Role Switcher */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5 text-indigo-400" />
                    Security Access Role
                  </label>
                  <select
                    id="select-profile-role"
                    value={role}
                    onChange={(e) => setRole(e.target.value as AuthContext['role'])}
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                  >
                    {ROLES_LIST.map((r) => (
                      <option key={r.role} value={r.role}>
                        {r.label} ({r.role})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Timezone & Region */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-indigo-400" />
                    Timezone Preference
                  </label>
                  <select
                    id="select-profile-timezone"
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                  >
                    <option value="America/Los_Angeles (PST)">America/Los_Angeles (PST, UTC-8)</option>
                    <option value="America/New_York (EST)">America/New_York (EST, UTC-5)</option>
                    <option value="Europe/London (GMT)">Europe/London (GMT, UTC+0)</option>
                    <option value="Europe/Berlin (CET)">Europe/Berlin (CET, UTC+1)</option>
                    <option value="Asia/Tokyo (JST)">Asia/Tokyo (JST, UTC+9)</option>
                    <option value="Asia/Shanghai (CST)">Asia/Shanghai (CST, UTC+8)</option>
                  </select>
                </div>
              </div>

              {/* Bio / Description */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-indigo-400" />
                    Professional Bio &amp; Specialty
                  </label>
                  {bio && (
                    <button
                      type="button"
                      onClick={() => handleClearField('bio')}
                      className="text-[10px] text-slate-400 hover:text-rose-400"
                    >
                      Clear Bio
                    </button>
                  )}
                </div>
                <textarea
                  id="input-profile-bio"
                  rows={2}
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                  placeholder="Describe your role or technical responsibilities..."
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
                />
              </div>

              {/* Bottom Action Buttons */}
              <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between">
                <div className="text-[11px] text-slate-500 dark:text-slate-400 font-mono">
                  Tenant: <span className="font-semibold text-slate-700 dark:text-slate-300">{auth.tenant_id}</span>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    id="btn-save-profile-changes"
                    type="submit"
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Save &amp; Apply Changes</span>
                  </button>
                </div>
              </div>
            </form>
          </div>
        )}

        {/* Tab 2: OBSERVE & TELEMETRY */}
        {activeTab === 'observe' && (
          <div className="p-6 space-y-6 max-h-[68vh] overflow-y-auto">
            {/* Live Observer Card (Mirrors How User is Displayed Everywhere) */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2">
                Live Profile Observer (Runtime Mirror)
              </h3>
              <div className="p-5 rounded-xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/40 via-slate-900/60 to-slate-900/40 shadow-sm relative overflow-hidden">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 relative z-10">
                  <div className="flex items-center gap-4">
                    {avatarUrl ? (
                      <img
                        src={avatarUrl}
                        alt={userName}
                        className="w-14 h-14 rounded-2xl object-cover border-2 border-indigo-500 shadow-md"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <div className="w-14 h-14 rounded-2xl bg-indigo-600 text-white font-bold flex items-center justify-center text-lg shadow-md">
                        {userName.substring(0, 2).toUpperCase()}
                      </div>
                    )}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-white">{userName}</span>
                        <span className="text-xs px-2 py-0.5 rounded-md bg-indigo-600/30 text-indigo-300 font-mono font-semibold border border-indigo-500/40">
                          {role.toUpperCase()}
                        </span>
                        <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-mono">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                          ONLINE
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-0.5">{userEmail}</p>
                      <p className="text-[11px] text-slate-400 mt-1 max-w-xl line-clamp-2">
                        {bio || 'No personal biography specified.'}
                      </p>
                    </div>
                  </div>

                  <div className="text-right shrink-0 font-mono text-[11px] text-slate-400 space-y-1">
                    <div>Timezone: <span className="text-slate-200">{timezone.split(' ')[0]}</span></div>
                    <div>Department: <span className="text-slate-200">{department || 'Unassigned'}</span></div>
                    <div>Locale: <span className="text-slate-200">{locale}</span></div>
                  </div>
                </div>
              </div>
            </div>

            {/* Observed Permissions Matrix */}
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                    <Shield className="w-4 h-4 text-emerald-400" />
                    Observed Role Capabilities ({currentRoleInfo.label})
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    {currentRoleInfo.desc}
                  </p>
                </div>
                <span className="text-[11px] font-mono text-emerald-500 font-semibold">
                  RBAC ENFORCED
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {currentRoleInfo.permissions.map((perm, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center gap-2 text-xs"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                    <span className="font-medium text-slate-800 dark:text-slate-200">{perm}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* JWT Token & Cryptographic Session Inspector */}
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Key className="w-4 h-4 text-indigo-400" />
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                    Cryptographic Session Token (HS256)
                  </h4>
                </div>
                <button
                  type="button"
                  onClick={() => setShowTokenSecret(!showTokenSecret)}
                  className="text-xs text-indigo-600 dark:text-indigo-400 hover:underline font-medium"
                >
                  {showTokenSecret ? 'Hide Token Payload' : 'Reveal Token Payload'}
                </button>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 overflow-x-auto space-y-1">
                <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider">
                  Bearer Authorization Header
                </div>
                <div className="break-all text-indigo-300">
                  {showTokenSecret
                    ? auth.token
                    : `${auth.token.substring(0, 24)}••••••••••••••••••••••••••••••••`}
                </div>
                <div className="pt-2 text-[11px] text-slate-400 grid grid-cols-2 sm:grid-cols-4 gap-2 border-t border-slate-800/80">
                  <div>alg: <span className="text-slate-200">HS256</span></div>
                  <div>typ: <span className="text-slate-200">JWT</span></div>
                  <div>sub: <span className="text-slate-200">{auth.user_id.substring(0, 8)}...</span></div>
                  <div>tenant: <span className="text-slate-200">{auth.tenant_id}</span></div>
                </div>
              </div>
            </div>

            {/* Observed User Activity Trail */}
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-teal-400" />
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white">
                    Observed Session Audit Events
                  </h4>
                </div>
                <span className="text-[11px] font-mono text-slate-400">
                  Host: 192.168.1.108 (TLS 1.3)
                </span>
              </div>

              <div className="space-y-1.5 max-h-40 overflow-y-auto font-mono text-xs">
                {auditLogs.slice(0, 4).map((log) => (
                  <div
                    key={log.id}
                    className="p-2 rounded-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-[10px] text-slate-500">{new Date(log.timestamp).toLocaleTimeString()}</span>
                      <span className="text-indigo-400 font-semibold">{log.action}</span>
                      <span className="text-slate-500 truncate">{log.resource_type}</span>
                    </div>
                    <span className="text-[10px] font-bold text-emerald-500 shrink-0">{log.status}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: REMOVE & DANGER ZONE */}
        {activeTab === 'remove' && (
          <div className="p-6 space-y-6 max-h-[68vh] overflow-y-auto">
            <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-300 text-xs flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <h4 className="font-bold text-amber-200">Granular Profile Deletion &amp; Reset Operations</h4>
                <p className="mt-0.5 text-amber-300/90 leading-relaxed">
                  You can remove individual profile assets (such as your uploaded photo or bio description), clear cached session tokens, or perform a complete restoration to standard factory profile settings.
                </p>
              </div>
            </div>

            {/* Removal Actions Grid */}
            <div className="space-y-4">
              {/* Option 1: Remove Avatar Photo */}
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white dark:bg-slate-900">
                <div>
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <User className="w-4 h-4 text-rose-400" />
                    Remove Profile Picture
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Deletes any custom uploaded avatar or preset and reverts your appearance to initials.
                  </p>
                </div>
                <button
                  id="btn-remove-avatar-action"
                  type="button"
                  onClick={handleRemoveAvatar}
                  disabled={!avatarUrl}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${
                    avatarUrl
                      ? 'border-rose-300 dark:border-rose-900/60 text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 cursor-pointer'
                      : 'opacity-50 cursor-not-allowed border-slate-200 dark:border-slate-800 text-slate-400'
                  }`}
                >
                  {avatarUrl ? 'Remove Picture' : 'No Picture Assigned'}
                </button>
              </div>

              {/* Option 2: Remove Metadata Fields */}
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white dark:bg-slate-900">
                <div>
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <FileText className="w-4 h-4 text-amber-400" />
                    Remove Bio &amp; Department Meta
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Clears your technical statement, department affiliation, and phone number fields.
                  </p>
                </div>
                <button
                  id="btn-clear-metadata-action"
                  type="button"
                  onClick={() => {
                    setBio('');
                    setDepartment('');
                    setPhone('');
                    onUpdateProfile({ bio: '', department: '', phone: '' });
                    showFeedback('Bio, department, and phone details removed.');
                  }}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors"
                >
                  Clear Meta Fields
                </button>
              </div>

              {/* Option 3: Terminate Session Token */}
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white dark:bg-slate-900">
                <div>
                  <h4 className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <LogOut className="w-4 h-4 text-purple-400" />
                    Invalidate Active Session Token
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Revokes active JWT bearer token signature and generates a fresh cryptographic session.
                  </p>
                </div>
                <button
                  id="btn-refresh-token-action"
                  type="button"
                  onClick={() => {
                    const newToken = `jwt-hs256-refreshed-${Date.now().toString(36)}`;
                    onUpdateProfile({ token: newToken });
                    showFeedback('Session token invalidated. Fresh cryptographic token provisioned.');
                  }}
                  className="px-3 py-1.5 rounded-lg text-xs font-semibold border border-purple-300 dark:border-purple-900/60 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-950/40 transition-colors"
                >
                  Refresh Token
                </button>
              </div>

              {/* Option 4: Full Factory Reset */}
              <div className="p-4 rounded-xl border border-rose-500/40 bg-rose-500/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h4 className="text-xs font-bold text-rose-600 dark:text-rose-400 flex items-center gap-2">
                    <RotateCcw className="w-4 h-4 text-rose-500" />
                    Reset All Profile Settings to Factory Defaults
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    Restores Dr. Elena Vance administrator profile, executive avatar, and default tenant credentials.
                  </p>
                </div>
                <button
                  id="btn-open-factory-reset"
                  type="button"
                  onClick={() => setConfirmResetOpen(true)}
                  className="px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-xs transition-colors cursor-pointer shrink-0"
                >
                  Reset to Defaults
                </button>
              </div>
            </div>

            {/* Confirmation Dialog for Factory Reset */}
            {confirmResetOpen && (
              <div className="p-4 rounded-xl border border-rose-600 bg-rose-950/60 text-rose-200 text-xs space-y-3">
                <div className="flex items-center gap-2 font-bold text-sm">
                  <AlertTriangle className="w-4 h-4 text-rose-400" />
                  Confirm Profile Factory Reset?
                </div>
                <p>
                  This action will overwrite your current display name, email address, role selection, and custom avatar with the system baseline defaults.
                </p>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={handleExecuteReset}
                    className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs transition-colors"
                  >
                    Yes, Reset Profile
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmResetOpen(false)}
                    className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 text-xs transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
