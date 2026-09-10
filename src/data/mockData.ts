import {
  MeetingItem,
  MeetingIntelligence,
  KnowledgeObject,
  GroundedQuery,
  TranslationItem,
  ReportItem,
  NotificationItem,
  AuditLogItem,
  EndpointDef
} from '../types';

export const INITIAL_MEETINGS: MeetingItem[] = [
  {
    id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
    title: 'Tableau Crime Data Analytics & Lab Evaluation',
    description: 'Collaborative analysis of Crime in India dataset, multi-sheet dashboard generation and report submission.',
    status: 'completed',
    primary_language: 'en',
    duration_minutes: 23,
    audio_uploaded: true,
    audio_file_name: '7a0285d2-b532-4912-80cf-67383a71a770_sample_meeting.wav',
    audio_file_size_mb: 0.06,
    participants: ['Niti', 'Sneha', 'Ayush', 'Instructor', 'Bhavya'],
    created_at: '2026-08-24T11:41:00Z',
    updated_at: '2026-08-24T11:47:00Z',
  },
  {
    id: '2395857a-d35f-462d-b54c-d76cdb91f969',
    title: 'Q3 Enterprise Architecture & Vector Storage Review',
    description: 'Evaluation of Qdrant vector database latency, Postgres schema sharding, and Redis failover policies.',
    status: 'completed',
    primary_language: 'en',
    duration_minutes: 45,
    audio_uploaded: true,
    audio_file_name: 'q3_architecture_sync.mp3',
    audio_file_size_mb: 42.5,
    participants: ['David Chen', 'Sarah Connor', 'Marcus Brody'],
    created_at: '2026-08-23T14:00:00Z',
    updated_at: '2026-08-23T14:50:00Z',
  },
  {
    id: '35ac8606-51cf-4947-9755-334708f94af7',
    title: 'Multilingual Ingestion & Diarization Benchmark',
    description: 'Sprint planning for 17-locale real-time code-switching transcription testing.',
    status: 'processing',
    primary_language: 'hi',
    duration_minutes: 30,
    audio_uploaded: true,
    audio_file_name: 'multilingual_benchmark.wav',
    audio_file_size_mb: 18.2,
    participants: ['Vikram Patel', 'Elena Rostova', 'Kenji Sato'],
    created_at: '2026-08-24T08:15:00Z',
    updated_at: '2026-08-24T08:30:00Z',
  },
  {
    id: '6bc63e54-c559-4327-ad32-c9f427600d48',
    title: 'Security Compliance & RBAC Audit Walkthrough',
    description: 'Penetration test findings, token revocation testing, and audit log tamper validation.',
    status: 'scheduled',
    primary_language: 'en',
    scheduled_start: '2026-08-25T10:00:00Z',
    duration_minutes: 60,
    audio_uploaded: false,
    participants: ['Chief Security Officer', 'Audit Lead'],
    created_at: '2026-08-24T07:00:00Z',
    updated_at: '2026-08-24T07:00:00Z',
  }
];

