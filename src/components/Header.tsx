import React from 'react';
import {
  Sparkles,
  RadioTower,
  ShieldCheck,
  Database,
  Languages,
  Bell,
  Sun,
  Moon,
  CheckCircle2,
  Lock
} from 'lucide-react';
import { AuthContext, NotificationItem } from '../types';

interface HeaderProps {
  auth: AuthContext;
  notifications: NotificationItem[];
  onOpenNotifications: () => void;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  auth,
  notifications,
  onOpenNotifications,
  theme,
  onToggleTheme
}) => {
  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <header id="app-header" className={`border-b transition-colors sticky top-0 z-50 ${theme === 'dark' ? 'border-neutral-800 bg-neutral-900/80 backdrop-blur-md' : 'border-[#E2E8F0] bg-[#FFFFFF]/90 backdrop-blur-md'}`}>
      <div className="w-full max-w-[1720px] mx-auto px-4 sm:px-6 lg:px-10 py-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        {/* Left Branding */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#2563EB] via-indigo-600 to-[#0D9488] flex items-center justify-center shadow-lg shadow-blue-500/20 ring-1 ring-white/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className={`text-lg font-bold tracking-tight ${theme === 'dark' ? 'text-white' : 'text-[#0F172A]'}`}>ABCI-MI</h1>
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded-full bg-blue-950 text-blue-300 border border-blue-800/80 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
                Framework v1.0
              </span>
              <span className="hidden sm:inline-flex px-2 py-0.5 text-[10px] font-bold uppercase rounded-full bg-emerald-950 text-[#059669] border border-emerald-800/80">
                Live Engine
              </span>
            </div>
            <p className={`text-[11px] font-medium ${theme === 'dark' ? 'text-neutral-400' : 'text-[#475569]'}`}>
              Adaptive Collaborative Intelligence for Multilingual Meeting Intelligence
            </p>
          </div>
        </div>

        {/* Right Status & User Bar */}
        <div className="flex items-center space-x-3">
          {/* Quick Metrics */}
          <div className="hidden lg:flex items-center gap-2 text-xs">
            <div className={`flex items-center space-x-1 px-2.5 py-1 rounded-md border ${theme === 'dark' ? 'bg-neutral-950 border-neutral-800 text-neutral-300' : 'bg-[#F7F9FC] border-[#E2E8F0] text-[#0F172A]'}`}>
              <RadioTower className="w-3 h-3 text-[#059669]" />
              <span>47 Endpoints</span>
            </div>
            <div className={`flex items-center space-x-1 px-2.5 py-1 rounded-md border ${theme === 'dark' ? 'bg-neutral-950 border-neutral-800 text-neutral-300' : 'bg-[#F7F9FC] border-[#E2E8F0] text-[#0F172A]'}`}>
              <ShieldCheck className="w-3 h-3 text-[#2563EB]" />
              <span>HS256 Scoped</span>
            </div>
            <div className={`flex items-center space-x-1 px-2.5 py-1 rounded-md border ${theme === 'dark' ? 'bg-neutral-950 border-neutral-800 text-neutral-300' : 'bg-[#F7F9FC] border-[#E2E8F0] text-[#0F172A]'}`}>
              <Languages className="w-3 h-3 text-[#D97706]" />
              <span>17 Locales</span>
            </div>
          </div>

          {/* Theme Toggle Button */}
          <button
            onClick={onToggleTheme}
            className={`p-2 rounded-lg border transition-colors flex items-center gap-1.5 text-xs font-medium ${theme === 'dark' ? 'bg-neutral-950 hover:bg-neutral-800 text-amber-400 border-neutral-800' : 'bg-[#F7F9FC] hover:bg-slate-100 text-[#2563EB] border-[#E2E8F0]'}`}
            title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
          >
            {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-[#2563EB]" />}
            <span className="hidden sm:inline">{theme === 'dark' ? 'Light' : 'Dark'}</span>
          </button>

          {/* Notifications Trigger */}
          <button
            id="btn-open-notifications"
            onClick={onOpenNotifications}
            className={`relative p-2 rounded-lg border transition-colors ${theme === 'dark' ? 'bg-neutral-950 hover:bg-neutral-800 text-neutral-400 hover:text-white border-neutral-800' : 'bg-[#F7F9FC] hover:bg-slate-100 text-[#475569] hover:text-[#0F172A] border-[#E2E8F0]'}`}
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-[#2563EB] text-white rounded-full text-[9px] font-bold flex items-center justify-center animate-pulse">
                {unreadCount}
              </span>
            )}
          </button>

          {/* User / Tenant Badge */}
          <div className={`flex items-center space-x-2 pl-2 border-l text-xs ${theme === 'dark' ? 'border-neutral-800' : 'border-[#E2E8F0]'}`}>
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold uppercase border ${theme === 'dark' ? 'bg-neutral-800 text-neutral-200 border-neutral-700' : 'bg-slate-200 text-[#0F172A] border-slate-300'}`}>
              {auth.role[0]}
            </div>
            <div className="hidden sm:block text-left">
              <div className={`text-[11px] font-semibold truncate max-w-[120px] ${theme === 'dark' ? 'text-white' : 'text-[#0F172A]'}`}>{auth.user_name}</div>
              <div className={`text-[10px] capitalize ${theme === 'dark' ? 'text-neutral-400' : 'text-[#475569]'}`}>{auth.role.replace('_', ' ')}</div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

