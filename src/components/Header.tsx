import React, { useState, useRef, useEffect } from 'react';
import {
  Bell,
  Sun,
  Moon,
  Search,
  Command,
  CheckCircle2,
  SlidersHorizontal,
  ChevronDown,
  User,
  Shield,
  Key,
  LogOut,
  Sparkles,
  Activity,
  FileText,
  RotateCcw,
  Check,
  Radio,
  ExternalLink,
  Layers,
  Settings
} from 'lucide-react';
import { AuthContext, NotificationItem } from '../types';

interface HeaderProps {
  auth: AuthContext;
  notifications: NotificationItem[];
  onOpenNotifications: () => void;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  onOpenCommandPalette?: () => void;
  onOpenProfileSettings?: () => void;
  onSwitchRole?: (role: AuthContext['role']) => void;
  onNavigateTab?: (tabKey: any) => void;
  onRefreshSessionToken?: () => void;
  activeTabTitle?: string;
}

export const Header: React.FC<HeaderProps> = ({
  auth,
  notifications,
  onOpenNotifications,
  theme,
  onToggleTheme,
  onOpenCommandPalette,
  onOpenProfileSettings,
  onSwitchRole,
  onNavigateTab,
  onRefreshSessionToken,
  activeTabTitle = 'Meetings & Audio Intake'
}) => {
  const unreadCount = notifications.filter(n => !n.read).length;
  const avatarSrc = auth.avatar_url || '/src/assets/images/workspace_executive_avatar_1790188244518.jpg';

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [userStatus, setUserStatus] = useState<'online' | 'busy' | 'away'>('online');
  const [copiedToken, setCopiedToken] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsDropdownOpen(false);
      }
    };

    if (isDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isDropdownOpen]);

  const handleRoleChange = (role: AuthContext['role']) => {
    if (onSwitchRole) {
      onSwitchRole(role);
    }
  };

  const handleCopySessionToken = () => {
    navigator.clipboard?.writeText(auth.token || 'jwt-bearer-token');
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  return (
    <header
      id="app-header"
      className={`border-b transition-colors sticky top-0 z-40 ${
        theme === 'dark'
          ? 'border-slate-800/90 bg-slate-950/95 backdrop-blur-md text-slate-100'
          : 'border-slate-200/90 bg-white/95 backdrop-blur-md text-slate-900'
      }`}
    >
      <div className="w-full max-w-[1760px] mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-4">
        {/* Zone 1: Platform Branding & Breadcrumb (Left-side profile button cleanly removed) */}
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex items-center gap-2.5 shrink-0">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-600 via-indigo-500 to-purple-600 text-white flex items-center justify-center font-bold text-xs shadow-xs tracking-tight">
              <Sparkles className="w-4 h-4 text-white" />
            </div>
            <div className="flex flex-col text-left leading-tight">
              <span className="text-xs font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-1.5">
                ABCI-MI
                <span className="px-1.5 py-0.2 rounded text-[10px] font-mono font-medium bg-indigo-500/10 text-indigo-500 dark:text-indigo-400 border border-indigo-500/20">
                  v1.0
                </span>
              </span>
              <span className="text-[10px] text-slate-500 dark:text-slate-400">
                Acoustic &amp; Meeting Intelligence
              </span>
            </div>
          </div>

          <span className="hidden sm:inline-block text-slate-300 dark:text-slate-700" aria-hidden="true">
            /
          </span>

          <div className="hidden sm:flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400 truncate">
            <span className="font-semibold text-slate-900 dark:text-white">Workspace</span>
            <span aria-hidden="true">·</span>
            <span className="truncate">{activeTabTitle}</span>
          </div>
        </div>

        {/* Zone 2: Search / Command Palette Bar */}
        <div className="hidden md:flex items-center flex-1 max-w-md mx-4">
          <button
            onClick={onOpenCommandPalette}
            className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-xs border transition-colors ${
              theme === 'dark'
                ? 'bg-slate-900/80 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                : 'bg-slate-50 border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-900'
            }`}
          >
            <div className="flex items-center gap-2">
              <Search className="w-3.5 h-3.5" />
              <span>Search meetings, decisions, knowledge...</span>
            </div>
            <kbd
              className={`flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-mono font-medium rounded border ${
                theme === 'dark'
                  ? 'bg-slate-800 border-slate-700 text-slate-300'
                  : 'bg-slate-200 border-slate-300 text-slate-700'
              }`}
            >
              <Command className="w-2.5 h-2.5" /> K
            </kbd>
          </button>
        </div>

        {/* Zone 3: Actions & Top-Right User Profile with Rich Dropdown */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Unboxed Live Status */}
          <div className="hidden lg:flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400 pr-2 border-r border-slate-200 dark:border-slate-800">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block animate-pulse" />
            <span className="font-medium text-[11px] tracking-wide">All Systems Nominal</span>
          </div>

          {/* Theme Toggle */}
          <button
            onClick={onToggleTheme}
            className={`p-2 rounded-lg border transition-colors ${
              theme === 'dark'
                ? 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800'
                : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
            }`}
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
            aria-label="Toggle Theme"
          >
            {theme === 'dark' ? (
              <Sun className="w-4 h-4 text-amber-400" />
            ) : (
              <Moon className="w-4 h-4 text-slate-700" />
            )}
          </button>

          {/* Notifications Trigger */}
          <button
            id="btn-open-notifications"
            onClick={onOpenNotifications}
            className={`relative p-2 rounded-lg border transition-colors ${
              theme === 'dark'
                ? 'bg-slate-900 hover:bg-slate-800 text-slate-300 border-slate-800'
                : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
            }`}
            aria-label="Notifications"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-indigo-500 rounded-full ring-2 ring-white dark:ring-slate-950" />
            )}
          </button>

          {/* Sole Top-Right User Profile Trigger with Interactive Dropdown */}
          <div className="relative" ref={dropdownRef}>
            <button
              id="btn-user-profile-top-right"
              type="button"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className={`flex items-center gap-2 pl-1 sm:pl-2 p-1 rounded-lg border transition-all text-left cursor-pointer group ${
                isDropdownOpen
                  ? theme === 'dark'
                    ? 'bg-slate-900 border-indigo-500/60 ring-1 ring-indigo-500/40'
                    : 'bg-slate-100 border-indigo-400 ring-1 ring-indigo-300'
                  : 'hover:bg-slate-100 dark:hover:bg-slate-900 border-transparent hover:border-slate-200 dark:hover:border-slate-800'
              }`}
              title="Account Profile & Settings Menu"
              aria-label="User Profile & Settings Menu"
              aria-expanded={isDropdownOpen}
              aria-haspopup="true"
            >
              <div className="relative">
                {auth.avatar_url ? (
                  <img
                    src={avatarSrc}
                    alt={auth.user_name}
                    className="w-7 h-7 rounded-full object-cover border border-slate-200 dark:border-slate-700 group-hover:border-indigo-500 transition-colors"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div className="w-7 h-7 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-xs shadow-xs">
                    {auth.user_name ? auth.user_name.substring(0, 2).toUpperCase() : 'SJ'}
                  </div>
                )}
                <span
                  className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 ${
                    theme === 'dark' ? 'border-slate-950' : 'border-white'
                  } ${
                    userStatus === 'online'
                      ? 'bg-emerald-500'
                      : userStatus === 'busy'
                      ? 'bg-rose-500'
                      : 'bg-amber-500'
                  }`}
                />
              </div>

              <div className="hidden sm:block text-left leading-tight">
                <div className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate max-w-[120px] flex items-center gap-1 group-hover:text-indigo-400 transition-colors">
                  {auth.user_name}
                  <ChevronDown
                    className={`w-3 h-3 text-slate-400 transition-transform duration-200 ${
                      isDropdownOpen ? 'rotate-180 text-indigo-400' : ''
                    }`}
                  />
                </div>
                <div className="text-[10px] text-slate-500 dark:text-slate-400 font-mono capitalize">
                  {auth.role}
                </div>
              </div>
            </button>

            {/* Profile Dropdown Menu */}
            {isDropdownOpen && (
              <div
                id="user-profile-dropdown-menu"
                className={`absolute right-0 mt-2 w-80 rounded-2xl border shadow-2xl overflow-hidden z-50 animate-in fade-in slide-in-from-top-2 duration-150 ${
                  theme === 'dark'
                    ? 'bg-slate-900 border-slate-800 text-slate-100 divide-y divide-slate-800'
                    : 'bg-white border-slate-200 text-slate-900 divide-y divide-slate-100'
                }`}
              >
                {/* User Identity Header */}
                <div className="p-4 bg-slate-50/50 dark:bg-slate-950/50">
                  <div className="flex items-center gap-3">
                    {auth.avatar_url ? (
                      <img
                        src={avatarSrc}
                        alt={auth.user_name}
                        className="w-11 h-11 rounded-xl object-cover border-2 border-indigo-500/40 shadow-xs"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <div className="w-11 h-11 rounded-xl bg-indigo-600 text-white font-bold flex items-center justify-center text-sm shadow-xs">
                        {auth.user_name ? auth.user_name.substring(0, 2).toUpperCase() : 'SJ'}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-slate-900 dark:text-white truncate">
                          {auth.user_name}
                        </span>
                        <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 font-semibold border border-indigo-500/20">
                          {auth.role}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
                        {auth.user_email}
                      </p>
                    </div>
                  </div>

                  {/* Presence Status Selector */}
                  <div className="mt-3 pt-3 border-t border-slate-200/80 dark:border-slate-800/80 flex items-center justify-between text-xs">
                    <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                      Current Status:
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setUserStatus('online')}
                        className={`px-2 py-0.5 rounded-md text-[11px] font-medium flex items-center gap-1 transition-all ${
                          userStatus === 'online'
                            ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-semibold ring-1 ring-emerald-500/30'
                            : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-300'
                        }`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        Online
                      </button>
                      <button
                        type="button"
                        onClick={() => setUserStatus('busy')}
                        className={`px-2 py-0.5 rounded-md text-[11px] font-medium flex items-center gap-1 transition-all ${
                          userStatus === 'busy'
                            ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400 font-semibold ring-1 ring-rose-500/30'
                            : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-300'
                        }`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                        In Meeting
                      </button>
                      <button
                        type="button"
                        onClick={() => setUserStatus('away')}
                        className={`px-2 py-0.5 rounded-md text-[11px] font-medium flex items-center gap-1 transition-all ${
                          userStatus === 'away'
                            ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 font-semibold ring-1 ring-amber-500/30'
                            : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-300'
                        }`}
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                        Away
                      </button>
                    </div>
                  </div>
                </div>

                {/* RBAC Quick Role Switcher */}
                <div className="p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1">
                      <Shield className="w-3 h-3 text-indigo-400" />
                      Switch RBAC Role
                    </span>
                    <span className="text-[10px] font-mono text-indigo-400">Live Context</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {(['admin', 'host', 'security_officer', 'member'] as const).map(r => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => handleRoleChange(r)}
                        className={`px-2.5 py-1.5 rounded-lg text-xs text-left font-medium transition-all flex items-center justify-between border ${
                          auth.role === r
                            ? 'bg-indigo-50 dark:bg-indigo-950/60 border-indigo-500/60 text-indigo-700 dark:text-indigo-300 ring-1 ring-indigo-500/30'
                            : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800/60'
                        }`}
                      >
                        <span className="capitalize">{r.replace('_', ' ')}</span>
                        {auth.role === r && <Check className="w-3 h-3 text-indigo-500" />}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Core Quick Navigation Actions */}
                <div className="p-2 space-y-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      setIsDropdownOpen(false);
                      if (onOpenProfileSettings) onOpenProfileSettings();
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors group cursor-pointer"
                  >
                    <Settings className="w-4 h-4 text-indigo-400 group-hover:rotate-45 transition-transform" />
                    <div>
                      <div className="font-semibold text-slate-900 dark:text-white">
                        Edit Profile &amp; Settings
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        Update avatar, bio, department &amp; preferences
                      </div>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setIsDropdownOpen(false);
                      if (onNavigateTab) onNavigateTab('security');
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors group"
                  >
                    <Shield className="w-4 h-4 text-emerald-400" />
                    <div>
                      <div className="font-semibold text-slate-900 dark:text-white">
                        Security &amp; Audit Trail
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        View cryptographic logs &amp; RBAC policies
                      </div>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setIsDropdownOpen(false);
                      if (onNavigateTab) onNavigateTab('system_health');
                    }}
                    className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-left hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors group"
                  >
                    <Activity className="w-4 h-4 text-amber-400" />
                    <div>
                      <div className="font-semibold text-slate-900 dark:text-white">
                        System Health &amp; Diagnostics
                      </div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400">
                        Monitor latency, memory, and engine status
                      </div>
                    </div>
                  </button>
                </div>

                {/* Session & Utility Actions */}
                <div className="p-2 space-y-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      if (onRefreshSessionToken) onRefreshSessionToken();
                      handleCopySessionToken();
                    }}
                    className="w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <Key className="w-3.5 h-3.5 text-indigo-400" />
                      <span>{copiedToken ? 'Token Copied & Refreshed!' : 'Refresh Session Token'}</span>
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">HS256</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setIsDropdownOpen(false);
                      onToggleTheme();
                    }}
                    className="w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      {theme === 'dark' ? <Sun className="w-3.5 h-3.5 text-amber-400" /> : <Moon className="w-3.5 h-3.5 text-slate-700" />}
                      <span>Appearance: {theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</span>
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">Toggle</span>
                  </button>
                </div>

                {/* Sign Out / Footer */}
                <div className="p-2.5 bg-slate-50/70 dark:bg-slate-950/70 flex items-center justify-between text-xs">
                  <div className="text-[10px] font-mono text-slate-500 dark:text-slate-400">
                    Tenant: <span className="font-semibold text-slate-700 dark:text-slate-300">{auth.tenant_id}</span>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setIsDropdownOpen(false);
                      if (onOpenProfileSettings) onOpenProfileSettings();
                    }}
                    className="flex items-center gap-1 text-xs font-semibold text-rose-500 hover:text-rose-400 transition-colors"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Manage Account</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