export const INITIAL_INTELLIGENCE: Record<string, MeetingIntelligence> = {
  '7a4cb6f8-2c52-4023-ad32-53b9a3bad142': {
    meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
    executive_summary: 'Students analyzed national crime statistics in Tableau under time constraints. Overcoming portal authentication and dataset merging hurdles, they produced 10 visualizations across 3 dashboards (Temporal Trends, Regional Stolen vs. Recovered Property, and SC/ST & Foreigner Demographics), culminating in an interactive Storyboard and Word doc submission.',
    key_takeaways: [
      'Selected Crime in India dataset over Tourism to exploit richer categorical metrics.',
      'Identified severe property recovery deficit in Delhi and Maharashtra (theft volume high, recovery < 35%).',
      'Engineered dual-axis charts and treemaps to bypass Tableau unrecognized geography errors.',
      'Pivoted to MS Teams when email delivery was blocked by firewall.'
    ],
    confidence_score: 0.94,
    decisions: [
      {
        id: 'dec-1',
        decision_text: 'Adopt Crime in India dataset over Tourism data for the lab assignment.',
        decision_maker: 'Team Consensus',
        consensus_level: 'unanimous',
        confidence: 0.98,
        timestamp_offset: 70,
        verification_status: 'verified'
      },
      {
        id: 'dec-2',
        decision_text: 'Group visualizations into 3 distinct sheets for Trends and 3 for Regional distributions.',
        decision_maker: 'Ayush / Niti',
        consensus_level: 'majority',
        confidence: 0.95,
        timestamp_offset: 3450,
        verification_status: 'verified'
      },
      {
        id: 'dec-3',
        decision_text: 'Use MS Teams file transfer rather than Gmail due to attachment bounce errors.',
        decision_maker: 'Sneha',
        consensus_level: 'directive',
        confidence: 0.99,
        timestamp_offset: 5120,
        verification_status: 'verified'
      }
    ],
    action_items: [
      {
        id: 'act-1',
        description: 'Export all 10 Tableau worksheets & 3 dashboards to high-res PNG for the report.',
        assignee: 'Niti',
        due_date: '2026-08-24T12:30:00Z',
        priority: 'high',
        status: 'completed',
        confidence: 0.97,
        meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
        meeting_title: 'Tableau Crime Data Analytics & Lab Evaluation'
      },
      {
        id: 'act-2',
        description: 'Draft the Word doc report with question titles, analysis write-ups, and screenshots.',
        assignee: 'Ayush',
        due_date: '2026-08-24T12:30:00Z',
        priority: 'high',
        status: 'completed',
        confidence: 0.96,
        meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
        meeting_title: 'Tableau Crime Data Analytics & Lab Evaluation'
      },
      {
        id: 'act-3',
        description: 'Complete individual student peer evaluations and post-test feedback forms.',
        assignee: 'Sneha',
        due_date: '2026-08-24T13:00:00Z',
        priority: 'medium',
        status: 'in_progress',
        confidence: 0.91,
        meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
        meeting_title: 'Tableau Crime Data Analytics & Lab Evaluation'
      }
    ],
    topics: [
      { id: 'top-1', name: 'Tableau Data Ingestion & Merging', duration_seconds: 480, sentiment: 'neutral', relevance: 0.95 },
      { id: 'top-2', name: 'IPC vs SLL Cognizable Crime Trends', duration_seconds: 320, sentiment: 'neutral', relevance: 0.92 },
      { id: 'top-3', name: 'Stolen vs Recovered Property Deficits', duration_seconds: 290, sentiment: 'negative', relevance: 0.90 },
      { id: 'top-4', name: 'Crimes Against SC/ST & Foreign Visitors', duration_seconds: 240, sentiment: 'mixed', relevance: 0.88 },
      { id: 'top-5', name: 'Document Formatting & Submission', duration_seconds: 180, sentiment: 'positive', relevance: 0.85 }
    ],
    risks: [
      {
        id: 'risk-1',
        risk_text: 'Data portal token expiration and session timeouts blocking fresh downloads.',
        severity: 'high',
        mitigation_suggestion: 'Cache downloaded CSVs locally in structured project repository folders.',
        confidence: 0.93
      },
      {
        id: 'risk-2',
        risk_text: 'Tableau unrecognized geography for Union Territories (Andaman, Dadra & Nagar Haveli).',
        severity: 'medium',
        mitigation_suggestion: 'Switch to custom coordinate overrides or treemaps/bar charts for non-standard administrative divisions.',
        confidence: 0.89
      }
    ],
    speaker_segments: [
      {
        id: 'seg-101',
        speaker: 'Niti',
        speaker_id: 'spk_1',
        start_time: '00:01:05',
        end_time: '00:01:24',
        start_seconds: 65,
        end_seconds: 84,
        text: 'Tourism hi lena hai... actually Crime in India lete hain, usme questions easily ban jayenge aur categorical columns zyada hain.',
        confidence: 0.96,
        acoustic_confidence: 0.98,
        language_code: 'hi-en',
        language_label: 'Hinglish (Code-Switching)',
        has_overlap: false,
        needs_review: false,
        verified: true,
        words: [
          { word: 'Tourism', confidence: 0.98, start_ms: 65000, end_ms: 65600 },
          { word: 'hi', confidence: 0.99, start_ms: 65650, end_ms: 65800 },
          { word: 'lena', confidence: 0.97, start_ms: 65850, end_ms: 66200 },
          { word: 'hai...', confidence: 0.95, start_ms: 66250, end_ms: 66600 },
          { word: 'actually', confidence: 0.98, start_ms: 67100, end_ms: 67600 },
          { word: 'Crime', confidence: 0.99, start_ms: 67650, end_ms: 68000 },
          { word: 'in', confidence: 0.99, start_ms: 68050, end_ms: 68200 },
          { word: 'India', confidence: 0.98, start_ms: 68250, end_ms: 68700 },
          { word: 'lete', confidence: 0.96, start_ms: 68750, end_ms: 69100 },
          { word: 'hain,', confidence: 0.97, start_ms: 69150, end_ms: 69450 },
          { word: 'usme', confidence: 0.94, start_ms: 69800, end_ms: 70150 },
          { word: 'questions', confidence: 0.98, start_ms: 70200, end_ms: 70800 },
          { word: 'easily', confidence: 0.97, start_ms: 70850, end_ms: 71300 },
          { word: 'ban', confidence: 0.95, start_ms: 71350, end_ms: 71600 },
          { word: 'jayenge', confidence: 0.96, start_ms: 71650, end_ms: 72100 },
          { word: 'aur', confidence: 0.98, start_ms: 72150, end_ms: 72400 },
          { word: 'categorical', confidence: 0.94, start_ms: 72450, end_ms: 73200 },
          { word: 'columns', confidence: 0.96, start_ms: 73250, end_ms: 73700 },
          { word: 'zyada', confidence: 0.93, start_ms: 73750, end_ms: 74100 },
          { word: 'hain.', confidence: 0.97, start_ms: 74150, end_ms: 74450 }
        ]
      },
      {
        id: 'seg-102',
        speaker: 'Ayush',
        speaker_id: 'spk_2',
        start_time: '00:01:25',
        end_time: '00:01:42',
        start_seconds: 85,
        end_seconds: 102,
        text: 'Correct, IPC crime against women aur property theft statistics mein clear variance mil rahi hai across states.',
        confidence: 0.94,
        acoustic_confidence: 0.95,
        language_code: 'hi-en',
        language_label: 'Hinglish (Code-Switching)',
        has_overlap: false,
        needs_review: false,
        verified: true,
        words: [
          { word: 'Correct,', confidence: 0.98, start_ms: 85000, end_ms: 85500 },
          { word: 'IPC', confidence: 0.97, start_ms: 85600, end_ms: 86100 },
          { word: 'crime', confidence: 0.98, start_ms: 86150, end_ms: 86550 },
          { word: 'against', confidence: 0.96, start_ms: 86600, end_ms: 87000 },
          { word: 'women', confidence: 0.95, start_ms: 87050, end_ms: 87450 },
          { word: 'aur', confidence: 0.97, start_ms: 87500, end_ms: 87750 },
          { word: 'property', confidence: 0.96, start_ms: 87800, end_ms: 88300 },
          { word: 'theft', confidence: 0.95, start_ms: 88350, end_ms: 88750 },
          { word: 'statistics', confidence: 0.92, start_ms: 88800, end_ms: 89500 },
          { word: 'mein', confidence: 0.98, start_ms: 89550, end_ms: 89800 },
          { word: 'clear', confidence: 0.97, start_ms: 89850, end_ms: 90200 },
          { word: 'variance', confidence: 0.91, start_ms: 90250, end_ms: 90800 },
          { word: 'mil', confidence: 0.94, start_ms: 90850, end_ms: 91100 },
          { word: 'rahi', confidence: 0.96, start_ms: 91150, end_ms: 91400 },
          { word: 'hai', confidence: 0.97, start_ms: 91450, end_ms: 91700 },
          { word: 'across', confidence: 0.98, start_ms: 91750, end_ms: 92200 },
          { word: 'states.', confidence: 0.96, start_ms: 92250, end_ms: 92750 }
        ]
      },
      {
        id: 'seg-103',
        speaker: 'Sneha',
        speaker_id: 'spk_3',
        start_time: '00:03:10',
        end_time: '00:03:28',
        start_seconds: 190,
        end_seconds: 208,
        text: 'Wait, data portal se CSV download karte time session timeout ho gaya tha... check karo token valid hai ya nahi.',
        confidence: 0.82,
        acoustic_confidence: 0.80,
        language_code: 'hi-en',
        language_label: 'Hinglish (Code-Switching)',
        has_overlap: false,
        needs_review: false,
        verified: false,
        words: [
          { word: 'Wait,', confidence: 0.92, start_ms: 190000, end_ms: 190400 },
          { word: 'data', confidence: 0.95, start_ms: 190450, end_ms: 190800 },
          { word: 'portal', confidence: 0.88, start_ms: 190850, end_ms: 191300 },
          { word: 'se', confidence: 0.96, start_ms: 191350, end_ms: 191550 },
          { word: 'CSV', confidence: 0.84, start_ms: 191600, end_ms: 192100 },
          { word: 'download', confidence: 0.89, start_ms: 192150, end_ms: 192700 },
          { word: 'karte', confidence: 0.94, start_ms: 192750, end_ms: 193100 },
          { word: 'time', confidence: 0.92, start_ms: 193150, end_ms: 193450 },
          { word: 'session', confidence: 0.81, start_ms: 193500, end_ms: 193950 },
          { word: 'timeout', confidence: 0.76, start_ms: 194000, end_ms: 194550 },
          { word: 'ho', confidence: 0.89, start_ms: 194600, end_ms: 194800 },
          { word: 'gaya', confidence: 0.91, start_ms: 194850, end_ms: 195150 },
          { word: 'tha...', confidence: 0.85, start_ms: 195200, end_ms: 195600 },
          { word: 'check', confidence: 0.93, start_ms: 195900, end_ms: 196300 },
          { word: 'karo', confidence: 0.95, start_ms: 196350, end_ms: 196650 },
          { word: 'token', confidence: 0.71, start_ms: 196700, end_ms: 197150 },
          { word: 'valid', confidence: 0.84, start_ms: 197200, end_ms: 197600 },
          { word: 'hai', confidence: 0.96, start_ms: 197650, end_ms: 197900 },
          { word: 'ya', confidence: 0.97, start_ms: 197950, end_ms: 198150 },
          { word: 'nahi.', confidence: 0.95, start_ms: 198200, end_ms: 198600 }
        ]
      },
      {
        id: 'seg-104',
        speaker: 'Bhavya [Overlapping Speech]',
        speaker_id: 'spk_4',
        start_time: '00:04:45',
        end_time: '00:05:01',
        start_seconds: 285,
        end_seconds: 301,
        text: 'Maine manual refresh kiya... [unclear acoustic noise / crosstalk] Andaman aur Dadra Nagar Haveli match nahi ho rahe map pe.',
        confidence: 0.61,
        acoustic_confidence: 0.54,
        language_code: 'hi-en',
        language_label: 'Hinglish (Acoustic Interference)',
        has_overlap: true,
        needs_review: true,
        verified: false,
        words: [
          { word: 'Maine', confidence: 0.88, start_ms: 285000, end_ms: 285400 },
          { word: 'manual', confidence: 0.81, start_ms: 285450, end_ms: 285900 },
          { word: 'refresh', confidence: 0.78, start_ms: 285950, end_ms: 286450 },
          { word: 'kiya...', confidence: 0.82, start_ms: 286500, end_ms: 286900 },
          { word: '[unclear', confidence: 0.42, start_ms: 287200, end_ms: 287700 },
          { word: 'acoustic', confidence: 0.45, start_ms: 287750, end_ms: 288300 },
          { word: 'noise', confidence: 0.48, start_ms: 288350, end_ms: 288800 },
          { word: '/', confidence: 0.50, start_ms: 288850, end_ms: 289000 },
          { word: 'crosstalk]', confidence: 0.41, start_ms: 289050, end_ms: 289700 },
          { word: 'Andaman', confidence: 0.68, start_ms: 290100, end_ms: 290700 },
          { word: 'aur', confidence: 0.89, start_ms: 290750, end_ms: 291000 },
          { word: 'Dadra', confidence: 0.62, start_ms: 291050, end_ms: 291500 },
          { word: 'Nagar', confidence: 0.65, start_ms: 291550, end_ms: 291950 },
          { word: 'Haveli', confidence: 0.59, start_ms: 292000, end_ms: 292500 },
          { word: 'match', confidence: 0.74, start_ms: 292550, end_ms: 292950 },
          { word: 'nahi', confidence: 0.85, start_ms: 293000, end_ms: 293250 },
          { word: 'ho', confidence: 0.89, start_ms: 293300, end_ms: 293500 },
          { word: 'rahe', confidence: 0.84, start_ms: 293550, end_ms: 293850 },
          { word: 'map', confidence: 0.79, start_ms: 293900, end_ms: 294250 },
          { word: 'pe.', confidence: 0.88, start_ms: 294300, end_ms: 294600 }
        ]
      },
      {
        id: 'seg-105',
        speaker: 'Ayush',
        speaker_id: 'spk_2',
        start_time: '00:05:03',
        end_time: '00:05:22',
        start_seconds: 303,
        end_seconds: 322,
        text: 'Treemap ya Horizontal Bar chart use kar lo Union Territories ke liye, geographic boundaries ko override kar denge.',
        confidence: 0.95,
        acoustic_confidence: 0.97,
        language_code: 'hi-en',
        language_label: 'Hinglish (Code-Switching)',
        has_overlap: false,
        needs_review: false,
        verified: true,
        words: [
          { word: 'Treemap', confidence: 0.94, start_ms: 303000, end_ms: 303600 },
          { word: 'ya', confidence: 0.98, start_ms: 303650, end_ms: 303850 },
          { word: 'Horizontal', confidence: 0.96, start_ms: 303900, end_ms: 304550 },
          { word: 'Bar', confidence: 0.97, start_ms: 304600, end_ms: 304950 },
          { word: 'chart', confidence: 0.98, start_ms: 305000, end_ms: 305400 },
          { word: 'use', confidence: 0.99, start_ms: 305450, end_ms: 305750 },
          { word: 'kar', confidence: 0.97, start_ms: 305800, end_ms: 306050 },
          { word: 'lo', confidence: 0.98, start_ms: 306100, end_ms: 306350 },
          { word: 'Union', confidence: 0.95, start_ms: 306400, end_ms: 306800 },
          { word: 'Territories', confidence: 0.93, start_ms: 306850, end_ms: 307600 },
          { word: 'ke', confidence: 0.98, start_ms: 307650, end_ms: 307850 },
          { word: 'liye,', confidence: 0.97, start_ms: 307900, end_ms: 308250 },
          { word: 'geographic', confidence: 0.94, start_ms: 308600, end_ms: 309300 },
          { word: 'boundaries', confidence: 0.92, start_ms: 309350, end_ms: 310000 },
          { word: 'ko', confidence: 0.98, start_ms: 310050, end_ms: 310250 },
          { word: 'override', confidence: 0.95, start_ms: 310300, end_ms: 310900 },
          { word: 'kar', confidence: 0.97, start_ms: 310950, end_ms: 311200 },
          { word: 'denge.', confidence: 0.96, start_ms: 311250, end_ms: 311700 }
        ]
      },
      {
        id: 'seg-106',
        speaker: 'Instructor [Intercom]',
        speaker_id: 'spk_5',
        start_time: '00:08:15',
        end_time: '00:08:30',
        start_seconds: 495,
        end_seconds: 510,
        text: 'Attention all teams: [low bandwidth distortion] Lab submission portal closes at 12:30 sharp. Make sure individual reflections are attached.',
        confidence: 0.69,
        acoustic_confidence: 0.62,
        language_code: 'en',
        language_label: 'English (Low SNR / Intercom)',
        has_overlap: false,
        needs_review: true,
        verified: false,
        words: [
          { word: 'Attention', confidence: 0.85, start_ms: 495000, end_ms: 495600 },
          { word: 'all', confidence: 0.91, start_ms: 495650, end_ms: 495900 },
          { word: 'teams:', confidence: 0.88, start_ms: 495950, end_ms: 496450 },
          { word: '[low', confidence: 0.51, start_ms: 496700, end_ms: 497100 },
          { word: 'bandwidth', confidence: 0.49, start_ms: 497150, end_ms: 497750 },
          { word: 'distortion]', confidence: 0.52, start_ms: 497800, end_ms: 498450 },
          { word: 'Lab', confidence: 0.78, start_ms: 498700, end_ms: 499100 },
          { word: 'submission', confidence: 0.82, start_ms: 499150, end_ms: 499800 },
          { word: 'portal', confidence: 0.74, start_ms: 499850, end_ms: 500300 },
          { word: 'closes', confidence: 0.79, start_ms: 500350, end_ms: 500850 },
          { word: 'at', confidence: 0.86, start_ms: 500900, end_ms: 501100 },
          { word: '12:30', confidence: 0.72, start_ms: 501150, end_ms: 501800 },
          { word: 'sharp.', confidence: 0.81, start_ms: 501850, end_ms: 502350 },
          { word: 'Make', confidence: 0.87, start_ms: 502600, end_ms: 502950 },
          { word: 'sure', confidence: 0.89, start_ms: 503000, end_ms: 503350 },
          { word: 'individual', confidence: 0.76, start_ms: 503400, end_ms: 504100 },
          { word: 'reflections', confidence: 0.66, start_ms: 504150, end_ms: 504900 },
          { word: 'are', confidence: 0.85, start_ms: 504950, end_ms: 505200 },
          { word: 'attached.', confidence: 0.82, start_ms: 505250, end_ms: 505850 }
        ]
      },
      {
        id: 'seg-107',
        speaker: 'Sneha',
        speaker_id: 'spk_3',
        start_time: '00:09:40',
        end_time: '00:09:58',
        start_seconds: 580,
        end_seconds: 598,
        text: 'Got it. Main individual reflections compile kar rahi hoon, Niti aap screenshots final karo.',
        confidence: 0.97,
        acoustic_confidence: 0.98,
        language_code: 'hi-en',
        language_label: 'Hinglish (Code-Switching)',
        has_overlap: false,
        needs_review: false,
        verified: true,
        words: [
          { word: 'Got', confidence: 0.98, start_ms: 580000, end_ms: 580300 },
          { word: 'it.', confidence: 0.99, start_ms: 580350, end_ms: 580650 },
          { word: 'Main', confidence: 0.97, start_ms: 580900, end_ms: 581250 },
          { word: 'individual', confidence: 0.96, start_ms: 581300, end_ms: 581950 },
          { word: 'reflections', confidence: 0.95, start_ms: 582000, end_ms: 582750 },
          { word: 'compile', confidence: 0.96, start_ms: 582800, end_ms: 583350 },
          { word: 'kar', confidence: 0.98, start_ms: 583400, end_ms: 583650 },
          { word: 'rahi', confidence: 0.98, start_ms: 583700, end_ms: 584000 },
          { word: 'hoon,', confidence: 0.97, start_ms: 584050, end_ms: 584450 },
          { word: 'Niti', confidence: 0.98, start_ms: 584800, end_ms: 585200 },
          { word: 'aap', confidence: 0.99, start_ms: 585250, end_ms: 585500 },
          { word: 'screenshots', confidence: 0.96, start_ms: 585550, end_ms: 586300 },
          { word: 'final', confidence: 0.97, start_ms: 586350, end_ms: 586800 },
          { word: 'karo.', confidence: 0.98, start_ms: 586850, end_ms: 587300 }
        ]
      }
    ]
  }
};

