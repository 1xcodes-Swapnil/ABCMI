import React, { useState, useEffect, useRef } from 'react';
import {
  Users,
  Radio,
  Sparkles,
  Search,
  Database,
  Languages,
  FileText,
  ShieldCheck,
  Terminal,
  Layers,
  CheckCircle2,
  X,
  Bell,
  Award,
  ChevronLeft,
  ChevronRight,
  Menu,
  Activity,
  Cpu,
  Workflow,
  PanelLeftClose,
  PanelLeftOpen,
  Command
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import {
  MeetingItem,
  MeetingIntelligence,
  KnowledgeObject,
  GroundedQuery,
  TranslationItem,
  AuditLogItem,
  NotificationItem,
  AuthContext
} from './types';
import {api, write, rows, credentials} from './api';
import {WorkspacePanels, WorkspaceStatus, Connection, Profile, ErrorBox} from './components/WorkspacePanels';
import { Header } from './components/Header';
import { CommandPalette } from './components/CommandPalette';

export default function App() {
  // State Management
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [activeTab, updateActiveTab] = useState<
    'projects' | 'meetings' | 'live_stream' | 'intelligence' | 'queries' | 'knowledge' | 'translations' | 'reports' | 'benchmarks' | 'security' | 'api_console' | 'system_health'
  >('meetings');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  const liveBusy = useRef(false);
  const sessionEpoch = useRef(0);
  function setActiveTab(next:any) {
    if (liveBusy.current) {setError('Stop capture and finish pending uploads before leaving the live tab.'); return;}
    updateActiveTab(next);
  }
  function selectMeeting(id:string) {
    if (liveBusy.current) {setError('Finish live capture and pending uploads before changing meetings.'); return;}
    setSelectedMeetingId(id);
  }
  useEffect(() => {
    const handler = (event:Event) => {liveBusy.current = (event as CustomEvent).detail;};
    window.addEventListener('abci:live-pending', handler);
    return () => window.removeEventListener('abci:live-pending', handler);
  }, []);
  const emptyAuth: AuthContext = {token: '', user_id: '', user_name: 'Not connected', user_email: '', role: 'member', tenant_id: ''};
  const [auth, setAuth] = useState<AuthContext>(emptyAuth);
  const [records, setRecords] = useState<any[]>([]);
  const meetingPages = useRef(1), meetingRequest = useRef(0);
  const [hasMoreMeetings, setHasMoreMeetings] = useState(false);
  const [selectedMeetingId, setSelectedMeetingId] = useState('');
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [showNotificationsModal, setShowNotificationsModal] = useState(false);
  const [isProfileSettingsOpen, setIsProfileSettingsOpen] = useState(false);
  const [error, setError] = useState('');
  const meetings: MeetingItem[] = records.map(m => ({...m, primary_language:m.language,
    audio_uploaded:!!m.audio_recordings?.length, participants:(m.participants || []).map((p:any) => p.display_name)}));
  async function refresh() {
    const epoch = sessionEpoch.current;
    const request = ++meetingRequest.current, collected:any[] = [];
    let more = false;
    for (let page=0; page<meetingPages.current; page++) {
      const batch = await api(`/meetings?limit=200&skip=${page*200}`);
      if (epoch !== sessionEpoch.current || request !== meetingRequest.current) return;
      collected.push(...batch); more = batch.length === 200;
      if (!more) break;
    }
    const list = Array.from(new Map(collected.map(m => [m.id, m])).values());
    setHasMoreMeetings(more);
    setRecords(list);
    setSelectedMeetingId(current => list.some((m:any) => m.id === current) ? current : list[0]?.id || '');
  }
  async function loadMoreMeetings() {meetingPages.current++; await refresh();}
  async function refreshNotifications() {
    const epoch = sessionEpoch.current;
    const result = await api('/notifications');
    if (epoch !== sessionEpoch.current) return;
    setNotifications(rows(result).map(n => ({...n, read:n.is_read ?? n.read, message:n.description ?? n.message})));
  }
  async function connect(token:string, tenant:string) {
    credentials(token, tenant);
    try {
      const me = await api('/auth/me');
      credentials(token, me.tenant_id);
      sessionEpoch.current++;
      meetingPages.current = 1;
      setAuth({token, user_id:me.user_id, user_name:me.full_name, user_email:me.email, role:me.role, tenant_id:me.tenant_id});
      setError('');
    } catch (e) {credentials('', ''); throw e;}
  }
  function signOut() {if (liveBusy.current) {setError('Finish live capture before signing out.'); return;} sessionEpoch.current++; credentials('', ''); setAuth(emptyAuth); setRecords([]); setNotifications([]); setSelectedMeetingId(''); setIsProfileSettingsOpen(false);}
  useEffect(() => {
    if (!auth.token) return;
    let active = true;
    const load = async () => {try {await refresh(); await refreshNotifications(); if (active) setError('');} catch(e) {if (active) setError((e as Error).message);}};
    void load(); const timer = setInterval(load, 15000);
    return () => {active = false; clearInterval(timer);};
  }, [auth.token]);
  useEffect(() => {
    const key = (e:KeyboardEvent) => {if ((e.ctrlKey || e.metaKey) && e.key === 'k') {e.preventDefault(); setIsCommandPaletteOpen(v => !v);}};
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key);
  }, []);

  interface NavItem {
    id: string;
    key: 'projects' | 'meetings' | 'live_stream' | 'intelligence' | 'queries' | 'knowledge' | 'translations' | 'reports' | 'benchmarks' | 'security' | 'api_console' | 'system_health';
    label: string;
    shortLabel: string;
    icon: any;
    color: string;
    badge: string;
    description: string;
  }

  interface NavCategory {
    title: string;
    items: NavItem[];
  }

  // Categorized Navigation
  const NAV_CATEGORIES: NavCategory[] = [
    {
      title: 'Core Meeting Pipeline',
      items: [
        {
          id: 'tab-projects', key: 'projects', label: 'Projects & Cross-Meeting', shortLabel: 'Projects', icon: Layers, color: 'text-indigo-400', badge: '', description: 'Group meetings and view persisted project intelligence'
        },
        {
          id: 'tab-meetings',
          key: 'meetings',
          label: 'Meetings & Audio Intake',
          shortLabel: 'Meetings',
          icon: Users,
          color: 'text-indigo-400',
          badge: `${meetings.length}`,
          description: 'Batch audio intake & chunking'
        },
        {
          id: 'tab-live-stream',
          key: 'live_stream',
          label: 'Real-Time Live Stream',
          shortLabel: 'Live Stream',
          icon: Radio,
          color: 'text-rose-400',
          badge: 'Live',
          description: 'Live streaming transcription'
        },
        {
          id: 'tab-intelligence',
          key: 'intelligence',
          label: 'Multi-Agent Intelligence (ACE)',
          shortLabel: 'Intelligence',
          icon: Sparkles,
          color: 'text-purple-400',
          badge: '13 Modules',
          description: 'Summary, decisions & ACE trace'
        }
      ]
    },
    {
      title: 'Knowledge & Analytics',
      items: [
        {
          id: 'tab-queries',
          key: 'queries',
          label: 'Ask ABCI-MI (Queries)',
          shortLabel: 'Queries',
          icon: Search,
          color: 'text-blue-400',
          badge: 'Grounded',
          description: 'Cross-meeting grounded Q&A'
        },
        {
          id: 'tab-knowledge',
          key: 'knowledge',
          label: 'Knowledge Warehouse (SKW)',
          shortLabel: 'Knowledge',
          icon: Database,
          color: 'text-teal-400',
          badge: 'Persisted',
          description: 'Vector embeddings & memory'
        },
        {
          id: 'tab-translations',
          key: 'translations',
          label: 'Translations',
          shortLabel: 'Translations',
          icon: Languages,
          color: 'text-amber-400',
          badge: 'Derived',
          description: 'Multilingual & Indian languages'
        }
      ]
    },
    {
      title: 'Governance & Platform',
      items: [
        {
          id: 'tab-reports',
          key: 'reports',
          label: 'Reports & Exports',
          shortLabel: 'Reports',
          icon: FileText,
          color: 'text-emerald-400',
          badge: '6 Domains',
          description: 'Multi-domain PDF & Markdown'
        },
        {
          id: 'tab-benchmarks',
          key: 'benchmarks',
          label: 'Research & Benchmarks',
          shortLabel: 'Benchmarks',
          icon: Award,
          color: 'text-amber-400',
          badge: 'Evidence',
          description: 'AMI, VoxConverse & AISHELL'
        },
        {
          id: 'tab-security',
          key: 'security',
          label: 'Security & Audit',
          shortLabel: 'Security',
          icon: ShieldCheck,
          color: 'text-emerald-400',
          badge: 'RBAC',
          description: 'Tamper-evident audit logs'
        },
        {
          id: 'tab-api-console',
          key: 'api_console',
          label: 'API Console',
          shortLabel: 'API Console',
          icon: Terminal,
          color: 'text-indigo-400',
          badge: 'OpenAPI',
          description: 'REST OpenAPI interactive tester'
        },
        {
          id: 'tab-system-health',
          key: 'system_health',
          label: 'System Health & Telemetry',
          shortLabel: 'System Health',
          icon: Activity,
          color: 'text-emerald-400',
          badge: 'Live',
          description: 'Real-time CPU, memory, latency & subsystem metrics'
        }
      ]
    }
  ];

  return (
    <div
      id="abci-mi-root"
      className={`min-h-screen font-sans antialiased selection:bg-indigo-600 selection:text-white transition-colors ${
        theme === 'dark' ? 'dark bg-slate-950 text-slate-100' : 'workspace-light bg-slate-50 text-slate-900'
      }`}
    >
      {/* Top Header & Status Metrics */}
      <Header
        auth={auth}
        notifications={notifications}
        onOpenNotifications={() => setShowNotificationsModal(true)}
        theme={theme}
        onToggleTheme={() => setTheme(t => (t === 'dark' ? 'light' : 'dark'))}
        onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
        onOpenProfileSettings={() => setIsProfileSettingsOpen(true)}
        onNavigateTab={setActiveTab}
        activeTabTitle={NAV_CATEGORIES.flatMap(c => c.items).find(i => i.key === activeTab)?.label}
      />

      {/* Command Palette Modal */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        meetings={meetings}
        onSelectMeeting={selectMeeting}
        theme={theme}
      />

      {/* Main Workspace Layout with Sidebar and Viewport */}
      <main id="app-main-content" className="w-full max-w-[1760px] mx-auto px-4 sm:px-6 lg:px-8 py-5">
        {/* Mobile Header Menu Bar */}
        <div
          className={`md:hidden flex items-center justify-between border rounded-xl p-3 mb-4 backdrop-blur-md ${
            theme === 'dark' ? 'bg-slate-900/90 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900 shadow-xs'
          }`}
        >
          <div className="flex items-center space-x-2 truncate">
            <span className={`text-xs ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>View:</span>
            <span className="text-xs font-semibold text-slate-900 dark:text-white truncate">
              {NAV_CATEGORIES.flatMap(c => c.items).find(i => i.key === activeTab)?.label}
            </span>
          </div>
          <button
            onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              theme === 'dark' ? 'bg-slate-800 text-slate-200 hover:text-white border-slate-700' : 'bg-slate-100 text-slate-800 hover:bg-slate-200 border-slate-200'
            }`}
          >
            <Menu className="w-4 h-4 text-slate-400" />
            <span>{isMobileSidebarOpen ? 'Close' : 'Navigation'}</span>
          </button>
        </div>

        {/* Mobile Sidebar Modal Drawer */}
        <AnimatePresence>
          {isMobileSidebarOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="md:hidden fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex flex-col p-4"
            >
              <div
                className={`border rounded-2xl p-5 flex-1 overflow-y-auto space-y-5 shadow-2xl ${
                  theme === 'dark' ? 'bg-slate-950 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
                }`}
              >
                <div className={`flex items-center justify-between border-b pb-3.5 ${theme === 'dark' ? 'border-slate-800' : 'border-slate-200'}`}>
                  <div className="flex items-center space-x-2.5">
                    <Workflow className="w-4 h-4 text-slate-400" />
                    <div>
                      <h3 className="text-sm font-semibold tracking-tight">ABCI-MI Workspace</h3>
                      <p className={`text-[11px] ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>Enterprise Meeting Intelligence</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setIsMobileSidebarOpen(false)}
                    className={`p-1.5 rounded-lg ${theme === 'dark' ? 'hover:bg-slate-800 text-slate-400' : 'hover:bg-slate-100 text-slate-600'}`}
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="space-y-4">
                  {NAV_CATEGORIES.map(category => (
                    <div key={category.title} className="space-y-1">
                      <div className={`text-[11px] font-semibold uppercase tracking-wider px-2 py-1 ${theme === 'dark' ? 'text-slate-500' : 'text-slate-400'}`}>
                        {category.title}
                      </div>
                      <div className="space-y-0.5">
                        {category.items.map(item => {
                          const IconComponent = item.icon;
                          const isActive = activeTab === item.key;
                          return (
                            <button
                              key={item.key}
                              id={item.id}
                              onClick={() => {
                                setActiveTab(item.key);
                                setIsMobileSidebarOpen(false);
                              }}
                              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-left transition-colors ${
                                isActive
                                  ? theme === 'dark'
                                    ? 'bg-slate-800 text-white font-medium'
                                    : 'bg-slate-100 text-slate-900 font-medium'
                                  : theme === 'dark'
                                  ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                              }`}
                            >
                              <div className="flex items-center space-x-2.5 min-w-0">
                                <IconComponent className={`w-4 h-4 shrink-0 ${isActive ? 'text-indigo-400' : 'text-slate-400'}`} />
                                <span className="text-xs truncate">{item.label}</span>
                              </div>
                              <span className="text-[11px] font-mono tabular-nums text-slate-400 ml-2">
                                {item.badge}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Layout Container: Animated Sidebar + Main Viewport */}
        <div className="flex items-start gap-6">
          {/* Animated Desktop Sidebar */}
          <motion.aside
            animate={{ width: isSidebarCollapsed ? 76 : 280 }}
            transition={{ type: 'spring', stiffness: 350, damping: 32 }}
            className={`hidden md:flex flex-col shrink-0 rounded-xl p-3 backdrop-blur-md sticky top-20 self-start max-h-[calc(100vh-6.5rem)] overflow-y-auto overflow-x-hidden border transition-colors ${
              theme === 'dark'
                ? 'bg-slate-900/60 border-slate-800/80 text-white'
                : 'bg-white border-slate-200/90 text-slate-900 shadow-xs'
            }`}
          >
            {/* Sidebar Collapse Toggle Header */}
            <div className={`flex items-center justify-between border-b pb-2.5 mb-3 px-1 ${theme === 'dark' ? 'border-slate-800/80' : 'border-slate-200'}`}>
              {!isSidebarCollapsed && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center space-x-2 overflow-hidden"
                >
                  <Workflow className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                  <span className={`text-xs font-semibold tracking-tight truncate ${theme === 'dark' ? 'text-slate-200' : 'text-slate-800'}`}>
                    Workspace Navigation
                  </span>
                </motion.div>
              )}
              <button
                onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                title={isSidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
                className={`p-1.5 rounded-md transition-colors ml-auto ${
                  theme === 'dark'
                    ? 'hover:bg-slate-800 text-slate-400 hover:text-white'
                    : 'hover:bg-slate-100 text-slate-500 hover:text-slate-900'
                }`}
              >
                {isSidebarCollapsed ? (
                  <PanelLeftOpen className="w-4 h-4 text-slate-400" />
                ) : (
                  <PanelLeftClose className="w-4 h-4 text-slate-400" />
                )}
              </button>
            </div>

            {/* Navigation Category Groups & Buttons */}
            <div className="space-y-4 flex-1">
              {NAV_CATEGORIES.map(category => (
                <div key={category.title} className="space-y-1">
                  {!isSidebarCollapsed && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 select-none ${
                        theme === 'dark' ? 'text-slate-500' : 'text-slate-400'
                      }`}
                    >
                      {category.title}
                    </motion.div>
                  )}

                  <div className="space-y-0.5">
                    {category.items.map(item => {
                      const IconComponent = item.icon;
                      const isActive = activeTab === item.key;

                      return (
                        <button
                          key={item.key}
                          id={item.id}
                          onClick={() => setActiveTab(item.key)}
                          title={isSidebarCollapsed ? `${item.label} (${item.badge})` : undefined}
                          className={`relative w-full flex items-center ${
                            isSidebarCollapsed ? 'justify-center px-0 py-2' : 'justify-between px-2.5 py-2'
                          } rounded-lg text-xs font-medium transition-colors group overflow-hidden ${
                            isActive
                              ? theme === 'dark'
                                ? 'bg-slate-800 text-white font-semibold'
                                : 'bg-slate-100 text-slate-950 font-semibold'
                              : theme === 'dark'
                              ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                          }`}
                        >
                          {/* Left Accent indicator when active */}
                          {isActive && (
                            <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 bg-indigo-500 rounded-r" />
                          )}

                          {/* Button Content */}
                          <div className="flex items-center space-x-2.5 min-w-0">
                            <IconComponent
                              className={`w-4 h-4 shrink-0 transition-colors ${
                                isActive
                                  ? 'text-indigo-500 dark:text-indigo-400'
                                  : 'text-slate-400 group-hover:text-slate-300'
                              }`}
                            />
                            {!isSidebarCollapsed && (
                              <div className="text-left truncate">
                                <span className="truncate text-xs leading-snug">{item.label}</span>
                              </div>
                            )}
                          </div>

                          {/* Status Count/Badge as Unboxed Tabular Text */}
                          {!isSidebarCollapsed && (
                            <span
                              className={`text-[11px] font-mono tabular-nums shrink-0 ml-2 ${
                                isActive
                                  ? 'text-slate-300 dark:text-slate-300 font-medium'
                                  : 'text-slate-400 dark:text-slate-500'
                              }`}
                            >
                              {item.badge}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {/* Sidebar Bottom Telemetry Footnote */}
            {!isSidebarCollapsed && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className={`mt-4 pt-3 border-t px-2 space-y-1 text-[11px] ${
                  theme === 'dark' ? 'border-slate-800/80 text-slate-400' : 'border-slate-200 text-slate-500'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-slate-400 dark:text-slate-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
                    ACE Engine
                  </span>
                  <span className="text-emerald-500 font-mono text-[10px] font-medium">See execution trace</span>
                </div>
                <div className="text-[10px] text-slate-500 dark:text-slate-500">
                  ABCI-MI Platform &bull; Enterprise
                </div>
              </motion.div>
            )}
          </motion.aside>

          {/* Main Content Viewport */}
          <div className="flex-1 min-w-0">
            {/* Real-time System Status Telemetry Strip */}
            <WorkspaceStatus />
            <ErrorBox error={error}/>
            {/* View Transitions */}
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8, scale: 0.995 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.995 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="space-y-6"
              >
                {!auth.token ? <Connection onConnect={connect}/> : <WorkspacePanels
                  tab={activeTab} meetings={records} meetingId={selectedMeetingId} select={selectMeeting}
                  hasMoreMeetings={hasMoreMeetings} loadMoreMeetings={loadMoreMeetings}
                  refresh={refresh} auth={auth} navigate={setActiveTab}/>}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </main>

      {/* Notifications Drawer Modal */}
      {showNotificationsModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div
            className={`border rounded-2xl max-w-md w-full p-5 space-y-4 shadow-2xl ${
              theme === 'dark' ? 'bg-slate-900 border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
            }`}
          >
            <div className={`flex items-center justify-between border-b pb-3 ${theme === 'dark' ? 'border-slate-800' : 'border-slate-200'}`}>
              <div className="flex items-center space-x-2">
                <Bell className="w-4 h-4 text-indigo-400" />
                <h3 className="text-sm font-bold">Real-time Notification Events</h3>
              </div>
              <button
                onClick={() => setShowNotificationsModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
              {notifications.map((notif) => (
                <div
                  key={notif.id}
                  className={`p-3 rounded-xl border text-xs space-y-1 ${
                    notif.read
                      ? theme === 'dark'
                        ? 'bg-slate-950 border-slate-800/80 opacity-75'
                        : 'bg-slate-50 border-slate-200 opacity-75'
                      : theme === 'dark'
                      ? 'bg-slate-950 border-indigo-900/60 shadow-xs'
                      : 'bg-indigo-50/50 border-indigo-200'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{notif.title}</span>
                    <span className="text-[10px] text-slate-400 font-mono">{new Date(notif.created_at).toLocaleTimeString()}</span>
                  </div>
                  <p className={`text-[11px] ${theme === 'dark' ? 'text-slate-300' : 'text-slate-600'}`}>{notif.message}</p>
                </div>
              ))}
            </div>

            <div className={`pt-3 border-t flex justify-between items-center ${theme === 'dark' ? 'border-slate-800' : 'border-slate-200'}`}>
              <button
                onClick={() => {
                  write('/notifications/read-all').then(refreshNotifications).catch(e => setError(e.message));
                }}
                className="text-xs text-indigo-400 hover:text-indigo-300 font-medium"
              >
                Mark all as read
              </button>
              <button
                onClick={() => setShowNotificationsModal(false)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold ${
                  theme === 'dark' ? 'bg-slate-800 hover:bg-slate-700 text-white' : 'bg-slate-100 hover:bg-slate-200 text-slate-900'
                }`}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {isProfileSettingsOpen && auth.token && <Profile auth={auth} onClose={() => setIsProfileSettingsOpen(false)}
        onSignOut={signOut} onUpdate={(me:any) => setAuth(prev => ({...prev, user_name:me.full_name}))}/>}
    </div>
  );
}
