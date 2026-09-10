import React, { useState } from 'react';
import {
  Languages,
  Sparkles,
  CheckCircle2,
  Globe,
  Plus,
  Loader2,
  FileText
} from 'lucide-react';
import { TranslationItem } from '../types';

interface TranslationTesterProps {
  translations: TranslationItem[];
  meetingId: string;
  meetingTitle: string;
  onRequestTranslation: (meetingId: string, langCode: string) => void;
}

export interface LocaleDefinition {
  code: string;
  name: string;
  nativeName: string;
  category: 'Indic' | 'Global' | 'Code-Switched';
  script: string;
  direction?: 'ltr' | 'rtl';
}

export const SUPPORTED_LOCALES: LocaleDefinition[] = [
  // 10 Indic Locales & Scripts
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', category: 'Indic', script: 'Devanagari' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', category: 'Indic', script: 'Tamil' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', category: 'Indic', script: 'Telugu' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ', category: 'Indic', script: 'Kannada' },
  { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം', category: 'Indic', script: 'Malayalam' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', category: 'Indic', script: 'Bengali' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी', category: 'Indic', script: 'Devanagari' },
  { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી', category: 'Indic', script: 'Gujarati' },
  { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', category: 'Indic', script: 'Gurmukhi' },
  { code: 'en', name: 'English', nativeName: 'English', category: 'Global', script: 'Latin' },
  // 7 Expanded Global Locales
  { code: 'es', name: 'Spanish', nativeName: 'Español', category: 'Global', script: 'Latin' },
  { code: 'fr', name: 'French', nativeName: 'Français', category: 'Global', script: 'Latin' },
  { code: 'de', name: 'German', nativeName: 'Deutsch', category: 'Global', script: 'Latin' },
  { code: 'zh', name: 'Mandarin Chinese', nativeName: '中文 (简体)', category: 'Global', script: 'Simplified Chinese' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語', category: 'Global', script: 'Kanji / Kana' },
  { code: 'ru', name: 'Russian', nativeName: 'Русский', category: 'Global', script: 'Cyrillic' },
  { code: 'ar', name: 'Arabic', nativeName: 'العربية', category: 'Global', script: 'Arabic', direction: 'rtl' },
  // Code-Switched Dialects
  { code: 'hinglish', name: 'Hinglish', nativeName: 'हिंग्लिश (Hindi-English)', category: 'Code-Switched', script: 'Mixed Latin / Devanagari' },
  { code: 'tanglish', name: 'Tanglish', nativeName: 'தாங்கிலிஷ் (Tamil-English)', category: 'Code-Switched', script: 'Mixed Latin / Tamil' },
  { code: 'spanglish', name: 'Spanglish', nativeName: 'Spanglish (Spanish-English)', category: 'Code-Switched', script: 'Latin' },
  { code: 'franglais', name: 'Franglais', nativeName: 'Franglais (French-English)', category: 'Code-Switched', script: 'Latin' },
  { code: 'arabiya-english', name: 'Arabiya-English', nativeName: 'عربيزي (Arabic-English)', category: 'Code-Switched', script: 'Mixed Arabic / Latin' },
];

export const TranslationTester: React.FC<TranslationTesterProps> = ({
  translations,
  meetingId,
  meetingTitle,
  onRequestTranslation
}) => {
  const [selectedLang, setSelectedLang] = useState('de');
  const [isTranslating, setIsTranslating] = useState(false);

  const handleRequest = () => {
    setIsTranslating(true);
    setTimeout(() => {
      onRequestTranslation(meetingId, selectedLang);
      setIsTranslating(false);
    }, 600);
  };

  const meetingTranslations = translations.filter(t => t.meeting_id === meetingId);

  return (
    <div id="translation-tester" className="space-y-6">
      {/* Header & Request Generator */}
      <div className="bg-neutral-900/60 p-5 rounded-xl border border-neutral-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Languages className="w-5 h-5 text-amber-400" />
                Cross-Lingual Derived Translations Layer
              </h2>

            </div>
            <p className="text-xs text-neutral-400 mt-1">
              Generate derived multilingual intelligence across 17 global locales without mutating canonical transcripts or knowledge objects.
            </p>
          </div>
        </div>

        {/* Action Toolbar */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 bg-neutral-950 p-4 rounded-xl border border-neutral-800">
          <div className="flex-1">
            <label className="block text-[11px] font-medium text-neutral-400 mb-1">
              Select Target Locale for Translation
            </label>
            <select
              id="select-translation-target-lang"
              value={selectedLang}
              onChange={(e) => setSelectedLang(e.target.value)}
              className="w-full bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-500"
            >
              <optgroup label="Indic Locales (10 Languages & Scripts)">
                {SUPPORTED_LOCALES.filter(l => l.category === 'Indic').map((loc) => (
                  <option key={loc.code} value={loc.code}>
                    {loc.name} — {loc.nativeName} ({loc.code})
                  </option>
                ))}
              </optgroup>
              <optgroup label="Global Locales (7 Languages & Scripts)">
                {SUPPORTED_LOCALES.filter(l => l.category === 'Global').map((loc) => (
                  <option key={loc.code} value={loc.code}>
                    {loc.name} — {loc.nativeName} ({loc.code})
                  </option>
                ))}
              </optgroup>
              <optgroup label="Code-Switched Dialects">
                {SUPPORTED_LOCALES.filter(l => l.category === 'Code-Switched').map((loc) => (
                  <option key={loc.code} value={loc.code}>
                    {loc.name} — {loc.nativeName}
                  </option>
                ))}
              </optgroup>
            </select>
          </div>

          <div className="pt-2 sm:pt-4">
            <button
              id="btn-request-translation"
              onClick={handleRequest}
              disabled={isTranslating}
              className="w-full sm:w-auto px-4 py-2.5 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center justify-center transition-colors shadow-sm"
            >
              {isTranslating ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
              ) : (
                <Plus className="w-3.5 h-3.5 mr-1.5" />
              )}
              Synthesize Translation
            </button>
          </div>
        </div>
      </div>

      {/* Translations Grid */}
      <div className="space-y-4">
        <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
          Active Translated Representations ({meetingTranslations.length})
        </h3>

        {meetingTranslations.length === 0 ? (
          <div className="bg-neutral-900/40 p-8 rounded-xl border border-neutral-800 text-center text-xs text-neutral-500">
            No translations generated yet for this session. Select a target locale above and click &quot;Synthesize Translation&quot;.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {meetingTranslations.map((tr) => (
              <div key={tr.id} className="bg-neutral-900/40 p-5 rounded-xl border border-neutral-800 space-y-4">
                <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
                  <div className="flex items-center space-x-2">
                    <Globe className="w-4 h-4 text-amber-400" />
                    <h4 className="text-sm font-bold text-white">{tr.language_name}</h4>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-950 text-neutral-400 font-mono border border-neutral-800 uppercase">
                    {tr.language_code}
                  </span>
                </div>

                <div className="space-y-1.5">
                  <span className="text-[10px] font-bold text-amber-400 uppercase tracking-wider">
                    Executive Summary ({tr.language_code})
                  </span>
                  <p className="text-xs text-neutral-300 leading-relaxed font-sans bg-neutral-950 p-3 rounded-lg border border-neutral-800/80">
                    {tr.translated_summary}
                  </p>
                </div>

                {tr.translated_decisions && tr.translated_decisions.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
                      Decisions
                    </span>
                    <ul className="space-y-1 text-xs text-neutral-300">
                      {tr.translated_decisions.map((dec, i) => (
                        <li key={`decision-${tr.id}-${dec.substring(0, 20)}-${i}`} className="flex items-start space-x-1.5 text-[11px]">
                          <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0 mt-0.5" />
                          <span>{dec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