export const INITIAL_KNOWLEDGE_OBJECTS: KnowledgeObject[] = [
  {
    id: 'ko-crime-in-india-2026',
    topic: 'Tableau Crime Analytics - State & Demographic Breakdown',
    content: 'Longitudinal analysis across Indian states between 2016-2018 demonstrated a divergence in crimes against vulnerable demographics, with Maharashtra and Delhi leading reported property theft while recovery rates hovered below 40%.',
    type: 'insight',
    version: 1,
    supersedes: null,
    superseded_by: null,
    entities: ['Tableau', 'Crime in India', 'IPC', 'SLL', 'SC/ST', 'Foreigners'],
    confidence: 0.96,
    meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
    created_at: '2026-08-24T11:47:00Z'
  },
  {
    id: 'ko-arch-vector-qdrant',
    topic: 'Vector DB Clustering and Memory Footprint',
    content: 'Qdrant collection sharding reduces P99 search latency from 140ms to 28ms when searching across 500,000+ meeting transcript chunk embeddings.',
    type: 'technical_spec',
    version: 2,
    supersedes: 'ko-arch-vector-qdrant-v1',
    superseded_by: null,
    entities: ['Qdrant', 'HNSW', 'Embeddings', 'PostgreSQL', 'P99'],
    confidence: 0.98,
    meeting_id: '2395857a-d35f-462d-b54c-d76cdb91f969',
    created_at: '2026-08-23T14:45:00Z'
  },
  {
    id: 'ko-rbac-enforcement',
    topic: 'Tenant Boundary Isolation Policy',
    content: 'All API routes strictly enforce tenant scoping where tenant_id is derived from cryptographically verified HS256 JWT claims. Cross-tenant queries return 403 Forbidden without exposing schema metadata.',
    type: 'policy',
    version: 1,
    supersedes: null,
    superseded_by: null,
    entities: ['HS256', 'JWT', 'RBAC', 'Multitenancy', 'HTTP 403'],
    confidence: 0.99,
    meeting_id: '2395857a-d35f-462d-b54c-d76cdb91f969',
    created_at: '2026-08-23T14:30:00Z'
  }
];

