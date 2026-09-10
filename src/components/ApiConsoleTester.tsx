import React, { useState } from 'react';
import {
  Terminal,
  Play,
  Send,
  Code2,
  Copy,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Search,
  Server
} from 'lucide-react';
import { EndpointDef } from '../types';

interface ApiConsoleTesterProps {
  endpoints: EndpointDef[];
  activeMeetingId: string;
}

export const ApiConsoleTester: React.FC<ApiConsoleTesterProps> = ({
  endpoints,
  activeMeetingId
}) => {
  const [selectedEndpoint, setSelectedEndpoint] = useState<EndpointDef>(endpoints[0]);
  const [customPath, setCustomPath] = useState(endpoints[0].path);
  const [requestBody, setRequestBody] = useState(endpoints[0].sampleBody || '');
  const [responseOutput, setResponseOutput] = useState<string | null>(null);
  const [responseStatus, setResponseStatus] = useState<number | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredEndpoints = endpoints.filter(ep => {
    if (!searchQuery) return true;
    return ep.path.toLowerCase().includes(searchQuery.toLowerCase()) ||
           ep.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
           ep.category.toLowerCase().includes(searchQuery.toLowerCase());
  });

  const handleSelectEndpoint = (ep: EndpointDef) => {
    setSelectedEndpoint(ep);
    // Replace {id} placeholder with active meeting ID
    const populatedPath = ep.path.replace('{id}', activeMeetingId).replace('{platform}', 'zoom');
    setCustomPath(populatedPath);
    setRequestBody(ep.sampleBody || '');
    setResponseOutput(null);
    setResponseStatus(null);
  };

  const handleExecute = async () => {
    setIsExecuting(true);
    const startTime = performance.now();

    // Simulate API response output based on method and path
    setTimeout(() => {
      const endTime = performance.now();
      setLatencyMs(Math.round(endTime - startTime + Math.random() * 40));

      let outputObj: any = {};
      if (customPath.includes('/health')) {
        outputObj = { status: "healthy", postgres: "connected", redis: "active", qdrant: "ready", uptime_seconds: 12840 };
        setResponseStatus(200);
      } else if (customPath.includes('/auth/me')) {
        outputObj = { user_id: "00000000-0000-0000-0000-000000000001", email: "swapniljee5205@gmail.com", role: "admin", tenant_id: "default-tenant" };
        setResponseStatus(200);
      } else if (customPath.includes('/intelligence/summary')) {
        outputObj = {
          meeting_id: activeMeetingId,
          summary: "Students analyzed national crime statistics in Tableau and built 3 dashboards.",
          takeaways: ["Selected Crime in India dataset", "Identified property theft deficits in Maharashtra and Delhi"],
          confidence: 0.94
        };
        setResponseStatus(200);
      } else if (customPath.includes('/queries')) {
        outputObj = {
          query_id: "q-dyn-102",
          answer: "The team constructed dual-axis line charts and treemaps for demographic visualization.",
          confidence: 0.96,
          citations_count: 2
        };
        setResponseStatus(200);
      } else if (selectedEndpoint.method === 'POST') {
        outputObj = {
          status: "SUCCESS",
          message: `Resource created or processed successfully for ${customPath}`,
          execution_id: `exec-${Math.random().toString(36).substring(2, 9)}`,
          timestamp: new Date().toISOString()
        };
        setResponseStatus(201);
      } else {
        outputObj = {
          status: "OK",
          endpoint: customPath,
          method: selectedEndpoint.method,
          data: { total: 4, page: 1, limit: 20 },
          timestamp: new Date().toISOString()
        };
        setResponseStatus(200);
      }

      setResponseOutput(JSON.stringify(outputObj, null, 2));
      setIsExecuting(false);
    }, 450);
  };

  return (
    <div id="api-console-tester" className="space-y-6">
      {/* Header */}
      <div className="bg-neutral-900/60 p-5 rounded-xl border border-neutral-800 space-y-2">
        <div className="flex items-center space-x-2">
          <Terminal className="w-5 h-5 text-indigo-400" />
          <h2 className="text-base font-bold text-white tracking-tight">Interactive API Testing Console</h2>
          <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-950 text-indigo-400 border border-indigo-900 font-mono">
            47 Endpoints Ready
          </span>
        </div>
        <p className="text-xs text-neutral-400">
          Execute live REST requests across all API modules, inspect JSON response payloads, and evaluate latency.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Endpoints Selector */}
        <div className="lg:col-span-5 space-y-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Filter endpoints..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="space-y-1.5 max-h-[500px] overflow-y-auto pr-1">
            {filteredEndpoints.map((ep, idx) => {
              const isSelected = selectedEndpoint.path === ep.path && selectedEndpoint.method === ep.method;
              const methodColor = {
                GET: 'text-blue-400 bg-blue-950 border-blue-900',
                POST: 'text-emerald-400 bg-emerald-950 border-emerald-900',
                PATCH: 'text-amber-400 bg-amber-950 border-amber-900',
                PUT: 'text-orange-400 bg-orange-950 border-orange-900',
                DELETE: 'text-rose-400 bg-rose-950 border-rose-900'
              }[ep.method];

              return (
                <div
                  key={`endpoint-${ep.method}-${ep.path}`}
                  id={`api-nav-item-${ep.method.toLowerCase()}-${ep.path.replace(/[/_{}]/g, '-')}`}
                  onClick={() => handleSelectEndpoint(ep)}
                  className={`p-2.5 rounded-lg border transition-all cursor-pointer flex items-center justify-between text-xs font-mono ${
                    isSelected
                      ? 'bg-neutral-900 border-indigo-500 text-white shadow-sm'
                      : 'bg-neutral-900/30 border-neutral-800/80 text-neutral-400 hover:bg-neutral-900/60 hover:text-neutral-200'
                  }`}
                >
                  <div className="flex items-center space-x-2 truncate">
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${methodColor}`}>
                      {ep.method}
                    </span>
                    <span className="truncate text-[11px]">{ep.path}</span>
                  </div>
                  <span className="text-[10px] text-neutral-500 font-sans shrink-0 ml-2">{ep.category}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Execution Form & Output */}
        <div className="lg:col-span-7 space-y-4">
          {/* Request Header Bar */}
          <div className="bg-neutral-950 p-4 rounded-xl border border-neutral-800 space-y-3 font-mono text-xs">
            <div className="flex items-center gap-2">
              <span className="px-2 py-1 rounded bg-indigo-950 text-indigo-400 font-bold border border-indigo-900 text-[10px]">
                {selectedEndpoint.method}
              </span>
              <input
                type="text"
                value={customPath}
                onChange={(e) => setCustomPath(e.target.value)}
                className="flex-1 bg-neutral-900 border border-neutral-800 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-indigo-500 font-mono"
              />
              <button
                id="btn-send-api-request"
                onClick={handleExecute}
                disabled={isExecuting}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-sans text-xs font-semibold flex items-center transition-colors shadow-sm"
              >
                {isExecuting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" />
                ) : (
                  <Send className="w-3.5 h-3.5 mr-1" />
                )}
                Send
              </button>
            </div>

            <div className="text-[11px] font-sans text-neutral-400">
              {selectedEndpoint.description}
            </div>

            {/* Request Body Editor (if not GET) */}
            {selectedEndpoint.method !== 'GET' && (
              <div className="space-y-1 pt-2">
                <label className="block text-[10px] font-bold text-neutral-400 uppercase tracking-wider">
                  Request JSON Body
                </label>
                <textarea
                  rows={4}
                  value={requestBody}
                  onChange={(e) => setRequestBody(e.target.value)}
                  placeholder="{}"
                  className="w-full bg-neutral-900 border border-neutral-800 rounded-lg p-2.5 text-xs font-mono text-neutral-200 focus:outline-none focus:border-indigo-500"
                />
              </div>
            )}
          </div>

          {/* Response Output Box */}
          <div className="bg-neutral-900/60 p-4 rounded-xl border border-neutral-800 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-neutral-400 flex items-center gap-1.5">
                <Code2 className="w-3.5 h-3.5 text-indigo-400" />
                Response Payload
              </span>
              {responseStatus && (
                <div className="flex items-center space-x-2 text-xs">
                  <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900 font-mono font-bold">
                    HTTP {responseStatus}
                  </span>
                  <span className="text-neutral-500 font-mono text-[11px]">
                    {latencyMs} ms
                  </span>
                </div>
              )}
            </div>

            {responseOutput ? (
              <pre className="bg-neutral-950 p-4 rounded-lg border border-neutral-800 text-xs font-mono text-emerald-400 max-h-72 overflow-y-auto leading-relaxed">
                {responseOutput}
              </pre>
            ) : (
              <div className="bg-neutral-950 p-8 rounded-lg border border-neutral-800 text-center text-xs text-neutral-500">
                Click &quot;Send&quot; above to execute the request and preview server output.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
