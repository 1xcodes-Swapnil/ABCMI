import React, { useState } from 'react';
import {
  Search,
  Sparkles,
  HelpCircle,
  Clock,
  User,
  Quote,
  CheckCircle2,
  AlertCircle,
  Send,
  Loader2,
  Filter
} from 'lucide-react';
import { GroundedQuery, MeetingItem } from '../types';

interface QueryTesterProps {
  queries: GroundedQuery[];
  meetings: MeetingItem[];
  selectedMeetingId: string;
  onRunQuery: (queryText: string, meetingId?: string) => void;
}

export const QueryTester: React.FC<QueryTesterProps> = ({
  queries,
  meetings,
  selectedMeetingId,
  onRunQuery
}) => {
  const [inputText, setInputText] = useState('');
  const [scopedMeetingId, setScopedMeetingId] = useState<string>(selectedMeetingId || 'all');
  const [isQuerying, setIsQuerying] = useState(false);

  const sampleQueries = [
    'What were the key decisions made regarding dataset selection?',
    'Why did the team decide against using Tourism data?',
    'What issues occurred with email and how were they resolved?',
    'Which Indian states showed highest property theft vs recovery?'
  ];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isQuerying) return;

    setIsQuerying(true);
    const targetScope = scopedMeetingId === 'all' ? undefined : scopedMeetingId;
    
    setTimeout(() => {
      onRunQuery(inputText, targetScope);
      setInputText('');
      setIsQuerying(false);
    }, 600);
  };

  const handleSelectSample = (sample: string) => {
    setInputText(sample);
  };

  return (
    <div id="query-tester" className="space-y-6">
      {/* Header & Prompt Box */}
      <div className="bg-neutral-900/60 p-5 rounded-xl border border-neutral-800 space-y-4">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-indigo-400" />
              Ask ABCI-MI &mdash; Grounded Knowledge Query Engine
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-950 text-indigo-400 border border-indigo-900 font-mono">
              Phase 4.23 &bull; ADR-011
            </span>
          </div>
          <p className="text-xs text-neutral-400 mt-1">
            Query across authorized meetings and canonical Knowledge Objects with exact transcript citation grounding and confidence scoring.
          </p>
        </div>

        {/* Query Input Form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="relative flex-1">
              <input
                id="input-grounded-query"
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                placeholder="Ask a question about meeting discussions, decisions, or action items..."
                className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-4 pr-10 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-indigo-500 transition-colors"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                id="select-query-meeting-scope"
                value={scopedMeetingId}
                onChange={(e) => setScopedMeetingId(e.target.value)}
                className="bg-neutral-950 border border-neutral-800 rounded-lg px-3 py-2.5 text-xs text-neutral-300 focus:outline-none focus:border-indigo-500"
              >
                <option value="all">Scope: All Meetings</option>
                {meetings.map((m) => (
                  <option key={m.id} value={m.id}>
                    Scope: {m.title.substring(0, 24)}...
                  </option>
                ))}
              </select>
              <button
                id="btn-submit-grounded-query"
                type="submit"
                disabled={!inputText.trim() || isQuerying}
                className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center transition-colors shadow-sm"
              >
                {isQuerying ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                ) : (
                  <Send className="w-3.5 h-3.5 mr-1.5" />
                )}
                Query
              </button>
            </div>
          </div>

          {/* Quick Suggestions */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-neutral-400">
            <span className="text-neutral-500">Sample Queries:</span>
            {sampleQueries.map((sq) => (
              <button
                key={`sample-query-${sq.replace(/\s+/g, '-').substring(0, 25)}`}
                type="button"
                onClick={() => handleSelectSample(sq)}
                className="px-2 py-0.5 rounded bg-neutral-950 hover:bg-neutral-800 text-neutral-300 border border-neutral-800 transition-colors text-[11px]"
              >
                {sq}
              </button>
            ))}
          </div>
        </form>
      </div>

      {/* Query Results / History Feed */}
      <div className="space-y-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
          Grounded Answers &amp; Attribution Trace ({queries.length})
        </h3>

        {queries.map((q) => (
          <div key={q.id} className="bg-neutral-900/40 p-5 rounded-xl border border-neutral-800 space-y-4">
            <div className="flex items-start justify-between gap-3 border-b border-neutral-800/60 pb-3">
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 text-[10px] font-bold border border-indigo-900">
                    Query #{q.id.substring(0, 6)}
                  </span>
                  <span className="text-xs text-neutral-400">{new Date(q.created_at).toLocaleTimeString()}</span>
                </div>
                <h4 className="text-sm font-semibold text-white">{q.query_text}</h4>
              </div>
              <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 text-[11px] font-bold border border-emerald-800 flex items-center shrink-0">
                <CheckCircle2 className="w-3 h-3 mr-1" />
                {(q.confidence * 100).toFixed(0)}% Confidence
              </span>
            </div>

            {/* Answer */}
            <div className="bg-neutral-950 p-4 rounded-lg border border-neutral-800/80 space-y-2">
              <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-wider">Synthesized Answer</span>
              <p className="text-xs text-neutral-200 leading-relaxed font-sans">{q.answer_text}</p>
            </div>

            {/* Citations Grounding */}
            {q.citations && q.citations.length > 0 && (
              <div className="space-y-2 pt-1">
                <span className="text-[10px] font-bold text-neutral-400 uppercase tracking-wider flex items-center gap-1">
                  <Quote className="w-3 h-3 text-indigo-400" />
                  Grounded Citations ({q.citations.length})
                </span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {q.citations.map((cit, idx) => (
                    <div key={`citation-${q.id}-${cit.timestamp}-${idx}`} className="bg-neutral-950 p-3 rounded-lg border border-neutral-800 text-xs space-y-1.5">
                      <div className="flex items-center justify-between text-[11px] text-neutral-400">
                        <span className="font-semibold text-indigo-300">{cit.speaker}</span>
                        <span className="font-mono text-neutral-500">{cit.timestamp}</span>
                      </div>
                      <p className="text-[11px] text-neutral-300 italic">
                        &ldquo;{cit.snippet}&rdquo;
                      </p>
                      <div className="text-[10px] text-neutral-500 truncate">
                        Meeting: {cit.meeting_title}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