export const INITIAL_QUERIES: GroundedQuery[] = [
  {
    id: 'q-1',
    query_text: 'What were the main decisions and visualization types chosen for the crime data analysis?',
    answer_text: 'The team decided to analyze the "Crime in India" dataset instead of Tourism. They built 10 visualizations divided into 3 dashboards: 1) Trends over time (Line charts), 2) Regional stolen vs. recovered property (Side-by-side bars), and 3) Demographic safety for SC/ST and Foreigners (Treemaps and dual-axis line/bar charts).',
    confidence: 0.96,
    status: 'grounded',
    citations: [
      {
        meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
        meeting_title: 'Tableau Crime Data Analytics & Lab Evaluation',
        timestamp: '00:01:05',
        speaker: 'Niti',
        snippet: 'Tourism hi lena hai... actually Crime in India lete hain questions easily ban jayenge.'
      },
      {
        meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
        meeting_title: 'Tableau Crime Data Analytics & Lab Evaluation',
        timestamp: '00:24:08',
        speaker: 'Ayush',
        snippet: 'Hamara first question hai Analysis of various categorical crime over time, isme bar chart lines wala use kar sakte hain.'
      }
    ],
    created_at: '2026-08-24T11:47:30Z',
    meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142'
  }
];

export const INITIAL_TRANSLATIONS: TranslationItem[] = [
  {
    id: 'tr-es-1',
    meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
    language_code: 'es',
    language_name: 'Spanish (Español)',
    translated_summary: 'El equipo completó con éxito el laboratorio de Tableau sobre estadísticas criminales en India. Crearon 10 gráficos y 3 paneles temáticos para delitos de IPC/SLL y robo de propiedades.',
    translated_decisions: [
      'Seleccionar el conjunto de datos sobre criminalidad en India en lugar de turismo.',
      'Estructurar las visualizaciones en 3 hojas de tendencias y 3 hojas regionales.'
    ],
    translated_action_items: [
      'Exportar todas las hojas de trabajo a formato PNG de alta resolución.',
      'Redactar el informe de laboratorio en Word con capturas de pantalla.'
    ],
    created_at: '2026-08-24T11:47:15Z'
  },
  {
    id: 'tr-fr-1',
    meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
    language_code: 'fr',
    language_name: 'French (Français)',
    translated_summary: 'L’équipe a mené à bien l’atelier pratique sur les statistiques de criminalité en Inde à l’aide de Tableau, en développant 10 visualisations structurées en 3 tableaux de bord interactifs.',
    translated_decisions: [
      'Choisir les données sur la criminalité en Inde plutôt que sur le tourisme.',
      'Organiser les visualisations en 3 vues de tendances et 3 vues régionales.'
    ],
    translated_action_items: [
      'Exporter toutes les feuilles Tableau au format PNG.',
      'Rédiger le rapport complet sous Microsoft Word.'
    ],
    created_at: '2026-08-24T11:47:18Z'
  },
  {
    id: 'tr-ja-1',
    meeting_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
    language_code: 'ja',
    language_name: 'Japanese (日本語)',
    translated_summary: '学生チームはTableauを用いてインドの犯罪統計データを分析し、10種類のグラフと3つのダッシュボードおよびストーリーボードを作成しました。',
    translated_decisions: [
      '観光データではなく犯罪統計データを選択。',
      'トレンド3枚と地域別3枚のシート構成を採用。'
    ],
    translated_action_items: [
      'Tableauワークシートのスクリーンショットを高画質で出力。',
      'Wordレポートの作成とピア評価フォームへの回答。'
    ],
    created_at: '2026-08-24T11:47:22Z'
  }
];

