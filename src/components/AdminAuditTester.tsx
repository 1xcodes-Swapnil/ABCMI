import React, { useState } from 'react';
import {
  ShieldCheck,
  Lock,
  UserCheck,
  KeyRound,
  FileCheck,
  AlertOctagon,
  Eye,
  CheckCircle2,
  RefreshCw,
  Search
} from 'lucide-react';
import { AuditLogItem, AuthContext } from '../types';

interface AdminAuditTesterProps {
  auth: AuthContext;
  auditLogs: AuditLogItem[];
  onSwitchRole: (role: 'host' | 'admin' | 'member' | 'security_officer') => void;
}

export const AdminAuditTester: React.FC<AdminAuditTesterProps> = ({
  auth,
  auditLogs,
  onSwitchRole
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [showRedactionInfo, setShowRedactionInfo] = useState(true);

  const filteredLogs = auditLogs.filter(log => {
    if (!searchTerm) return true;
    return log.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
           log.user_email.toLowerCase().includes(searchTerm.toLowerCase()) ||
           log.resource_type.toLowerCase().includes(searchTerm.toLowerCase()) ||
           log.status.toLowerCase().includes(searchTerm.toLowerCase());
  });

  return (
    <div id="admin-audit-tester" className="space-y-6">
      {/* Header & Role Switcher */}
      <div className="bg-neutral-900/60 p-5 rounded-xl border border-neutral-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-400" />
                Security, RBAC Auth &amp; Immutable Audit Logs
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-950 text-emerald-400 border border-emerald-900 font-mono">
                Phase 4.25 &bull; HS256 JWT
              </span>
            </div>
            <p className="text-xs text-neutral-400 mt-1">
              Active Tenant: <strong className="text-neutral-200">{auth.tenant_id}</strong> &bull; User: <span className="font-mono text-indigo-400">{auth.user_email}</span>
            </p>
          </div>

          {/* Current Role Badge & Switcher */}
          <div className="flex items-center space-x-2">
            <span className="text-xs text-neutral-400">Simulate Role:</span>
            <div className="flex rounded-lg bg-neutral-950 p-1 border border-neutral-800">
              {(['admin', 'security_officer', 'host', 'member'] as const).map((r) => (
                <button
                  key={r}
                  id={`btn-role-switch-${r}`}
                  onClick={() => onSwitchRole(r)}
                  className={`px-2.5 py-1 rounded text-xs font-semibold uppercase tracking-wider transition-colors ${
                    auth.role === r
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'text-neutral-400 hover:text-neutral-200'
                  }`}
                >
                  {r.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Security Scorecard Metrics */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
          <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800">
            <div className="text-[10px] font-bold text-neutral-500 uppercase">Cryptographic Token</div>
            <div className="text-xs font-semibold text-emerald-400 flex items-center gap-1 mt-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              HS256 Verified
            </div>
          </div>
          <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800">
            <div className="text-[10px] font-bold text-neutral-500 uppercase">Tenant Isolation</div>
            <div className="text-xs font-semibold text-indigo-400 flex items-center gap-1 mt-1">
              <Lock className="w-3.5 h-3.5" />
              Strictly Scoped
            </div>
          </div>
          <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800">
            <div className="text-[10px] font-bold text-neutral-500 uppercase">Secret Redaction</div>
            <div className="text-xs font-semibold text-purple-400 flex items-center gap-1 mt-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              Active (SHA-256)
            </div>
          </div>
          <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800">
            <div className="text-[10px] font-bold text-neutral-500 uppercase">Access Violations</div>
            <div className="text-xs font-semibold text-amber-400 flex items-center gap-1 mt-1">
              <AlertOctagon className="w-3.5 h-3.5" />
              1 Blocked (403)
            </div>
          </div>
        </div>
      </div>

      {/* Audit Logs Table & Search */}
      <div className="bg-neutral-900/40 p-5 rounded-xl border border-neutral-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-neutral-400">
            Immutable Audit Trail ({filteredLogs.length} Events)
          </h3>
          <div className="relative w-full sm:w-72">
            <Search className="w-3.5 h-3.5 text-neutral-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search action, user, or status..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-neutral-950 border border-neutral-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-white placeholder-neutral-500 focus:outline-none focus:border-emerald-500"
            />
          </div>
        </div>

        <div className="bg-neutral-950 rounded-xl border border-neutral-800 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-neutral-300">
              <thead className="bg-neutral-900 border-b border-neutral-800 text-[10px] uppercase font-semibold text-neutral-400">
                <tr>
                  <th className="py-3 px-4 w-32">Timestamp</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Resource</th>
                  <th className="py-3 px-4 w-24">Status</th>
                  <th className="py-3 px-4">Redacted Payload</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-900 font-mono text-[11px]">
                {filteredLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-neutral-900/40 transition-colors">
                    <td className="py-2.5 px-4 text-neutral-500">{new Date(log.timestamp).toLocaleTimeString()}</td>
                    <td className="py-2.5 px-4 font-bold text-neutral-200">{log.action}</td>
                    <td className="py-2.5 px-4 text-neutral-400 font-sans text-xs truncate max-w-[140px]">{log.user_email}</td>
                    <td className="py-2.5 px-4 text-neutral-400">{log.resource_type}</td>
                    <td className="py-2.5 px-4">
                      {log.status === 'SUCCESS' ? (
                        <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 text-[10px] font-bold border border-emerald-900">
                          SUCCESS
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-rose-950 text-rose-400 text-[10px] font-bold border border-rose-900">
                          DENIED
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-[10px] text-neutral-400 truncate max-w-xs font-mono">
                      {log.sanitized_payload}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};
