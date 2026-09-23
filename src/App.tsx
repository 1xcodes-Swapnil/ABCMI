import React, { useState, useEffect } from 'react';
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
import {
  INITIAL_MEETINGS,
  INITIAL_INTELLIGENCE,
  INITIAL_KNOWLEDGE_OBJECTS,
  INITIAL_QUERIES,
  INITIAL_TRANSLATIONS,
  INITIAL_NOTIFICATIONS,
  INITIAL_AUDIT_LOGS,
  ALL_API_ENDPOINTS
} from './data/mockData';
import { Header } from './components/Header';
import { SystemStatusBar } from './components/SystemStatusBar';
import { CommandPalette } from './components/CommandPalette';
import { MeetingsTester } from './components/MeetingsTester';
import { LiveStreamTester } from './components/LiveStreamTester';
import { IntelligenceViewer } from './components/IntelligenceViewer';
import { QueryTester } from './components/QueryTester';
import { KnowledgeTester } from './components/KnowledgeTester';
import { TranslationTester } from './components/TranslationTester';
import { ReportTester } from './components/ReportTester';
import { AdminAuditTester } from './components/AdminAuditTester';
import { ApiConsoleTester } from './components/ApiConsoleTester';
import { ResearchBenchmarkViewer } from './components/ResearchBenchmarkViewer';
import { SystemHealthDashboard } from './components/SystemHealthDashboard';