export const INITIAL_NOTIFICATIONS: NotificationItem[] = [
  {
    id: 'notif-1',
    event_type: 'meeting.processed',
    title: 'Meeting Ingestion Complete',
    message: 'Tableau Crime Data Analytics session has finished ACE Blackboard processing with confidence score 0.94.',
    read: false,
    created_at: '2026-08-24T11:47:00Z'
  },
  {
    id: 'notif-2',
    event_type: 'action_item.assigned',
    title: 'Action Item Assigned',
    message: 'Ayush was assigned to compile the final Word report with embedded screenshots.',
    read: false,
    created_at: '2026-08-24T11:47:05Z'
  },
  {
    id: 'notif-3',
    event_type: 'security.alert',
    title: 'Audit Verification Logged',
    message: 'SHA-256 integrity check validated for audio recording chunk stream #344.',
    read: true,
    created_at: '2026-08-24T11:41:30Z'
  }
];

export const INITIAL_AUDIT_LOGS: AuditLogItem[] = [
  {
    id: 'aud-101',
    timestamp: '2026-08-24T11:47:30Z',
    user_id: '00000000-0000-0000-0000-000000000001',
    user_email: 'swapniljee5205@gmail.com',
    action: 'QUERY_INTERFACE_EXECUTE',
    resource_type: 'meeting_query',
    resource_id: 'q-1',
    ip_address: '10.0.4.12',
    status: 'SUCCESS',
    sanitized_payload: '{"query": "What were the main decisions?", "tenant_id": "default-tenant", "auth_token": "[REDACTED]"}'
  },
  {
    id: 'aud-102',
    timestamp: '2026-08-24T11:47:00Z',
    user_id: '00000000-0000-0000-0000-000000000001',
    user_email: 'swapniljee5205@gmail.com',
    action: 'PIPELINE_ORCHESTRATION_TRIGGER',
    resource_type: 'meeting',
    resource_id: '7a4cb6f8-2c52-4023-ad32-53b9a3bad142',
    ip_address: '10.0.4.12',
    status: 'SUCCESS',
    sanitized_payload: '{"action": "ace_blackboard_trigger", "mode": "batch", "jwt_signature": "[REDACTED]"}'
  },
  {
    id: 'aud-103',
    timestamp: '2026-08-24T11:41:10Z',
    user_id: '00000000-0000-0000-0000-000000000001',
    user_email: 'swapniljee5205@gmail.com',
    action: 'AUDIO_PAYLOAD_UPLOAD',
    resource_type: 'audio_file',
    resource_id: 'de23aad1-14df-4715-85e1-94efc163be54',
    ip_address: '10.0.4.12',
    status: 'SUCCESS',
    sanitized_payload: '{"file_name": "7a0285d2-b532-4912-80cf-67383a71a770_sample_meeting.wav", "size_bytes": 64044}'
  },
  {
    id: 'aud-104',
    timestamp: '2026-08-24T10:15:00Z',
    user_id: 'unknown-intruder',
    user_email: 'hacker@unauthorized-domain.com',
    action: 'CROSS_TENANT_READ_ATTEMPT',
    resource_type: 'knowledge_object',
    resource_id: 'ko-arch-vector-qdrant',
    ip_address: '198.51.100.77',
    status: 'DENIED',
    sanitized_payload: '{"error": "HTTP 403 Forbidden: Cross-tenant boundary access violation", "provided_secret": "[REDACTED]"}'
  }
];

