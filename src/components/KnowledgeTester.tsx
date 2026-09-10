import React, { useState } from 'react';
import {
  Database,
  Search,
  Layers,
  GitBranch,
  FileCode,
  Tag,
  CheckCircle2,
  Calendar,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { KnowledgeObject } from '../types';

interface KnowledgeTesterProps {
  knowledgeObjects: KnowledgeObject[];
  onSearch: (query: string) => void;
}

export const KnowledgeTester: React.FC<KnowledgeTesterProps> = ({
  knowledgeObjects,
  onSearch
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedKO, setSelectedKO] = useState<KnowledgeObject | null>(knowledgeObjects[0] || null);

  const filteredKOs = knowledgeObjects.filter(ko => {
    if (!searchTerm) return true;
    const match = ko.topic.toLowerCase().includes(searchTerm.toLowerCase()) ||
                  ko.content.toLowerCase().includes(searchTerm.toLowerCase()) ||
                  ko.entities.some(e => e.toLowerCase().includes(searchTerm.toLowerCase()));
    return match;
  });

  return (
    <div id="knowledge-tester" className="space-y-6">
      {/* Header & Search */}
      <div className="bg-neutral-900/60 p-5 rounded-xl border border-neutral-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Database className="w-5 h-5 text-purple-400" />
                Semantic Knowledge Warehouse (SKW)
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-950 text-purple-400 border border-purple-900 font-mono">
                Qdrant Vector DB &bull; Lineage Audited
              </span>
            </div>
            <p className="text-xs text-neutral-400 mt-1">
              Inspect canonical Knowledge Objects (KOs), semantic vector indexing, and revision lineage with supersession tracking.
            </p>
          </div>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <Search className="w-4 h-4 text-neutral-500 absolute left-3 top-3" />
          <input
            id="input-skw-search"
            type="text"
            placeholder="Search knowledge objects by semantic topic, content, or entity tags..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-9 pr-4 py-2 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-purple-500 transition-colors"
          />
        </div>
      </div>

      {/* Grid: KO List and KO Detail Viewer */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: List */}
        <div className="lg:col-span-1 space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
            Canonical Objects ({filteredKOs.length})
          </h3>
          <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
            {filteredKOs.map((ko) => {
              const isSelected = selectedKO?.id === ko.id;
              return (
                <div
                  key={ko.id}
                  id={`ko-item-${ko.id}`}
                  onClick={() => setSelectedKO(ko)}
                  className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                    isSelected
                      ? 'bg-neutral-900 border-purple-500 shadow-md shadow-purple-500/10'
                      : 'bg-neutral-900/40 border-neutral-800 hover:border-neutral-700 hover:bg-neutral-900/60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="px-2 py-0.5 rounded bg-purple-950 text-purple-400 text-[10px] font-bold border border-purple-900 uppercase">
                      {ko.type}
                    </span>
                    <span className="text-[10px] text-neutral-500 font-mono">v{ko.version}</span>
                  </div>
                  <h4 className="text-xs font-semibold text-white line-clamp-1">{ko.topic}</h4>
                  <p className="text-[11px] text-neutral-400 line-clamp-2">{ko.content}</p>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {ko.entities.slice(0, 3).map((ent) => (
                      <span key={`ko-card-ent-${ko.id}-${ent}`} className="text-[9px] px-1.5 py-0.5 rounded bg-neutral-950 text-neutral-400 border border-neutral-800">
                        #{ent}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Selected KO Inspection */}
        <div className="lg:col-span-2 space-y-4">
          {selectedKO ? (
            <div className="bg-neutral-900/60 p-6 rounded-xl border border-neutral-800 space-y-5">
              <div className="flex items-start justify-between gap-3 border-b border-neutral-800 pb-4">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-mono text-purple-400 font-bold">{selectedKO.id}</span>
                    <span className="px-2 py-0.5 rounded bg-neutral-950 text-neutral-300 text-[10px] font-semibold border border-neutral-800">
                      Revision v{selectedKO.version}
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-white">{selectedKO.topic}</h3>
                </div>
                <span className="px-2.5 py-1 rounded bg-emerald-950 text-emerald-400 text-xs font-bold border border-emerald-800 flex items-center">
                  <Sparkles className="w-3 h-3 mr-1" />
                  {(selectedKO.confidence * 100).toFixed(0)}% Confidence
                </span>
              </div>

              {/* Content Body */}
              <div className="space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-neutral-400">Canonical Content</span>
                <div className="bg-neutral-950 p-4 rounded-lg border border-neutral-800 text-xs text-neutral-200 leading-relaxed font-sans">
                  {selectedKO.content}
                </div>
              </div>

              {/* Entities Tag Cloud */}
              <div className="space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-neutral-400 flex items-center gap-1">
                  <Tag className="w-3.5 h-3.5 text-purple-400" />
                  Indexed Semantic Entities
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {selectedKO.entities.map((ent) => (
                    <span key={`ko-detail-ent-${selectedKO.id}-${ent}`} className="text-xs px-2.5 py-1 rounded-md bg-neutral-950 text-indigo-300 border border-indigo-900/60 font-mono">
                      {ent}
                    </span>
                  ))}
                </div>
              </div>

              {/* Lineage & Revision Audit */}
              <div className="space-y-2 pt-2 border-t border-neutral-800">
                <span className="text-xs font-bold uppercase tracking-wider text-neutral-400 flex items-center gap-1.5">
                  <GitBranch className="w-3.5 h-3.5 text-emerald-400" />
                  Version Lineage &amp; Supersession Audit
                </span>
                <div className="bg-neutral-950 p-4 rounded-lg border border-neutral-800 space-y-2 text-xs font-mono">
                  <div className="flex items-center justify-between text-neutral-400">
                    <span>Current Active Version:</span>
                    <span className="text-emerald-400 font-bold">v{selectedKO.version} (Active Canonical)</span>
                  </div>
                  {selectedKO.supersedes && (
                    <div className="flex items-center justify-between text-neutral-400">
                      <span>Supersedes Revision:</span>
                      <span className="text-amber-400">{selectedKO.supersedes}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between text-neutral-400">
                    <span>Source Meeting UUID:</span>
                    <span className="text-indigo-400">{selectedKO.meeting_id}</span>
                  </div>
                  <div className="flex items-center justify-between text-neutral-400">
                    <span>Timestamp:</span>
                    <span className="text-neutral-300">{selectedKO.created_at}</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-neutral-900/40 p-8 rounded-xl border border-neutral-800 text-center text-xs text-neutral-500">
              Select a Knowledge Object to inspect canonical payload and version lineage.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