export default function App() {
  // State Management
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [activeTab, setActiveTab] = useState<
    'meetings' | 'live_stream' | 'intelligence' | 'queries' | 'knowledge' | 'translations' | 'reports' | 'benchmarks' | 'security' | 'api_console' | 'system_health'
  >('meetings');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);

  const [auth, setAuth] = useState<AuthContext>({
    token: 'jwt-hs256-mock-token-sample',
    user_id: '00000000-0000-0000-0000-000000000001',
    user_name: 'Swapnil Jee',
    user_email: 'swapniljee5205@gmail.com',
    role: 'admin',
    tenant_id: 'default-tenant'
  });

  const [meetings, setMeetings] = useState<MeetingItem[]>(INITIAL_MEETINGS);
  const [selectedMeetingId, setSelectedMeetingId] = useState<string>(INITIAL_MEETINGS[0].id);
  const [intelligenceMap, setIntelligenceMap] = useState<Record<string, MeetingIntelligence>>(INITIAL_INTELLIGENCE);
  const [knowledgeObjects, setKnowledgeObjects] = useState<KnowledgeObject[]>(INITIAL_KNOWLEDGE_OBJECTS);
  const [queries, setQueries] = useState<GroundedQuery[]>(INITIAL_QUERIES);
  const [translations, setTranslations] = useState<TranslationItem[]>(INITIAL_TRANSLATIONS);
  const [notifications, setNotifications] = useState<NotificationItem[]>(INITIAL_NOTIFICATIONS);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>(INITIAL_AUDIT_LOGS);
  const [showNotificationsModal, setShowNotificationsModal] = useState(false);

  const selectedMeeting = meetings.find(m => m.id === selectedMeetingId) || meetings[0];
  const activeIntelligence = intelligenceMap[selectedMeetingId];

  // Global Keyboard shortcut for Command Palette
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Helper: Append Audit Log
  const addAuditLog = (
    action: string,
    resourceType: string,
    resourceId: string,
    status: 'SUCCESS' | 'FAILED' | 'DENIED',
    metadata?: string
  ) => {
    const newLog: AuditLogItem = {
      id: `log-${Date.now().toString(36)}`,
      timestamp: new Date().toISOString(),
      user_id: auth.user_id,
      user_email: auth.user_email,
      action,
      resource_type: resourceType,
      resource_id: resourceId,
      status,
      ip_address: '127.0.0.1',
      sanitized_payload: metadata || '{}'
    };
    setAuditLogs(prev => [newLog, ...prev]);
  };

  // Handler: Create Meeting
  const handleCreateMeeting = (
    title: string,
    description: string,
    language: string,
    details?: {
      category?: string;
      tags?: string[];
      participants?: string[];
      duration_minutes?: number;
      scheduled_start?: string;
      audio_file?: File;
      auto_process?: boolean;
    }
  ) => {
    const newId = `meet-${Math.random().toString(36).substring(2, 9)}-${Date.now().toString(36)}`;
    const hasAudio = !!details?.audio_file;
    const newMeeting: MeetingItem = {
      id: newId,
      title,
      description,
      status: 'created',
      primary_language: language,
      category: details?.category || 'Architecture & Engineering',
      tags: details?.tags || ['Multilingual', 'Open-MOSS'],
      scheduled_start: details?.scheduled_start || new Date().toISOString(),
      duration_minutes: details?.duration_minutes || (hasAudio ? 45 : 30),
      audio_uploaded: hasAudio,
      audio_file_name: details?.audio_file?.name,
      audio_file_size_mb: details?.audio_file
        ? parseFloat((details.audio_file.size / (1024 * 1024)).toFixed(2))
        : undefined,
      participants:
        details?.participants && details.participants.length > 0
          ? details.participants
          : [auth.user_name, 'Dr. Aris (Audio Lead)', 'Kiran (ML Ops)'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    };

    setMeetings(prev => [newMeeting, ...prev]);
    setSelectedMeetingId(newId);
    addAuditLog('MEETING_CREATE', 'meeting', newId, 'SUCCESS', JSON.stringify({ title, language, has_audio: hasAudio }));

    if (details?.auto_process && hasAudio) {
      setTimeout(() => {
        handleProcessMeeting(newId);
      }, 400);
    }
  };

  // Handler: Upload Audio
  const handleUploadAudio = (meetingId: string, file: File) => {
    setMeetings(prev =>
      prev.map(m =>
        m.id === meetingId
          ? {
              ...m,
              audio_uploaded: true,
              audio_file_name: file.name,
              audio_file_size_mb: parseFloat((file.size / (1024 * 1024)).toFixed(2)),
              status: 'created'
            }
          : m
      )
    );

    addAuditLog('AUDIO_PAYLOAD_UPLOAD', 'audio_file', meetingId, 'SUCCESS', JSON.stringify({ filename: file.name, size: file.size }));
  };

  // Handler: Trigger ACE Pipeline Processing
  const handleProcessMeeting = (meetingId: string) => {
    setMeetings(prev =>
      prev.map(m => (m.id === meetingId ? { ...m, status: 'processing' } : m))
    );

    setTimeout(() => {
      setMeetings(prev =>
        prev.map(m => (m.id === meetingId ? { ...m, status: 'completed' } : m))
      );

      const targetMeeting = meetings.find(m => m.id === meetingId);
      const generatedIntel: MeetingIntelligence = {
        meeting_id: meetingId,
        executive_summary: `Executive summary for "${targetMeeting?.title}": Multi-agent synthesis completed across Open-MOSS acoustic diarization, speaker attribution, and semantic entity linking.`,
        key_takeaways: [
          'High-confidence speaker diarization achieved via Open-MOSS primary engine.',
          'Action item assignments verified with assigned deadlines and owners.',
          'Cross-meeting canonical Knowledge Objects indexed into vector warehouse.'
        ],
        confidence_score: 0.95,
        decisions: [
          {
            id: `dec-${Date.now()}`,
            decision_text: `Approved technical decisions and action path for ${targetMeeting?.title}.`,
            decision_maker: auth.user_name,
            consensus_level: 'unanimous',
            confidence: 0.97,
            timestamp_offset: 120,
            verification_status: 'verified'
          }
        ],
        action_items: [
          {
            id: `act-${Date.now()}`,
            description: `Execute post-meeting action deliverables for ${targetMeeting?.title}.`,
            assignee: auth.user_name,
            due_date: new Date(Date.now() + 86400000 * 2).toISOString(),
            priority: 'high',
            status: 'pending',
            confidence: 0.95,
            meeting_id: meetingId,
            meeting_title: targetMeeting?.title
          }
        ],
        topics: [
          { id: `top-1`, name: 'Execution & Pipeline Alignment', duration_seconds: 300, sentiment: 'positive', relevance: 0.94 }
        ],
        risks: [
          { id: `risk-1`, risk_text: 'Timeline dependencies on third-party deliverables.', severity: 'medium', mitigation_suggestion: 'Establish milestone checkpoint.', confidence: 0.9 }
        ]
      };

      setIntelligenceMap(prev => ({ ...prev, [meetingId]: generatedIntel }));

      // Add Notification
      setNotifications(prev => [
        {
          id: `notif-${Date.now()}`,
          event_type: 'meeting.processed',
          title: 'Processing Complete',
          message: `ACE Blackboard synthesis finished for ${targetMeeting?.title}.`,
          read: false,
          created_at: new Date().toISOString()
        },
        ...prev
      ]);

      addAuditLog('PIPELINE_ORCHESTRATION_TRIGGER', 'meeting', meetingId, 'SUCCESS', '{"mode": "batch", "status": "completed"}');
    }, 1500);
  };

  // Handler: Run Grounded Query
  const handleRunQuery = (queryText: string, meetingId?: string) => {
    const newQuery: GroundedQuery = {
      id: `q-${Date.now().toString(36)}`,
      query_text: queryText,
      answer_text: `Based on authorized meeting transcripts and canonical knowledge objects, the analysis reveals that "${queryText.replace('?', '')}" was verified with high multi-agent consensus across the ACE Blackboard.`,
      confidence: 0.95,
      status: 'grounded',
      citations: [
        {
          meeting_id: meetingId || selectedMeeting.id,
          meeting_title: selectedMeeting.title,
          timestamp: '00:15:20',
          speaker: selectedMeeting.participants[0] || 'Lead Speaker',
          snippet: `Regarding "${queryText.substring(0, 40)}...", the decision was finalized with full consensus.`
        }
      ],
      created_at: new Date().toISOString(),
      meeting_id: meetingId
    };

    setQueries([newQuery, ...queries]);
    addAuditLog('QUERY_INTERFACE_EXECUTE', 'meeting_query', newQuery.id, 'SUCCESS', JSON.stringify({ query: queryText }));
  };

  // Handler: Request Translation
  const handleRequestTranslation = (meetingId: string, langCode: string) => {
    const localeLookup: Record<string, {
      name: string;
      summary: string;
      decisions: string[];
      actions: string[];
    }> = {
      hi: {
        name: 'Hindi (हिन्दी)',
        summary: 'टीम ने अपराध सांख्यिकी पर झांकी बनाई और 10 चार्ट्स के साथ 3 डैशबोर्ड सफलतापूर्वक तैयार किए।',
        decisions: ['पर्यटन के बजाय अपराध डेटासेट का चयन किया गया।', '3 प्रवृत्ति पत्रक और 3 क्षेत्रीय दृश्य बनाने का निर्णय लिया गया।'],
        actions: ['सभी वर्कशीट्स को उच्च रिज़ॉल्यूशन PNG में निर्यात करें।', 'वर्ड रिपोर्ट तैयार करें।']
      },
      ta: {
        name: 'Tamil (தமிழ்)',
        summary: 'குழு டாப்ளோ ஆய்வகத்தில் குற்றப் புள்ளிவிவரத் தரவுகளை வெற்றிகரமாக ஆய்வு செய்து 10 விளக்கப்படங்களை உருவாக்கியது.',
        decisions: ['சுற்றுலா தரவுகளுக்கு பதிலாக குற்றப் புள்ளிவிவரங்களைத் தேர்வு செய்தல்.', '3 போக்குத் தாள்கள் மற்றும் 3 பிராந்திய தாள்கள் கட்டமைப்பு.'],
        actions: ['அனைத்து பணித்தாள்களையும் உயர் தெளிவுத்திறன் கொண்ட PNG வடிவத்தில் ஏற்றுமதி செய்க.', 'Word அறிக்கையை தொகுக்க.']
      },
      te: {
        name: 'Telugu (తెలుగు)',
        summary: 'బృందం టాబ్లో ల్యాబ్‌లో నేర గణాంకాల డేటాను విజయవంతంగా విశ్లేషించి 10 చార్ట్‌లను రూపొందించింది.',
        decisions: ['పర్యాటక డేటాకు బదులుగా నేరాల డేటాసెట్‌ను ఎంచుకోవాలని నిర్ణయించారు.', '3 ట్రెండ్ షీట్లు మరియు 3 ప్రాంతీయ షీట్లను రూపొందించడం.'],
        actions: ['అన్ని వర్క్‌షీట్‌లను అధిక రిజల్యూషన్ PNG గా ఎగుమతి చేయండి.', 'తుది వర్డ్ నివేదికను రూపొందించండి.']
      },
      kn: {
        name: 'Kannada (ಕನ್ನಡ)',
        summary: 'ತಂಡವು ಅಪರಾಧ ಅಂಕಿಅಂಶಗಳ ಕುರಿತು ಟ್ಯಾಬ್ಲೋ ಲ್ಯಾಬ್ ಅನ್ನು ಯಶಸ್ವಿಯಾಗಿ ಪೂರ್ಣಗೊಳಿಸಿತು ಮತ್ತು 10 ಚಾರ್ಟ್‌ಗಳನ್ನು ರಚಿಸಿತು.',
        decisions: ['ಪ್ರವಾಸೋದ್ಯಮದ ಬದಲಿಗೆ ಅಪರಾಧ ಡೇಟಾಸೆಟ್ ಆಯ್ಕೆ.', '3 ಪ್ರವೃತ್ತಿ ಹಾಳೆಗಳು ಮತ್ತು 3 ಪ್ರಾದೇಶಿಕ ಹಾಳೆಗಳ ರಚನೆ.'],
        actions: ['ಎಲ್ಲಾ ವರ್ಕ್‌ಶೀಟ್‌ಗಳನ್ನು PNG ರೂಪದಲ್ಲಿ ರಫ್ತು ಮಾಡಿ.', 'ವರದಿಯನ್ನು ಸಿದ್ಧಪಡಿಸಿ.']
      },
      ml: {
        name: 'Malayalam (മലയാളം)',
        summary: 'ക്രൈം സ്റ്റാറ്റിസ്റ്റിക്സ് ഡാറ്റ വിശകലനം ചെയ്ത് ടീം 10 ചാർട്ടുകളും 3 ഡാഷ്‌ബോർഡുകളും വിജയകരമായി സൃഷ്ടിച്ചു.',
        decisions: ['ടൂറിസത്തിന് പകരം കുറ്റകൃത്യ ഡാറ്റാസെറ്റ് തിരഞ്ഞെടുക്കാൻ തീരുമാനിച്ചു.', '3 ട്രെൻഡ് ഷീറ്റുകളും 3 റീജിയണൽ ഷീറ്റുകളും ക്രമീകരിക്കുക.'],
        actions: ['എല്ലാ വർക്ക്ഷീറ്റുകളും ഉയർന്ന റെസല്യൂഷൻ PNG ആയി എക്സ്പോർട്ട് ചെയ്യുക.', 'റിപ്പോർട്ട് തയ്യാറാക്കുക.']
      },
      bn: {
        name: 'Bengali (বাংলা)',
        summary: 'দলটি অপরাধ পরিসংখ্যানের উপর ট্যাবলো ল্যাব সফলভাবে সম্পন্ন করেছে এবং ১০টি চার্ট তৈরি করেছে।',
        decisions: ['পর্যটনের পরিবর্তে অপরাধ ডেটাসেট নির্বাচন করার সিদ্ধান্ত গৃহীত হয়েছে।', '৩টি প্রবণতা পত্রক এবং ৩টি আঞ্চলিক দৃশ্য তৈরি করা।'],
        actions: ['সমস্ত ওয়ার্কশীট উচ্চ রেজোলিউশনের PNG ফরম্যাটে রপ্তানি করুন।', 'ওয়ার্ড রিপোর্ট প্রস্তুত করুন।']
      },
      mr: {
        name: 'Marathi (मराठी)',
        summary: 'संघाने टॅब्लो लॅबमध्ये गुन्हेगारी आकडेवारीचे यशस्वी विश्लेषण केले आणि १० तक्ते तयार केले.',
        decisions: ['पर्यटनाऐवजी गुन्हेगारी डेटासेट निवडण्याचा सर्वसंमतीने निर्णय.', '३ ट्रेंड शीट्स आणि ३ प्रादेशिक व्ह्यूज तयार करणे.'],
        actions: ['सर्व वर्कशीट उच्च रिझोल्यूशन PNG मध्ये निर्यात करा.', 'अहवाल तयार करा.']
      },
      gu: {
        name: 'Gujarati (ગુજરાતી)',
        summary: 'ટીમે ક્રાઈમ સ્ટેટિસ્ટિક્સ ડેટા પર ટેબ્લો લેબ સફળતાપૂર્વક પૂર્ણ કરી અને 10 ચાર્ટ્સ બનાવ્યા.',
        decisions: ['પ્રવાસન ડેટાને બદલે ક્રાઈમ ડેટાસેટ પસંદ કરવાનો નિર્ણય.', '3 ટ્રેન્ડ શીટ્સ અને 3 પ્રાદેશિક વ્યુઝ તૈયાર કરવા.'],
        actions: ['બધી વર્કશીટ્સને હાઈ રિઝોલ્યુશન PNG માં એક્સપોર્ટ કરો.', 'અહેવાલ તૈયાર કરો.']
      },
      pa: {
        name: 'Punjabi (ਪੰਜਾਬੀ)',
        summary: 'ਟੀਮ ਨੇ ਜੁਰਮ ਅੰਕੜਿਆਂ ਤੇ ਟੈਬਲੋ ਲੈਬ ਨੂੰ ਸਫਲਤਾਪੂਰਵਕ ਪੂਰਾ ਕੀਤਾ ਅਤੇ 10 ਚਾਰਟ ਬਣਾਏ।',
        decisions: ['ਸੈਰ-ਸਪਾਟੇ ਦੀ ਬਜਾਏ ਜੁਰਮ ਡੇਟਾਸੈਟ ਦੀ ਚੋਣ ਕੀਤੀ ਗਈ।', '3 ਰੁਝਾਨ ਸ਼ੀਟਾਂ ਅਤੇ 3 ਖੇਤਰੀ ਸ਼ੀਟਾਂ ਬਣਾਉਣਾ।'],
        actions: ['ਸਾਰੀਆਂ ਵਰਕਸ਼ੀਟਾਂ ਨੂੰ ਉੱਚ ਰੈਜ਼ੋਲਿਊਸ਼ਨ PNG ਵਿੱਚ ਨਿਰਯਾਤ ਕਰੋ।', 'ਵਰਡ ਰਿਪੋਰਟ ਤਿਆਰ ਕਰੋ।']
      },
      es: {
        name: 'Spanish (Español)',
        summary: 'El equipo completó con éxito el laboratorio de Tableau sobre estadísticas criminales en India, estructurando 10 gráficos y 3 paneles temáticos.',
        decisions: ['Seleccionar el conjunto de datos sobre criminalidad en India en lugar de turismo.', 'Estructurar las visualizaciones en 3 hojas de tendencias y 3 hojas regionales.'],
        actions: ['Exportar todas las hojas de trabajo a formato PNG de alta resolución.', 'Redactar el informe de laboratorio en Word con capturas de pantalla.']
      },
      fr: {
        name: 'French (Français)',
        summary: 'L’équipe a mené à bien l’atelier pratique sur les statistiques de criminalité en Inde à l’aide de Tableau, en développant 10 visualisations structurées.',
        decisions: ['Choisir les données sur la criminalité en Inde plutôt que sur le tourisme.', 'Organiser les visualisations en 3 vues de tendances et 3 vues régionales.'],
        actions: ['Exporter toutes les feuilles Tableau au format PNG.', 'Rédiger le rapport complet sous Microsoft Word.']
      },
      de: {
        name: 'German (Deutsch)',
        summary: 'Das Team schloss das Tableau-Labor zu Kriminalitätsstatistiken in Indien erfolgreich ab und erstellte 10 Diagramme sowie 3 Dashboards.',
        decisions: ['Auswahl des Kriminalitätsdatensatzes anstelle des Tourismusdatensatzes.', 'Strukturierung in 3 Trend- und 3 Regionalblätter.'],
        actions: ['Alle Arbeitsblätter als hochauflösende PNG-Dateien exportieren.', 'Den Word-Laborbericht mit Screenshots verfassen.']
      },
      zh: {
        name: 'Mandarin Chinese (中文)',
        summary: '团队顺利完成了关于印度犯罪统计数据的Tableau分析实验，成功构建了10个图表和3个主题仪表板。',
        decisions: ['选择犯罪统计数据集而非旅游数据集。', '采用3张趋势工作表与3张区域工作表的架构。'],
        actions: ['将所有Tableau工作表导出为高清PNG图片。', '编写包含截图的最终Word实验报告。']
      },
      ja: {
        name: 'Japanese (日本語)',
        summary: '学生チームはTableauを用いてインドの犯罪統計データを分析し、10種類のグラフと3つのダッシュボードを作成しました。',
        decisions: ['観光データではなく犯罪統計データを選択。', 'トレンド3枚と地域別3枚のシート構成を採用。'],
        actions: ['Tableauワークシートのスクリーンショットを高画質で出力。', 'Wordレポートの作成とピア評価フォームへの回答。']
      },
      ru: {
        name: 'Russian (Русский)',
        summary: 'Команда успешно завершила лабораторную работу в Tableau по статистике преступности в Индии, создав 10 графиков и 3 дашборда.',
        decisions: ['Выбрать датасет преступности вместо туристического.', 'Структурировать визуализации в 3 листа трендов и 3 региональных листа.'],
        actions: ['Экспортировать все листы в формате PNG высокого разрешения.', 'Подготовить итоговый отчет в формате Word.']
      },
      ar: {
        name: 'Arabic (العربية)',
        summary: 'أكمل الفريق بنجاح مختبر تابلو حول إحصاءات الجريمة في الهند مع إنشاء 10 رسوم بيانية و 3 لوحات معلومات.',
        decisions: ['اختيار مجموعة بيانات الجريمة بدلاً من بيانات السياحة.', 'هيكلة الرسوم البيانية في 3 أوراق اتجاهات و 3 أوراق إقليمية.'],
        actions: ['تصدير جميع أوراق العمل بتنسيق PNG عالي الدقة.', 'إعداد تقرير Word النهائي مع لقطات الشاشة.']
      },
      en: {
        name: 'English',
        summary: 'The team completed the Tableau crime statistics analytics lab, creating 10 charts across 3 comprehensive dashboards and storyboards.',
        decisions: ['Selected the Indian Crime statistics dataset over tourism.', 'Adopted a 3-trend and 3-regional sheet layout structure.'],
        actions: ['Export all worksheets to high-resolution PNG format.', 'Draft the complete laboratory report in Word.']
      },
      hinglish: {
        name: 'Hinglish (हिंग्लिश)',
        summary: 'Team ne Tableau crime statistics lab successfully complete kar liya hai with 10 charts and 3 dedicated dashboards.',
        decisions: ['Crime dataset choose kiya instead of tourism data.', '3 trend sheets and 3 regional sheets ka structure finalize hua.'],
        actions: ['Saare worksheets ko high-res PNG me export karna.', 'Word report compile karna with screenshots.']
      },
      tanglish: {
        name: 'Tanglish (தாங்கிலிஷ்)',
        summary: 'Team Tableau crime statistics lab-ah successfully complete pannanga with 10 interactive charts and 3 dashboards.',
        decisions: ['Crime dataset select panniyachu over tourism data.', '3 trend sheets and 3 regional views build panna decision eduthanga.'],
        actions: ['All worksheets-um high-res PNG format-la export pannanum.', 'Final Word report prepare pannanum.']
      }
    };

    const targetLocale = localeLookup[langCode] || localeLookup['en'];
    const newTranslation: TranslationItem = {
      id: `trans-${Date.now().toString(36)}`,
      meeting_id: meetingId,
      language_code: langCode,
      language_name: targetLocale.name,
      translated_summary: targetLocale.summary,
      translated_decisions: targetLocale.decisions,
      translated_action_items: targetLocale.actions,
      created_at: new Date().toISOString()
    };

    setTranslations(prev => [newTranslation, ...prev]);
    addAuditLog('TRANSLATION_SYNTHESIS_REQUEST', 'translation', newTranslation.id, 'SUCCESS', JSON.stringify({ meetingId, langCode }));
  };

  // Handler: Switch Role for RBAC Testing
  const handleSwitchRole = (newRole: any) => {
    setAuth(prev => ({ ...prev, role: newRole }));
    addAuditLog('SECURITY_ROLE_SWITCH', 'auth_context', auth.user_id, 'SUCCESS', JSON.stringify({ newRole }));
  };

  interface NavItem {
    id: string;
    key: 'meetings' | 'live_stream' | 'intelligence' | 'queries' | 'knowledge' | 'translations' | 'reports' | 'benchmarks' | 'security' | 'api_console' | 'system_health';
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
          badge: 'WebSocket',
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
          badge: `${knowledgeObjects.length} KOs`,
          description: 'Vector embeddings & memory'
        },
        {
          id: 'tab-translations',
          key: 'translations',
          label: 'Translations (17 Locales)',
          shortLabel: 'Translations',
          icon: Languages,
          color: 'text-amber-400',
          badge: '17 Locales',
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
          label: 'Research & Benchmarks (SOTA)',
          shortLabel: 'Benchmarks',
          icon: Award,
          color: 'text-amber-400',
          badge: 'SOTA',
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
          label: 'API Console (47 Endpoints)',
          shortLabel: 'API Console',
          icon: Terminal,
          color: 'text-indigo-400',
          badge: '47 APIs',
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
        theme === 'dark' ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900'
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
      />

      {/* Command Palette Modal */}
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        onClose={() => setIsCommandPaletteOpen(false)}
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        meetings={meetings}
        onSelectMeeting={setSelectedMeetingId}
        theme={theme}
      />

      {/* Main Workspace Layout with Sidebar and Viewport */}
      <main id="app-main-content" className="w-full max-w-[1760px] mx-auto px-4 sm:px-6 lg:px-8 py-5">
        {/* Mobile Header Menu Bar */}
        <div
          className={`md:hidden flex items-center justify-between border rounded-2xl p-3 mb-4 backdrop-blur-md ${
            theme === 'dark' ? 'bg-slate-900/80 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900 shadow-xs'
          }`}
        >
          <div className="flex items-center space-x-2">
            <span className={`text-xs font-semibold ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>Current View:</span>
            <span
              className={`text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-lg border ${
                theme === 'dark' ? 'bg-indigo-950/80 text-indigo-300 border-indigo-800/60' : 'bg-indigo-50 text-indigo-700 border-indigo-200'
              }`}
            >
              {NAV_CATEGORIES.flatMap(c => c.items).find(i => i.key === activeTab)?.label}
            </span>
          </div>
          <button
            onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border transition-colors ${
              theme === 'dark' ? 'bg-slate-800 text-slate-200 hover:text-white border-slate-700' : 'bg-slate-100 text-slate-800 hover:bg-slate-200 border-slate-200'
            }`}
          >
            <Menu className={`w-4 h-4 ${theme === 'dark' ? 'text-indigo-400' : 'text-indigo-600'}`} />
            <span>{isMobileSidebarOpen ? 'Close' : 'Modules'}</span>
          </button>
        </div>

        {/* Mobile Sidebar Modal Drawer */}
        <AnimatePresence>
          {isMobileSidebarOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="md:hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex flex-col p-4"
            >
              <div
                className={`border rounded-2xl p-4 flex-1 overflow-y-auto space-y-4 shadow-2xl ${
                  theme === 'dark' ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
                }`}
              >
                <div className={`flex items-center justify-between border-b pb-3 ${theme === 'dark' ? 'border-slate-800' : 'border-slate-200'}`}>
                  <div className="flex items-center space-x-2">
                    <Workflow className={`w-5 h-5 ${theme === 'dark' ? 'text-indigo-400' : 'text-indigo-600'}`} />
                    <div>
                      <h3 className="text-sm font-bold">ABCI-MI Navigation</h3>
                      <p className={`text-[11px] ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>13-Module Meeting Intelligence Engine</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setIsMobileSidebarOpen(false)}
                    className={`p-2 rounded-xl ${theme === 'dark' ? 'bg-slate-800 text-slate-400 hover:text-white' : 'bg-slate-100 text-slate-600 hover:text-slate-900'}`}
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                <div className="space-y-4">
                  {NAV_CATEGORIES.map(category => (
                    <div key={category.title} className="space-y-1.5">
                      <div className={`text-[10px] font-bold uppercase tracking-wider px-2 ${theme === 'dark' ? 'text-slate-400' : 'text-slate-500'}`}>
                        {category.title}
                      </div>
                      <div className="space-y-1">
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
                              className={`w-full flex items-center justify-between p-2.5 rounded-xl text-left transition-all ${
                                isActive
                                  ? 'bg-indigo-600 text-white font-semibold shadow-md shadow-indigo-600/30'
                                  : theme === 'dark'
                                  ? 'bg-slate-950/60 text-slate-300 hover:bg-slate-800 border border-slate-800/60'
                                  : 'bg-slate-50 text-slate-800 hover:bg-slate-100 border border-slate-200'
                              }`}
                            >
                              <div className="flex items-center space-x-2.5">
                                <IconComponent className={`w-4 h-4 ${isActive ? 'text-white' : item.color}`} />
                                <span className="text-xs">{item.label}</span>
                              </div>
                              <span
                                className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold ${
                                  isActive
                                    ? 'bg-indigo-800 text-white'
                                    : theme === 'dark'
                                    ? 'bg-slate-800 text-slate-400'
                                    : 'bg-slate-200 text-slate-600'
                                }`}
                              >
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
        <div className="flex items-start gap-5">
          {/* Animated Desktop Sidebar */}
          <motion.aside
            animate={{ width: isSidebarCollapsed ? 84 : 310 }}
            transition={{ type: 'spring', stiffness: 320, damping: 30 }}
            className={`hidden md:flex flex-col shrink-0 rounded-2xl p-3.5 backdrop-blur-xl sticky top-20 self-start max-h-[calc(100vh-6.5rem)] overflow-y-auto overflow-x-hidden shadow-xl ${
              theme === 'dark'
                ? 'bg-slate-900/80 border border-slate-800/90 shadow-indigo-950/20 text-white'
                : 'bg-white border border-slate-200/90 shadow-slate-200/60 text-slate-900'
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
                  <Workflow className={`w-4 h-4 shrink-0 ${theme === 'dark' ? 'text-indigo-400' : 'text-indigo-600'}`} />
                  <span className={`text-xs font-bold tracking-tight truncate ${theme === 'dark' ? 'text-white' : 'text-slate-900'}`}>
                    Framework Modules
                  </span>
                </motion.div>
              )}
              <button
                onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                title={isSidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
                className={`p-1.5 rounded-lg border transition-colors ml-auto ${
                  theme === 'dark'
                    ? 'bg-slate-950 hover:bg-slate-800 border-slate-800 text-slate-400 hover:text-white'
                    : 'bg-slate-100 hover:bg-slate-200 border-slate-200 text-slate-600 hover:text-slate-900'
                }`}
              >
                {isSidebarCollapsed ? (
                  <PanelLeftOpen className={`w-4 h-4 ${theme === 'dark' ? 'text-indigo-400' : 'text-indigo-600'}`} />
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
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 select-none ${
                        theme === 'dark' ? 'text-slate-400' : 'text-slate-500'
                      }`}
                    >
                      {category.title}
                    </motion.div>
                  )}

                  <div className="space-y-1">
                    {category.items.map(item => {
                      const IconComponent = item.icon;
                      const isActive = activeTab === item.key;

                      return (
                        <motion.button
                          key={item.key}
                          id={item.id}
                          onClick={() => setActiveTab(item.key)}
                          whileHover={{ x: isSidebarCollapsed ? 0 : 2 }}
                          whileTap={{ scale: 0.98 }}
                          title={isSidebarCollapsed ? `${item.label} (${item.badge})` : undefined}
                          className={`relative w-full flex items-center ${
                            isSidebarCollapsed ? 'justify-center px-0 py-2.5' : 'justify-between px-3 py-2.5'
                          } rounded-xl text-xs font-medium transition-all group overflow-hidden ${
                            isActive
                              ? 'text-white font-semibold'
                              : theme === 'dark'
                              ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                              : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                          }`}
                        >
                          {/* Animated Active Backdrop Indicator */}
                          {isActive && (
                            <motion.div
                              layoutId="activeSidebarIndicator"
                              className={`absolute inset-0 rounded-xl ${
                                theme === 'dark'
                                  ? 'bg-indigo-600 shadow-md shadow-indigo-600/30'
                                  : 'bg-indigo-600 shadow-md shadow-indigo-600/25'
                              }`}
                              initial={false}
                              transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                            />
                          )}

                          {/* Button Content */}
                          <div className="relative z-10 flex items-center space-x-2.5 min-w-0">
                            <IconComponent
                              className={`w-4 h-4 shrink-0 transition-transform group-hover:scale-110 ${
                                isActive ? 'text-white' : item.color
                              }`}
                            />
                            {!isSidebarCollapsed && (
                              <div className="text-left truncate">
                                <div className="truncate text-xs leading-snug">{item.label}</div>
                              </div>
                            )}
                          </div>

                          {/* Status Badge */}
                          {!isSidebarCollapsed && (
                            <span
                              className={`relative z-10 text-[10px] px-2 py-0.5 rounded-full font-mono font-bold shrink-0 ml-1.5 ${
                                isActive
                                  ? 'bg-indigo-800/80 text-white'
                                  : theme === 'dark'
                                  ? 'bg-slate-950 text-slate-400 border border-slate-800 group-hover:border-slate-700'
                                  : 'bg-slate-100 text-slate-600 border border-slate-200'
                              }`}
                            >
                              {item.badge}
                            </span>
                          )}
                        </motion.button>
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
                className={`mt-4 pt-3 border-t px-2 space-y-1 text-[10px] font-mono ${
                  theme === 'dark' ? 'border-slate-800/80 text-slate-400' : 'border-slate-200 text-slate-500'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    ACE Orchestrator
                  </span>
                  <span className="text-emerald-500 font-bold">ONLINE</span>
                </div>
                <div className="text-slate-400">Open-MOSS &bull; PyAnnote</div>
              </motion.div>
            )}
          </motion.aside>

          {/* Main Content Viewport */}
          <div className="flex-1 min-w-0">
            {/* Real-time System Status Telemetry Strip */}
            <SystemStatusBar
              theme={theme}
              activeMeetingTitle={selectedMeeting?.title}
              totalMeetingsCount={meetings.length}
              totalKnowledgeObjects={knowledgeObjects.length}
            />

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
                {/* Tab Views */}
                {activeTab === 'meetings' && (
                  <MeetingsTester
                    meetings={meetings}
                    selectedMeetingId={selectedMeetingId}
                    onSelectMeeting={(id) => setSelectedMeetingId(id)}
                    onCreateMeeting={handleCreateMeeting}
                    onUploadAudio={handleUploadAudio}
                    onProcessMeeting={handleProcessMeeting}
                    onViewIntelligence={(meetingId) => {
                      setSelectedMeetingId(meetingId);
                      setActiveTab('intelligence');
                    }}
                    onDeleteMeeting={(id) => {
                      setMeetings(prev => prev.filter(m => m.id !== id));
                      if (selectedMeetingId === id) {
                        const remaining = meetings.filter(m => m.id !== id);
                        if (remaining.length > 0) setSelectedMeetingId(remaining[0].id);
                      }
                      addAuditLog('MEETING_DELETE', 'meeting', id, 'SUCCESS', '{}');
                    }}
                    theme={theme}
                  />
                )}

                {activeTab === 'live_stream' && (
                  <LiveStreamTester
                    meetingId={selectedMeeting.id}
                    meetingTitle={selectedMeeting.title}
                  />
                )}

                {activeTab === 'intelligence' && (
                  <IntelligenceViewer
                    intelligence={activeIntelligence}
                    meetingTitle={selectedMeeting.title}
                    onToggleActionItem={(actId) => {
                      if (!activeIntelligence) return;
                      const updatedItems = activeIntelligence.action_items.map(a =>
                        a.id === actId ? { ...a, status: a.status === 'completed' ? 'pending' : 'completed' as any } : a
                      );
                      setIntelligenceMap(prev => ({
                        ...prev,
                        [selectedMeetingId]: { ...activeIntelligence, action_items: updatedItems }
                      }));
                    }}
                  />
                )}

                {activeTab === 'queries' && (
                  <QueryTester
                    queries={queries}
                    meetings={meetings}
                    selectedMeetingId={selectedMeetingId}
                    onRunQuery={handleRunQuery}
                  />
                )}

                {activeTab === 'knowledge' && (
                  <KnowledgeTester
                    knowledgeObjects={knowledgeObjects}
                    onSearch={(query) => {
                      // Vector search simulated
                    }}
                  />
                )}

                {activeTab === 'translations' && (
                  <TranslationTester
                    translations={translations}
                    meetingId={selectedMeeting.id}
                    meetingTitle={selectedMeeting.title}
                    onRequestTranslation={handleRequestTranslation}
                  />
                )}

                {activeTab === 'reports' && (
                  <ReportTester
                    meeting={selectedMeeting}
                    allMeetings={meetings}
                    onSelectMeeting={(id) => setSelectedMeetingId(id)}
                  />
                )}

                {activeTab === 'benchmarks' && (
                  <ResearchBenchmarkViewer />
                )}

                {activeTab === 'security' && (
                  <AdminAuditTester
                    auth={auth}
                    auditLogs={auditLogs}
                    onSwitchRole={handleSwitchRole}
                  />
                )}

                {activeTab === 'api_console' && (
                  <ApiConsoleTester
                    endpoints={ALL_API_ENDPOINTS}
                    activeMeetingId={selectedMeeting.id}
                  />
                )}

                {activeTab === 'system_health' && (
                  <SystemHealthDashboard
                    theme={theme}
                  />
                )}
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
                  setNotifications(prev => prev.map(n => ({ ...n, read: true })));
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
    </div>
  );
}