export const ALL_API_ENDPOINTS: EndpointDef[] = [
  // Health
  { method: 'GET', path: '/api/v1/health/liveness', category: 'Health', description: 'Application liveness probe for orchestrators', rbac: 'Public', phase: 'Phase 1' },
  { method: 'GET', path: '/api/v1/health/readiness', category: 'Health', description: 'Postgres, Redis, and Qdrant readiness matrix', rbac: 'Public', phase: 'Phase 1' },
  { method: 'GET', path: '/api/v1/health/system', category: 'Health', description: 'Comprehensive diagnostic component matrix', rbac: 'Public', phase: 'Phase 1' },
  // Auth
  { method: 'POST', path: '/api/v1/auth/login', category: 'Authentication', description: 'Authenticate user & issue HS256 cryptographic JWT', rbac: 'Public', phase: 'Phase 4.25', sampleBody: '{\n  "email": "user@abci-mi.org",\n  "password": "SecurePassword123!"\n}' },
  { method: 'GET', path: '/api/v1/auth/me', category: 'Authentication', description: 'Retrieve authenticated claims and organization profile', rbac: 'Authenticated', phase: 'Phase 4.25' },
  // Meetings
  { method: 'GET', path: '/api/v1/meetings', category: 'Meetings', description: 'List workspace meetings with status & pagination', rbac: 'Member+', phase: 'Phase 2' },
  { method: 'POST', path: '/api/v1/meetings', category: 'Meetings', description: 'Create and initialize a new meeting room', rbac: 'Host+', phase: 'Phase 2', sampleBody: '{\n  "title": "Quarterly Technical Review",\n  "description": "Cross-functional pipeline sync",\n  "language": "en",\n  "duration_minutes": 60\n}' },
  { method: 'GET', path: '/api/v1/meetings/{id}', category: 'Meetings', description: 'Fetch meeting details and participants', rbac: 'Member+', phase: 'Phase 2' },
  { method: 'PATCH', path: '/api/v1/meetings/{id}', category: 'Meetings', description: 'Update meeting metadata or lifecycle status', rbac: 'Host+', phase: 'Phase 2', sampleBody: '{\n  "status": "completed"\n}' },
  { method: 'POST', path: '/api/v1/meetings/{id}/audio', category: 'Meetings', description: 'Upload audio file for asynchronous pipeline processing (up to 500MB)', rbac: 'Host+', phase: 'Phase 2' },
  { method: 'POST', path: '/api/v1/meetings/{id}/process', category: 'Meetings', description: 'Trigger full ASR, Blackboard, and SKW pipeline', rbac: 'Host+', phase: 'Phase 2' },
  // Live Streaming
  { method: 'POST', path: '/api/v1/meetings/{id}/live/session', category: 'Live Streaming', description: 'Initialize or resume real-time streaming session', rbac: 'Host+', phase: 'Phase 4.17', sampleBody: '{\n  "sample_rate": 16000,\n  "channels": 1,\n  "codec": "pcm_s16le"\n}' },
  { method: 'POST', path: '/api/v1/meetings/{id}/live/chunks', category: 'Live Streaming', description: 'Ingest sequenced audio chunk with SHA-256 validation', rbac: 'Host+', phase: 'Phase 4.17', sampleBody: '{\n  "sequence_number": 1,\n  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",\n  "chunk_base64": "UklGRi..."\n}' },
  { method: 'POST', path: '/api/v1/meetings/{id}/live/pause', category: 'Live Streaming', description: 'Pause live ingestion stream', rbac: 'Host+', phase: 'Phase 4.17' },
  { method: 'POST', path: '/api/v1/meetings/{id}/live/resume', category: 'Live Streaming', description: 'Resume paused audio ingestion stream', rbac: 'Host+', phase: 'Phase 4.17' },
  { method: 'POST', path: '/api/v1/meetings/{id}/live/complete', category: 'Live Streaming', description: 'Finalize live stream and trigger synthesis', rbac: 'Host+', phase: 'Phase 4.17' },
  // Meeting Intelligence
  { method: 'GET', path: '/api/v1/meetings/{id}/intelligence/summary', category: 'Intelligence', description: 'Retrieve executive summary & key takeaways', rbac: 'Member+', phase: 'Phase 4.22' },
  { method: 'GET', path: '/api/v1/meetings/{id}/intelligence/decisions', category: 'Intelligence', description: 'List formal decisions with consensus levels', rbac: 'Member+', phase: 'Phase 4.22' },
  { method: 'GET', path: '/api/v1/meetings/{id}/intelligence/action-items', category: 'Intelligence', description: 'List action items, assignees, and deadlines', rbac: 'Member+', phase: 'Phase 4.22' },
  { method: 'GET', path: '/api/v1/meetings/{id}/intelligence/topics', category: 'Intelligence', description: 'List discussed topics and sentiment trends', rbac: 'Member+', phase: 'Phase 4.22' },
  { method: 'GET', path: '/api/v1/meetings/{id}/intelligence/risks', category: 'Intelligence', description: 'Retrieve flagged operational & technical risks', rbac: 'Member+', phase: 'Phase 4.22' },
  // Action Items
  { method: 'GET', path: '/api/v1/action-items', category: 'Action Items', description: 'Query action items across tenant meetings', rbac: 'Member+', phase: 'Phase 4.22' },
  { method: 'PATCH', path: '/api/v1/action-items/{id}', category: 'Action Items', description: 'Update assignee, verification, or completion status', rbac: 'Member+', phase: 'Phase 4.22', sampleBody: '{\n  "status": "completed"\n}' },
  // Knowledge (SKW)
  { method: 'GET', path: '/api/v1/knowledge/search', category: 'Knowledge (SKW)', description: 'Semantic and hybrid search over Knowledge Objects', rbac: 'Member+', phase: 'Phase 4' },
  { method: 'GET', path: '/api/v1/knowledge/objects/{id}', category: 'Knowledge (SKW)', description: 'Retrieve canonical Knowledge Object with version lineage', rbac: 'Member+', phase: 'Phase 4' },
  { method: 'GET', path: '/api/v1/knowledge/objects/{id}/lineage', category: 'Knowledge (SKW)', description: 'Audit revision history and supersession trace', rbac: 'Member+', phase: 'Phase 4' },
  // Ask ABCI-MI (Query Interface)
  { method: 'POST', path: '/api/v1/queries', category: 'Ask ABCI-MI', description: 'Grounded natural language Q&A with citations', rbac: 'Member+', phase: 'Phase 4.23', sampleBody: '{\n  "query": "What were the key decisions made in the Tableau lab?",\n  "meeting_id": "7a4cb6f8-2c52-4023-ad32-53b9a3bad142"\n}' },
  { method: 'GET', path: '/api/v1/queries', category: 'Ask ABCI-MI', description: 'Query history with start_time & end_time date filters', rbac: 'Member+', phase: 'Phase 4.23' },
  { method: 'GET', path: '/api/v1/queries/{id}', category: 'Ask ABCI-MI', description: 'Retrieve query answer, citations, and confidence', rbac: 'Member+', phase: 'Phase 4.23' },
  // Translations
  { method: 'POST', path: '/api/v1/translations', category: 'Translations', description: 'Request multilingual translation across 17 locales', rbac: 'Member+', phase: 'Phase 4.20', sampleBody: '{\n  "meeting_id": "7a4cb6f8-2c52-4023-ad32-53b9a3bad142",\n  "target_language": "es"\n}' },
  { method: 'GET', path: '/api/v1/meetings/{id}/translations', category: 'Translations', description: 'List derived translations for meeting', rbac: 'Member+', phase: 'Phase 4.20' },
  // Reports
  { method: 'POST', path: '/api/v1/reports', category: 'Reports & Export', description: 'Generate comprehensive meeting report', rbac: 'Member+', phase: 'Phase 4.19', sampleBody: '{\n  "meeting_id": "7a4cb6f8-2c52-4023-ad32-53b9a3bad142",\n  "format": "markdown"\n}' },
  { method: 'POST', path: '/api/v1/reports/domain/{domain}/{usecase}', category: 'Reports & Export', description: 'Generate specialized domain report (Business, Education, Healthcare, Legal, Support, Research)', rbac: 'Member+', phase: 'Phase 4.19', sampleBody: '{\n  "meeting_id": "7a4cb6f8-2c52-4023-ad32-53b9a3bad142",\n  "domain": "healthcare",\n  "usecase": "health_doctor_patient",\n  "format": "markdown",\n  "redaction_level": "strict",\n  "include_timestamps": true\n}' },
  { method: 'GET', path: '/api/v1/reports/templates/domains', category: 'Reports & Export', description: 'List available domain report templates & compliance standards', rbac: 'Public', phase: 'Phase 4.19' },
  { method: 'GET', path: '/api/v1/reports/{id}/download', category: 'Reports & Export', description: 'Download report in PDF 1.4, Markdown, JSON, HTML, or TXT', rbac: 'Member+', phase: 'Phase 4.19' },
  // Notifications
  { method: 'GET', path: '/api/v1/notifications', category: 'Notifications', description: 'List real-time notification events with unread count', rbac: 'Authenticated', phase: 'Phase 4.24' },
  { method: 'PATCH', path: '/api/v1/notifications/{id}/read', category: 'Notifications', description: 'Mark single notification as read', rbac: 'Authenticated', phase: 'Phase 4.24' },
  { method: 'POST', path: '/api/v1/notifications/mark-all-read', category: 'Notifications', description: 'Batch mark all tenant notifications as read', rbac: 'Authenticated', phase: 'Phase 4.24' },
  // Admin & Security
  { method: 'GET', path: '/api/v1/admin/users', category: 'Admin & Audit', description: 'List organization users and assign RBAC roles', rbac: 'Admin', phase: 'Phase 4.25' },
  { method: 'GET', path: '/api/v1/admin/audit-logs', category: 'Admin & Audit', description: 'Search immutable audit logs with secret redaction', rbac: 'Security Officer+', phase: 'Phase 4.25' },
  { method: 'GET', path: '/api/v1/admin/access-denials', category: 'Admin & Audit', description: 'View security access-denial telemetry & tenant violations', rbac: 'Security Officer+', phase: 'Phase 4.25' },
  { method: 'GET', path: '/api/v1/admin/security/summary', category: 'Admin & Audit', description: 'Real-time security posture scorecard & incident metrics', rbac: 'Security Officer+', phase: 'Phase 4.25' },
];
