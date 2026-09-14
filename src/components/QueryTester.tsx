import React, { useState, useEffect, useRef } from 'react';
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
  Filter,
  Mic,
  MicOff,
  Radio,
  Volume2,
  X
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

  // Speech Recognition State
  const [isListening, setIsListening] = useState(false);
  const [speechLanguage, setSpeechLanguage] = useState('en-US');
  const [voiceFeedback, setVoiceFeedback] = useState<string | null>(null);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);

  const sampleQueries = [
    'What were the key decisions made regarding dataset selection?',
    'Why did the team decide against using Tourism data?',
    'What issues occurred with email and how were they resolved?',
    'Which Indian states showed highest property theft vs recovery?'
  ];

  // Initialize and clean up speech recognition
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {
          // ignore
        }
      }
    };
  }, []);

  const handleToggleVoiceCommand = () => {
    // If already listening, stop
    if (isListening) {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {
          // ignore
        }
      }
      setIsListening(false);
      setVoiceFeedback(null);
      return;
    }

    // Check browser support for SpeechRecognition
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSpeechError(
        'Speech recognition is not natively supported in this browser. Please use Chrome, Edge, or Safari, or enter queries manually.'
      );
      return;
    }

    setSpeechError(null);
    setVoiceFeedback('Listening... Speak your question clearly.');

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = speechLanguage;

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: any) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const transcriptPiece = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalTranscript += transcriptPiece;
          } else {
            interimTranscript += transcriptPiece;
          }
        }

        const currentText = finalTranscript || interimTranscript;
        if (currentText.trim()) {
          setInputText(currentText);
          setVoiceFeedback(`Captured: "${currentText}"`);
        }
      };

      recognition.onerror = (event: any) => {
        console.warn('SpeechRecognition error:', event.error);
        if (event.error === 'not-allowed') {
          setSpeechError(
            'Microphone access was denied. Please allow microphone permissions in your browser to use Voice Command.'
          );
        } else if (event.error === 'no-speech') {
          setSpeechError('No speech was detected. Please click Voice Command and try again.');
        } else if (event.error === 'network') {
          setSpeechError('Network error during speech recognition. Please check your connection.');
        } else {
          setSpeechError(`Voice capture notice: ${event.error}`);
        }
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err: any) {
      console.error('Failed to start SpeechRecognition:', err);
      setSpeechError(err?.message || 'Could not start voice recognition.');
      setIsListening(false);
      setVoiceFeedback(null);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isQuerying) return;

    if (isListening && recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        // ignore
      }
      setIsListening(false);
    }

    setIsQuerying(true);
    const targetScope = scopedMeetingId === 'all' ? undefined : scopedMeetingId;

    setTimeout(() => {
      onRunQuery(inputText, targetScope);
      setInputText('');
      setVoiceFeedback(null);
      setIsQuerying(false);
    }, 600);
  };

  const handleSelectSample = (sample: string) => {
    setInputText(sample);
    setVoiceFeedback(null);
    setSpeechError(null);
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
            Query across authorized meetings and canonical Knowledge Objects with exact transcript citation grounding, confidence scoring, and browser voice commands.
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
                placeholder={isListening ? "Listening to your voice... Speak your query" : "Ask a question about meeting discussions, decisions, or action items..."}
                className={`w-full bg-neutral-950 border rounded-lg pl-4 pr-10 py-2.5 text-xs text-white placeholder-neutral-500 focus:outline-none transition-all ${
                  isListening
                    ? 'border-rose-500/80 ring-2 ring-rose-500/20 shadow-md shadow-rose-950/40'
                    : 'border-neutral-800 focus:border-indigo-500'
                }`}
              />
              {inputText && (
                <button
                  type="button"
                  onClick={() => {
                    setInputText('');
                    setVoiceFeedback(null);
                  }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500 hover:text-neutral-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {/* Voice Command Button */}
              <button
                id="btn-voice-command"
                type="button"
                onClick={handleToggleVoiceCommand}
                title={isListening ? "Stop Voice Listening" : "Start Voice Command (Speech Recognition)"}
                className={`px-3.5 py-2.5 rounded-lg text-xs font-semibold flex items-center transition-all cursor-pointer ${
                  isListening
                    ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/30 animate-pulse'
                    : 'bg-neutral-950 hover:bg-neutral-800 text-rose-400 border border-rose-900/50 hover:border-rose-700'
                }`}
              >
                {isListening ? (
                  <>
                    <MicOff className="w-3.5 h-3.5 mr-1.5 animate-bounce" />
                    <span>Listening...</span>
                  </>
                ) : (
                  <>
                    <Mic className="w-3.5 h-3.5 mr-1.5" />
                    <span>Voice Command</span>
                  </>
                )}
              </button>

              {/* Speech Language Selector */}
              <select
                id="select-voice-language"
                value={speechLanguage}
                onChange={(e) => setSpeechLanguage(e.target.value)}
                disabled={isListening}
                className="bg-neutral-950 border border-neutral-800 rounded-lg px-2.5 py-2.5 text-xs text-neutral-300 focus:outline-none focus:border-indigo-500"
                title="Voice Input Language"
              >
                <option value="en-US">EN (English)</option>
                <option value="hi-IN">HI (हिन्दी)</option>
                <option value="ta-IN">TA (தமிழ்)</option>
                <option value="te-IN">TE (తెలుగు)</option>
                <option value="bn-IN">BN (বাংলা)</option>
                <option value="es-ES">ES (Español)</option>
                <option value="fr-FR">FR (Français)</option>
                <option value="de-DE">DE (Deutsch)</option>
                <option value="ja-JP">JA (日本語)</option>
              </select>

              {/* Scope Selector */}
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

              {/* Submit Query Button */}
              <button
                id="btn-submit-grounded-query"
                type="submit"
                disabled={!inputText.trim() || isQuerying}
                className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center transition-colors shadow-sm cursor-pointer"
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

          {/* Voice Command Live Feedback Banner */}
          {isListening && (
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs text-rose-200 animate-in fade-in duration-200">
              <div className="flex items-center space-x-2">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
                <span className="font-semibold">Speech Recognition Active:</span>
                <span className="text-rose-300 italic">{voiceFeedback || 'Speak your question now...'}</span>
              </div>
              <button
                type="button"
                onClick={handleToggleVoiceCommand}
                className="text-xs px-2 py-0.5 rounded bg-rose-900/60 hover:bg-rose-800 text-white font-medium transition-colors"
              >
                Done
              </button>
            </div>
          )}

          {/* Speech Error Banner */}
          {speechError && (
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-amber-950/40 border border-amber-800/60 text-xs text-amber-200">
              <div className="flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
                <span>{speechError}</span>
              </div>
              <button
                type="button"
                onClick={() => setSpeechError(null)}
                className="text-amber-400 hover:text-amber-200 p-1"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Quick Suggestions */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-neutral-400">
            <span className="text-neutral-500">Sample Queries:</span>
            {sampleQueries.map((sq) => (
              <button
                key={`sample-query-${sq.replace(/\s+/g, '-').substring(0, 25)}`}
                type="button"
                onClick={() => handleSelectSample(sq)}
                className="px-2 py-0.5 rounded bg-neutral-950 hover:bg-neutral-800 text-neutral-300 border border-neutral-800 transition-colors text-[11px] cursor-pointer"
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
