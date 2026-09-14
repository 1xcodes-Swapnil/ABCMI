import React from 'react';
import {
  Sparkles,
  Radio,
  ShieldCheck,
  Languages,
  Bell,
  Sun,
  Moon,
  Search,
  Command,
  Cpu,
  Layers,
  Activity,
  CheckCircle2
} from 'lucide-react';
import { AuthContext, NotificationItem } from '../types';

interface HeaderProps {
  auth: AuthContext;
  notifications: NotificationItem[];
  onOpenNotifications: () => void;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  onOpenCommandPalette?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  auth,
  notifications,
  onOpenNotifications,
  theme,
  onToggleTheme,
  onOpenCommandPalette
}) => {
  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <header
      id="app-header"
      className={`border-b transition-colors sticky top-0 z-40 ${
        theme === 'dark'
          ? 'border-slate-800/80 bg-slate-950/85 backdrop-blur-xl text-slate-100'
          : 'border-slate-200/90 bg-white/90 backdrop-blur-xl text-slate-900 shadow-xs'
      }`}
    >
      <div className="w-full max-w-[1760px] mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between gap-4">
        {/* Left Branding & Framework Identity */}
        <div className="flex items-center gap-3.5">
          <div className="relative group">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-blue-600 to-teal-500 flex items-center justify-center shadow-md shadow-indigo-500/25 ring-1 ring-white/20 transition-transform group-hover:scale-105">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <span className="absolute -bottom-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500 ring-2 ring-slate-950" />
            </span>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-extrabold tracking-tight bg-gradient-to-r from-indigo-400 via-blue-500 to-teal-400 bg-clip-text text-transparent">
                ABCI-MI
              </span>
              <span
                className={`px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase rounded-full border ${
                  theme === 'dark'
                    ? 'bg-indigo-950/70 text-indigo-300 border-indigo-800/60'
                    : 'bg-indigo-50 text-indigo-700 border-indigo-200'
                }`}
              >
                v1.0 Pro
              </span>
              <span
                className={`hidden md:inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold uppercase rounded-full border ${
                  theme === 'dark'
                    ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/60'
                    : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                MOSS Primary
              </span>
            </div>
            <p
              className={`text-[11px] font-medium hidden sm:block ${
                theme === 'dark' ? 'text-slate-400' : 'text-slate-500'
              }`}
            >
              Adaptive Blackboard Collaborative Intelligence for Multilingual Meeting Analytics
            </p>
          </div>
        </div>

        {/* Center Quick Search / Command Palette Bar */}
        <div className="hidden xl:flex items-center flex-1 max-w-md mx-6">
          <button
            onClick={onOpenCommandPalette}
            className={`w-full flex items-center justify-between px-3.5 py-2 rounded-xl text-xs border transition-all ${
              theme === 'dark'
                ? 'bg-slate-900/90 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200 hover:bg-slate-900'
                : 'bg-slate-50 border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-900 hover:bg-white'
            }`}
          >
            <div className="flex items-center gap-2">
              <Search className="w-3.5 h-3.5" />
              <span>Search meetings, knowledge objects, decisions...</span>
            </div>
            <kbd
              className={`flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-mono font-semibold rounded border ${
                theme === 'dark'
                  ? 'bg-slate-800 border-slate-700 text-slate-300'
                  : 'bg-slate-200 border-slate-300 text-slate-700'
              }`}
            >
              <Command className="w-2.5 h-2.5" /> K
            </kbd>
          </button>
        </div>

        {/* Right Status Indicators & User Bar */}
        <div className="flex items-center gap-2.5">
          {/* Engine Status Chips */}
          <div className="hidden lg:flex items-center gap-2">
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono font-medium ${
                theme === 'dark'
                  ? 'bg-slate-900 border-slate-800 text-slate-300'
                  : 'bg-slate-100 border-slate-200 text-slate-700'
              }`}
              title="Blackboard ACE Event Orchestrator Active"
            >
              <Activity className="w-3 h-3 text-emerald-400" />
              <span>ACE Active</span>
            </div>

            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-mono font-medium ${
                theme === 'dark'
                  ? 'bg-slate-900 border-slate-800 text-slate-300'
                  : 'bg-slate-100 border-slate-200 text-slate-700'
              }`}
              title="17 Supported Indic & Global Languages"
            >
              <Languages className="w-3 h-3 text-indigo-400" />
              <span>17 Locales</span>
            </div>
          </div>

          {/* Theme Toggle Button */}
          <button
            onClick={onToggleTheme}
            className={`p-2 rounded-xl border transition-colors flex items-center justify-center ${
              theme === 'dark'
                ? 'bg-slate-900 hover:bg-slate-800 text-amber-400 border-slate-800 hover:border-slate-700'
                : 'bg-slate-100 hover:bg-slate-200 text-indigo-600 border-slate-200 hover:border-slate-300'
            }`}
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
            aria-label="Toggle Theme"
          >
            {theme === 'dark' ? (
              <Sun className="w-4 h-4 text-amber-400 transition-transform hover:rotate-45" />
            ) : (
              <Moon className="w-4 h-4 text-indigo-600 transition-transform hover:-rotate-12" />
            )}
          </button>

          {/* Notifications Trigger */}
          <button
            id="btn-open-notifications"
            onClick={onOpenNotifications}
            className={`relative p-2 rounded-xl border transition-colors ${
              theme === 'dark'
                ? 'bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border-slate-800 hover:border-slate-700'
                : 'bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-900 border-slate-200 hover:border-slate-300'
            }`}
            aria-label="Notifications"
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-indigo-600 text-white rounded-full text-[9px] font-bold flex items-center justify-center ring-2 ring-slate-950 animate-pulse">
                {unreadCount}
              </span>
            )}
          </button>

          {/* User / Tenant Badge */}
          <div
            className={`flex items-center gap-2 pl-2.5 border-l ${
              theme === 'dark' ? 'border-slate-800' : 'border-slate-200'
            }`}
          >
            <div
              className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-bold uppercase tracking-wider border shadow-xs ${
                theme === 'dark'
                  ? 'bg-gradient-to-br from-indigo-900 to-slate-900 text-indigo-200 border-indigo-700/50'
                  : 'bg-gradient-to-br from-indigo-100 to-blue-50 text-indigo-700 border-indigo-200'
              }`}
            >
              {auth.user_name.charAt(0)}
            </div>
            <div className="hidden sm:block text-left leading-tight">
              <div
                className={`text-xs font-semibold truncate max-w-[120px] ${
                  theme === 'dark' ? 'text-slate-200' : 'text-slate-800'
                }`}
              >
                {auth.user_name}
              </div>
              <div
                className={`text-[10px] font-mono capitalize ${
                  theme === 'dark' ? 'text-slate-400' : 'text-slate-500'
                }`}
              >
                {auth.role}
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

