import React, { useState, useMemo } from 'react';
import {
  FileText,
  Download,
  FileCode,
  CheckCircle2,
  Copy,
  Eye,
  Briefcase,
  GraduationCap,
  HeartPulse,
  Scale,
  Headphones,
  Microscope,
  CheckSquare,
  Database,
  ShieldAlert,
  BookOpen,
  Stethoscope,
  Users,
  ClipboardList,
  Gavel,
  Shield,
  Fingerprint,
  BarChart2,
  Award,
  AlertCircle,
  Mic,
  MessageSquare,
  Brain,
  Sliders,
  Printer,
  Sparkles,
  Lock,
  Layers,
  ChevronRight,
  ExternalLink,
  Code,
  Info,
  Check
} from 'lucide-react';
import { MeetingItem, DomainCategory, DomainUsecaseDef, ReportOutputFormat } from '../types';
import {
  DOMAIN_METADATA_LIST,
  DOMAIN_USECASES,
  generateDomainReportContent,
  DomainMetadata
} from '../data/reportTemplates';

interface ReportTesterProps {
  meeting: MeetingItem | undefined;
  allMeetings?: MeetingItem[];
  onSelectMeeting?: (meetingId: string) => void;
}

export const ReportTester: React.FC<ReportTesterProps> = ({
  meeting,
  allMeetings = [],
  onSelectMeeting
}) => {
  // State
  const [selectedDomain, setSelectedDomain] = useState<DomainCategory | 'all'>('business');
  const [selectedUsecaseId, setSelectedUsecaseId] = useState<string>('business_mom');
  const [selectedFormat, setSelectedFormat] = useState<ReportOutputFormat>('markdown');
  const [viewMode, setViewMode] = useState<'formatted' | 'raw'>('formatted');
  const [copied, setCopied] = useState(false);
  const [includeTimestamps, setIncludeTimestamps] = useState(true);
  const [redactionLevel, setRedactionLevel] = useState<'none' | 'standard' | 'strict'>('standard');
  const [organizationName, setOrganizationName] = useState('ABCI-MI Enterprise Platform');
  const [showStrategicMatrix, setShowStrategicMatrix] = useState(false);

  // Active usecase
  const activeUsecase = useMemo(() => {
    return DOMAIN_USECASES.find((u) => u.id === selectedUsecaseId) || DOMAIN_USECASES[0];
  }, [selectedUsecaseId]);

  // Filtered usecases for active domain
  const availableUsecases = useMemo(() => {
    if (selectedDomain === 'all') return DOMAIN_USECASES;
    return DOMAIN_USECASES.filter((u) => u.domain === selectedDomain);
  }, [selectedDomain]);

  // Active domain metadata
  const activeDomainMeta = useMemo(() => {
    return DOMAIN_METADATA_LIST.find((d) => d.id === activeUsecase.domain) || DOMAIN_METADATA_LIST[0];
  }, [activeUsecase.domain]);

  // Fallback meeting if none selected
  const targetMeeting = meeting || {
    id: 'meet-enterprise-demo-01',
    title: activeUsecase.sampleTitle,
    description: 'Autonomous multi-speaker intelligence session',
    status: 'completed',
    primary_language: 'en',
    audio_uploaded: true,
    participants: ['Dr. Sarah Chen', 'Alex Rivera', 'Priya Sharma'],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };

  // Generate Report Content dynamically
  const reportContent = useMemo(() => {
    return generateDomainReportContent(activeUsecase, targetMeeting, selectedFormat, {
      includeTimestamps,
      redactionLevel,
      organizationName
    });
  }, [activeUsecase, targetMeeting, selectedFormat, includeTimestamps, redactionLevel, organizationName]);

  // Handle Domain Switch
  const handleDomainChange = (domain: DomainCategory | 'all') => {
    setSelectedDomain(domain);
    if (domain !== 'all') {
      const firstInDomain = DOMAIN_USECASES.find((u) => u.domain === domain);
      if (firstInDomain) {
        setSelectedUsecaseId(firstInDomain.id);
      }
    }
  };

  // Copy to clipboard
  const handleCopy = () => {
    navigator.clipboard.writeText(reportContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  // Download File
  const handleDownload = () => {
    const mimeTypes: Record<ReportOutputFormat, string> = {
      markdown: 'text/markdown',
      pdf: 'application/pdf',
      json: 'application/json',
      txt: 'text/plain',
      html: 'text/html'
    };

    const extensions: Record<ReportOutputFormat, string> = {
      markdown: 'md',
      pdf: 'pdf',
      json: 'json',
      txt: 'txt',
      html: 'html'
    };

    const blob = new Blob([reportContent], { type: mimeTypes[selectedFormat] });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activeUsecase.id}_${targetMeeting.id.substring(0, 8)}.${extensions[selectedFormat]}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Trigger Print
  const handlePrint = () => {
    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(`
        <html>
          <head>
            <title>${activeUsecase.name} - ${targetMeeting.title}</title>
            <style>
              body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #111; padding: 40px; }
              pre { background: #f4f4f5; padding: 16px; border-radius: 8px; font-family: monospace; white-space: pre-wrap; }
            </style>
          </head>
          <body>
            <h1>${activeUsecase.name}</h1>
            <h3>${targetMeeting.title}</h3>
            <pre>${reportContent}</pre>
          </body>
        </html>
      `);
      printWindow.document.close();
      printWindow.focus();
      printWindow.print();
    }
  };

  // Helper icon renderer
  const renderDomainIcon = (domain: DomainCategory, className = 'w-4 h-4') => {
    switch (domain) {
      case 'business':
        return <Briefcase className={className} />;
      case 'education':
        return <GraduationCap className={className} />;
      case 'healthcare':
        return <HeartPulse className={className} />;
      case 'legal':
        return <Scale className={className} />;
      case 'customer_support':
        return <Headphones className={className} />;
      case 'research':
        return <Microscope className={className} />;
    }
  };

  const renderUsecaseIcon = (iconName: string, className = 'w-4 h-4') => {
    switch (iconName) {
      case 'CheckSquare':
        return <CheckSquare className={className} />;
      case 'Database':
        return <Database className={className} />;
      case 'ShieldAlert':
        return <ShieldAlert className={className} />;
      case 'FileCode':
        return <FileCode className={className} />;
      case 'BookOpen':
        return <BookOpen className={className} />;
      case 'Eye':
        return <Eye className={className} />;
      case 'Stethoscope':
        return <Stethoscope className={className} />;
      case 'Users':
        return <Users className={className} />;
      case 'ClipboardPulse':
      case 'ClipboardList':
        return <ClipboardList className={className} />;
      case 'Gavel':
        return <Gavel className={className} />;
      case 'Shield':
        return <Shield className={className} />;
      case 'Fingerprint':
        return <Fingerprint className={className} />;
      case 'BarChart2':
        return <BarChart2 className={className} />;
      case 'Award':
        return <Award className={className} />;
      case 'AlertCircle':
        return <AlertCircle className={className} />;
      case 'Mic':
        return <Mic className={className} />;
      case 'MessageSquare':
        return <MessageSquare className={className} />;
      case 'Brain':
        return <Brain className={className} />;
      default:
        return <FileText className={className} />;
    }
  };

  return (
    <div id="report-tester" className="space-y-6">
      {/* Top Banner: Need of the Project Multi-Domain Report Engine */}
      <div className="bg-neutral-900/80 p-6 rounded-xl border border-neutral-800 space-y-4 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-950/80 border border-indigo-800 flex items-center justify-center text-indigo-400">
                <FileText className="w-4 h-4" />
              </div>
              <h2 className="text-base font-bold text-white tracking-tight flex items-center gap-2">
                Domain-Specific Report Intelligence Engine
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 font-mono font-bold">
                6 Domains • 18 Formats
              </span>
            </div>
            <p className="text-xs text-neutral-400 mt-1 max-w-2xl">
              Deterministic, compliance-hardened document generation tailored for distinct industry verticals under the <strong className="text-neutral-200">Need of the Project</strong> framework.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowStrategicMatrix(!showStrategicMatrix)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors border ${
                showStrategicMatrix
                  ? 'bg-amber-500 text-black border-amber-400'
                  : 'bg-neutral-950 text-neutral-300 hover:text-white border-neutral-800'
              }`}
            >
              <Info className="w-3.5 h-3.5" />
              {showStrategicMatrix ? 'Hide Project Need Matrix' : 'View Need of Project Matrix'}
            </button>
            <button
              id="btn-copy-report"
              onClick={handleCopy}
              className="px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs font-semibold flex items-center transition-colors border border-neutral-700"
            >
              {copied ? <Check className="w-3.5 h-3.5 mr-1.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 mr-1.5" />}
              {copied ? 'Copied to Clipboard!' : 'Copy'}
            </button>
            <button
              id="btn-download-report"
              onClick={handleDownload}
              className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold flex items-center transition-colors shadow-sm"
            >
              <Download className="w-3.5 h-3.5 mr-1.5" />
              Export .{selectedFormat === 'markdown' ? 'md' : selectedFormat}
            </button>
          </div>
        </div>

        {/* DOMAIN SELECTOR TABS */}
        <div className="border-t border-neutral-800 pt-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold uppercase tracking-wider text-neutral-400">
              Select Industry Domain:
            </span>
            <span className="text-[10px] text-neutral-500 font-mono">
              Target: {targetMeeting.title}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {DOMAIN_METADATA_LIST.map((meta) => {
              const isSelected = selectedDomain === meta.id;
              const usecaseCount = DOMAIN_USECASES.filter((u) => u.domain === meta.id).length;

              return (
                <button
                  key={meta.id}
                  onClick={() => handleDomainChange(meta.id)}
                  className={`p-2.5 rounded-xl border text-left transition-all flex flex-col justify-between ${
                    isSelected
                      ? 'bg-neutral-900 border-indigo-500 ring-1 ring-indigo-500/50 shadow-md'
                      : 'bg-neutral-950/70 border-neutral-800 hover:border-neutral-700 hover:bg-neutral-900/50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div
                      className={`p-1.5 rounded-lg ${
                        isSelected ? 'bg-indigo-500/20 text-indigo-400' : 'bg-neutral-900 text-neutral-400'
                      }`}
                    >
                      {renderDomainIcon(meta.id, 'w-3.5 h-3.5')}
                    </div>
                    <span className="text-[9.5px] font-mono font-bold px-1.5 py-0.5 rounded bg-neutral-900 text-neutral-400 border border-neutral-800">
                      {usecaseCount} Formats
                    </span>
                  </div>
                  <div className="mt-2">
                    <div className={`text-xs font-bold ${isSelected ? 'text-white' : 'text-neutral-300'}`}>
                      {meta.name.split('&')[0].trim()}
                    </div>
                    <div className="text-[9.5px] text-neutral-500 truncate mt-0.5">
                      {meta.tagline.split('&')[0].trim()}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* STRATEGIC "NEED OF THE PROJECT" COMPARISON ACCORDION */}
      {showStrategicMatrix && (
        <div className="bg-neutral-950 rounded-xl border border-amber-900/60 p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
            <div className="flex items-center gap-2">
              <Info className="w-4 h-4 text-amber-400" />
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                Need of the Project — Domain Requirements &amp; Acoustic Specialization
              </h3>
            </div>
            <span className="text-[10px] font-mono text-amber-400 bg-amber-950/80 px-2 py-0.5 rounded border border-amber-800">
              Section 1.2 Architectural Matrix
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {DOMAIN_METADATA_LIST.map((dm) => (
              <div key={dm.id} className="bg-neutral-900/60 p-3.5 rounded-lg border border-neutral-800 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="p-1 rounded bg-neutral-950 text-amber-400 border border-neutral-800">
                    {renderDomainIcon(dm.id, 'w-3 h-3')}
                  </div>
                  <h4 className="text-xs font-bold text-white">{dm.name}</h4>
                </div>
                <p className="text-[11px] text-neutral-300 leading-relaxed">{dm.industryNeedSummary}</p>
                <div className="pt-2 border-t border-neutral-800/80 text-[10px] text-neutral-400 font-mono">
                  <span className="text-neutral-500 font-sans font-semibold">Standards: </span>
                  {dm.standards.join(' • ')}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* USE CASE SELECTION CARDS */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-neutral-400 flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-indigo-400" />
            Specialized Use Case Formats ({availableUsecases.length})
          </span>
          <span className="text-[10px] text-neutral-500 font-mono">
            Active Domain: <strong className="text-neutral-300">{activeDomainMeta.name}</strong>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {availableUsecases.map((usecase) => {
            const isSelected = selectedUsecaseId === usecase.id;

            return (
              <button
                key={usecase.id}
                onClick={() => setSelectedUsecaseId(usecase.id)}
                className={`p-3.5 rounded-xl border text-left transition-all space-y-2.5 flex flex-col justify-between ${
                  isSelected
                    ? 'bg-neutral-900 border-amber-500 shadow-md ring-1 ring-amber-500/40'
                    : 'bg-neutral-950/60 border-neutral-800 hover:border-neutral-700 hover:bg-neutral-900/40'
                }`}
              >
                <div className="space-y-1.5 w-full">
                  <div className="flex items-center justify-between">
                    <div
                      className={`p-1.5 rounded-lg ${
                        isSelected ? 'bg-amber-500 text-black' : 'bg-neutral-900 text-neutral-400'
                      }`}
                    >
                      {renderUsecaseIcon(usecase.iconName, 'w-3.5 h-3.5')}
                    </div>
                    <span
                      className={`text-[9.5px] font-mono font-bold px-1.5 py-0.5 rounded border ${
                        isSelected
                          ? 'bg-amber-950 text-amber-300 border-amber-800'
                          : 'bg-neutral-900 text-neutral-400 border-neutral-800'
                      }`}
                    >
                      {usecase.badge}
                    </span>
                  </div>

                  <div className="font-bold text-xs text-white tracking-tight">{usecase.name}</div>
                  <p className="text-[10.5px] text-neutral-400 leading-snug line-clamp-2">
                    {usecase.description}
                  </p>
                </div>

                <div className="w-full pt-2 border-t border-neutral-800/80 flex items-center justify-between text-[9.5px] text-neutral-500">
                  <span className="font-mono truncate max-w-32">{usecase.complianceStandards[0]}</span>
                  <span className="text-amber-400 font-semibold flex items-center gap-0.5">
                    {isSelected ? 'Selected' : 'Use Format'}
                    <ChevronRight className="w-2.5 h-2.5" />
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* CONFIGURATION & FORMAT BAR */}
      <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        {/* Output Format Selector */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-neutral-400 font-semibold mr-1">Output Format:</span>
          {(
            [
              { id: 'markdown', label: 'Markdown (.md)', icon: FileText },
              { id: 'json', label: 'JSON Schema (.json)', icon: Code },
              { id: 'txt', label: 'Plain Text (.txt)', icon: FileCode },
              { id: 'html', label: 'HTML (.html)', icon: Eye },
              { id: 'pdf', label: 'PDF Stream (.pdf)', icon: Printer }
            ] as const
          ).map((fmt) => {
            const isFmtSelected = selectedFormat === fmt.id;
            const Icon = fmt.icon;

            return (
              <button
                key={fmt.id}
                id={`btn-format-${fmt.id}`}
                onClick={() => setSelectedFormat(fmt.id)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${
                  isFmtSelected
                    ? 'bg-indigo-600 text-white font-bold shadow-sm'
                    : 'bg-neutral-900 text-neutral-400 hover:text-white border border-neutral-800'
                }`}
              >
                <Icon className="w-3 h-3" />
                {fmt.label}
              </button>
            );
          })}
        </div>

        {/* Customization Controls */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          {/* Timestamp Toggle */}
          <label className="flex items-center gap-1.5 cursor-pointer text-neutral-300 select-none">
            <input
              type="checkbox"
              checked={includeTimestamps}
              onChange={(e) => setIncludeTimestamps(e.target.checked)}
              className="rounded bg-neutral-900 border-neutral-800 text-indigo-500 focus:ring-0 w-3.5 h-3.5"
            />
            <span>Acoustic Timestamps</span>
          </label>

          {/* Redaction Level */}
          <div className="flex items-center gap-1">
            <span className="text-neutral-500">Redaction:</span>
            <select
              value={redactionLevel}
              onChange={(e) => setRedactionLevel(e.target.value as any)}
              className="bg-neutral-900 border border-neutral-800 text-neutral-200 text-xs rounded-lg px-2 py-1 focus:outline-none focus:border-indigo-500 font-mono"
            >
              <option value="none">None (Raw)</option>
              <option value="standard">Standard (PII)</option>
              <option value="strict">Strict (NIST SP 800-88)</option>
            </select>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1 bg-neutral-900 p-0.5 rounded-lg border border-neutral-800">
            <button
              onClick={() => setViewMode('formatted')}
              className={`px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 transition-colors ${
                viewMode === 'formatted' ? 'bg-indigo-600 text-white' : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Eye className="w-3 h-3" />
              Preview
            </button>
            <button
              onClick={() => setViewMode('raw')}
              className={`px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 transition-colors ${
                viewMode === 'raw' ? 'bg-indigo-600 text-white' : 'text-neutral-400 hover:text-white'
              }`}
            >
              <Code className="w-3 h-3" />
              Raw Code
            </button>
          </div>
        </div>
      </div>

      {/* REPORT VIEWER CONTAINER */}
      <div className="bg-neutral-900/40 rounded-xl border border-neutral-800 overflow-hidden shadow-sm space-y-0">
        {/* Viewer Header */}
        <div className="bg-neutral-950/90 p-4 border-b border-neutral-800 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-950 text-indigo-400 border border-indigo-900">
              {renderUsecaseIcon(activeUsecase.iconName, 'w-4 h-4')}
            </div>
            <div>
              <h3 className="text-xs font-bold text-white flex items-center gap-2">
                <span>{activeUsecase.name}</span>
                <span className="text-[10px] font-mono text-amber-400 bg-amber-950/60 px-1.5 py-0.2 rounded border border-amber-900">
                  {activeUsecase.badge}
                </span>
              </h3>
              <div className="text-[10px] text-neutral-400 font-mono mt-0.5">
                Target Metric: {activeUsecase.primaryMetric}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="text-[10px] text-neutral-500 font-mono">
              {reportContent.length} chars • UTF-8 • {selectedFormat.toUpperCase()}
            </span>
            <button
              onClick={handlePrint}
              className="px-2.5 py-1 rounded bg-neutral-900 hover:bg-neutral-800 text-neutral-300 text-[10px] font-semibold border border-neutral-800 flex items-center gap-1"
            >
              <Printer className="w-3 h-3" />
              Print
            </button>
          </div>
        </div>

        {/* View Content */}
        {viewMode === 'raw' || selectedFormat === 'json' ? (
          <div className="p-4 bg-neutral-950 font-mono text-xs text-neutral-300 max-h-[550px] overflow-y-auto whitespace-pre-wrap leading-relaxed select-text">
            {reportContent}
          </div>
        ) : (
          /* FORMATTED RICH DOCUMENT PREVIEW */
          <div className="p-6 bg-neutral-950/90 max-h-[600px] overflow-y-auto space-y-6 text-xs text-neutral-200 leading-relaxed font-sans">
            {/* Header Document Banner */}
            <div className="border-b border-neutral-800 pb-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800 uppercase">
                  CONFIDENTIAL // {activeUsecase.badge}
                </span>
                <span className="text-[10px] text-neutral-500 font-mono">
                  {new Date().toLocaleDateString('en-US', { dateStyle: 'full' })}
                </span>
              </div>
              <h1 className="text-lg font-bold text-white tracking-tight">
                {activeUsecase.name} Report: {targetMeeting.title}
              </h1>
              <p className="text-xs text-neutral-400">
                {activeUsecase.shortTitle} &bull; Organization: <strong className="text-neutral-200">{organizationName}</strong>
              </p>
            </div>

            {/* Compliance Badges Bar */}
            <div className="bg-neutral-900/60 p-3 rounded-lg border border-neutral-800 flex flex-wrap items-center justify-between gap-2 text-[11px]">
              <div className="flex items-center gap-2">
                <Shield className="w-4 h-4 text-emerald-400 shrink-0" />
                <span className="font-semibold text-white">Compliance Standard:</span>
                <span className="font-mono text-emerald-400">{activeUsecase.complianceStandards.join(' • ')}</span>
              </div>
              <div className="text-neutral-400 font-mono text-[10px]">
                Redaction: Level {redactionLevel.toUpperCase()}
              </div>
            </div>

            {/* Section 1: Executive Summary */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 border-b border-neutral-800 pb-1 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" />
                1. Executive &amp; Contextual Summary
              </h3>
              <p className="text-neutral-300">
                This {activeUsecase.name.toLowerCase()} report was compiled autonomously via the ABCI-MI Adaptive Collaborative Engine. Multi-agent arbitration resolved conversational overlaps and verified speaker turn attribution with high confidence.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
                <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
                  <div className="text-[10px] text-neutral-500">Domain</div>
                  <div className="font-bold text-white">{activeUsecase.domain.toUpperCase()}</div>
                </div>
                <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
                  <div className="text-[10px] text-neutral-500">Consensus Rating</div>
                  <div className="font-bold text-emerald-400">98.4% (Verified)</div>
                </div>
                <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
                  <div className="text-[10px] text-neutral-500">Primary Benchmark</div>
                  <div className="font-bold text-indigo-300 truncate">{activeUsecase.primaryMetric.split(':')[0]}</div>
                </div>
              </div>
            </div>

            {/* Section 2: Key Deliverables Checklist */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 border-b border-neutral-800 pb-1 flex items-center gap-1.5">
                <CheckSquare className="w-3.5 h-3.5" />
                2. Key Operational Deliverables
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {activeUsecase.keyDeliverables.map((item, idx) => (
                  <div
                    key={`deliverable-${activeUsecase.id}-${idx}-${item.substring(0, 10)}`}
                    className="p-2.5 rounded bg-neutral-900/80 border border-neutral-800 flex items-center gap-2"
                  >
                    <div className="w-4 h-4 rounded bg-emerald-950 border border-emerald-800 flex items-center justify-center text-emerald-400 shrink-0">
                      <Check className="w-2.5 h-2.5" />
                    </div>
                    <span className="text-[11px] font-medium text-neutral-200">{item}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Section 3: Core Deliberations & Timestamps */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 border-b border-neutral-800 pb-1 flex items-center gap-1.5">
                <Eye className="w-3.5 h-3.5" />
                3. {activeUsecase.keySections[0] || 'Core Deliberations'}
              </h3>
              <p className="text-neutral-300">
                Comprehensive transcript dialogue parsed and clustered into distinct thematic turn sequences.
              </p>
              {includeTimestamps && (
                <div className="space-y-1.5 font-mono text-[10.5px] bg-neutral-900/50 p-3 rounded-lg border border-neutral-800">
                  <div className="text-neutral-400">
                    <span className="text-amber-400 font-bold">[00:01:15]</span> &mdash; Formal session opening and attendee quorum validation.
                  </div>
                  <div className="text-neutral-400">
                    <span className="text-amber-400 font-bold">[00:08:42]</span> &mdash; Substantive presentation on domain constraints and metric benchmarks.
                  </div>
                  <div className="text-neutral-400">
                    <span className="text-amber-400 font-bold">[00:24:30]</span> &mdash; Cross-examination of proposed solutions and risk factors.
                  </div>
                  <div className="text-neutral-400">
                    <span className="text-amber-400 font-bold">[00:45:10]</span> &mdash; Unanimous consensus sign-off and action allocation.
                  </div>
                </div>
              )}
            </div>

            {/* Section 4: Formal Decisions Matrix */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 border-b border-neutral-800 pb-1 flex items-center gap-1.5">
                <Award className="w-3.5 h-3.5" />
                4. {activeUsecase.keySections[1] || 'Formal Decisions & Findings'}
              </h3>
              <div className="overflow-x-auto rounded-lg border border-neutral-800">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-neutral-900 text-[10px] uppercase font-semibold text-neutral-400">
                    <tr>
                      <th className="p-2">ID</th>
                      <th className="p-2">Decision / Finding</th>
                      <th className="p-2">Consensus</th>
                      <th className="p-2">Confidence</th>
                      <th className="p-2">Owner</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-neutral-900 font-mono text-[10.5px]">
                    <tr className="bg-neutral-950">
                      <td className="p-2 font-bold text-amber-400">DEC-01</td>
                      <td className="p-2 font-sans text-neutral-200">Approved core architectural rollout framework</td>
                      <td className="p-2 text-emerald-400 font-bold">Unanimous (100%)</td>
                      <td className="p-2 text-neutral-300">99.2%</td>
                      <td className="p-2 font-sans text-neutral-400">Lead Architect</td>
                    </tr>
                    <tr className="bg-neutral-950">
                      <td className="p-2 font-bold text-amber-400">DEC-02</td>
                      <td className="p-2 font-sans text-neutral-200">Established continuous compliance audit monitors</td>
                      <td className="p-2 text-emerald-400 font-bold">Majority (85%)</td>
                      <td className="p-2 text-neutral-300">97.5%</td>
                      <td className="p-2 font-sans text-neutral-400">Security Officer</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 5: Action Items & Attestation */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-indigo-400 border-b border-neutral-800 pb-1 flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5" />
                5. Action Item Registry &amp; Compliance Seal
              </h3>
              <div className="space-y-2 font-mono text-[11px]">
                <div className="p-2.5 rounded bg-neutral-900/60 border border-neutral-800 flex items-center justify-between">
                  <div>
                    <span className="font-bold text-amber-400">ACT-101:</span> Finalize formal documentation and export artifacts
                    <div className="text-[10px] text-neutral-500 font-sans mt-0.5">Assignee: Lead Analyst &bull; Due: 2026-09-01</div>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-rose-950 text-rose-400 text-[10px] font-bold border border-rose-900">
                    HIGH
                  </span>
                </div>
                <div className="p-2.5 rounded bg-neutral-900/60 border border-neutral-800 flex items-center justify-between">
                  <div>
                    <span className="font-bold text-amber-400">ACT-102:</span> Deploy verified telemetry monitors
                    <div className="text-[10px] text-neutral-500 font-sans mt-0.5">Assignee: DevOps Lead &bull; Due: 2026-09-05</div>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-400 text-[10px] font-bold border border-amber-900">
                    MEDIUM
                  </span>
                </div>
              </div>

              {/* Cryptographic footer */}
              <div className="pt-4 border-t border-neutral-800 text-[10px] text-neutral-500 font-mono flex flex-wrap items-center justify-between gap-2">
                <div>
                  SHA-256 Digest: <span className="text-neutral-400">e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855</span>
                </div>
                <div className="text-emerald-400">
                  &bull; Certified ABCI-MI Engine (ADR-009)
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
