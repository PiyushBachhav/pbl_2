import { useEffect, useState } from 'react';
import { getSummary, getViolationsByType, getEvents, type SafetyEvent } from '../services/api';
import { AlertTriangle, Shield, CheckCircle2, Activity, TrendingUp, Clock } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface Summary {
  total_events: number;
  open_events: number;
  high_critical_events: number;
  resolved_events: number;
}

const SEVERITY_COLOR: Record<string, string> = {
  LOW: '#22c55e',
  MEDIUM: '#f59e0b',
  HIGH: '#ef4444',
  CRITICAL: '#dc2626',
};

function SeverityBadge({ severity }: { severity: string }) {
  const cls = {
    LOW: 'badge-low',
    MEDIUM: 'badge-medium',
    HIGH: 'badge-high',
    CRITICAL: 'badge-critical',
  }[severity] || 'badge-medium';
  return <span className={cls}>{severity}</span>;
}

function StatCard({ label, value, icon: Icon, accent }: {
  label: string; value: number | string; icon: React.ElementType; accent: string
}) {
  return (
    <div className="stat-card group">
      <div className="flex items-center justify-between mb-3">
        <span className="stat-label">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${accent}`}>
          <Icon size={16} />
        </div>
      </div>
      <span className="stat-value">{value}</span>
    </div>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [violations, setViolations] = useState<{ event_type: string; count: number }[]>([]);
  const [recentEvents, setRecentEvents] = useState<SafetyEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [sum, viol, evts] = await Promise.all([
          getSummary(),
          getViolationsByType(),
          getEvents({ limit: 8 }),
        ]);
        setSummary(sum);
        setViolations(viol);
        setRecentEvents(evts);
        setBackendOnline(true);
      } catch {
        setBackendOnline(false);
      } finally {
        setLoading(false);
      }
    }
    load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, []);

  const formatEventType = (t: string) =>
    t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  const formatTime = (iso: string) =>
    new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Safety Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Real-time industrial safety monitoring</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${backendOnline === false ? 'bg-red-500' : 'bg-green-400 animate-pulse'}`} />
          <span className="text-xs text-slate-500">
            {backendOnline === null ? 'Connecting…' : backendOnline ? 'Backend Online' : 'Backend Offline'}
          </span>
        </div>
      </div>

      {/* Offline notice */}
      {backendOnline === false && (
        <div className="card border-red-800/50 bg-red-950/20 flex items-center gap-3">
          <AlertTriangle size={18} className="text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-300">Backend not reachable</p>
            <p className="text-xs text-slate-500 mt-0.5">
              Start the backend: <code className="font-mono bg-surface px-1 rounded">uvicorn app.main:app --reload</code>
            </p>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Events"
          value={loading ? '—' : (summary?.total_events ?? 0)}
          icon={Activity}
          accent="bg-brand-900/40 text-brand-400"
        />
        <StatCard
          label="Open Violations"
          value={loading ? '—' : (summary?.open_events ?? 0)}
          icon={AlertTriangle}
          accent="bg-amber-900/40 text-amber-400"
        />
        <StatCard
          label="High / Critical"
          value={loading ? '—' : (summary?.high_critical_events ?? 0)}
          icon={TrendingUp}
          accent="bg-red-900/40 text-red-400"
        />
        <StatCard
          label="Resolved"
          value={loading ? '—' : (summary?.resolved_events ?? 0)}
          icon={CheckCircle2}
          accent="bg-green-900/40 text-green-400"
        />
      </div>

      {/* Charts + Recent Events */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Violations by type chart */}
        <div className="card lg:col-span-3">
          <div className="flex items-center gap-2 mb-4">
            <Shield size={16} className="text-brand-400" />
            <h2 className="text-sm font-semibold text-slate-200">Violations by Type</h2>
          </div>
          {violations.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-slate-600 text-sm">
              No events recorded yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={violations} barSize={24}>
                <XAxis
                  dataKey="event_type"
                  tick={{ fill: '#64748b', fontSize: 10 }}
                  tickFormatter={formatEventType}
                />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{
                    background: '#161b27',
                    border: '1px solid #1f2937',
                    borderRadius: '8px',
                    color: '#e2e8f0',
                  }}
                  formatter={(v) => [v, 'Events']}
                  labelFormatter={(t) => formatEventType(String(t))}
                />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {violations.map((_, i) => (
                    <Cell key={i} fill={`hsl(${230 + i * 15}, 60%, 55%)`} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Recent events */}
        <div className="card lg:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <Clock size={16} className="text-brand-400" />
            <h2 className="text-sm font-semibold text-slate-200">Recent Events</h2>
          </div>
          <div className="space-y-2">
            {recentEvents.length === 0 ? (
              <p className="text-sm text-slate-600 text-center py-8">No events yet</p>
            ) : (
              recentEvents.map(evt => (
                <div key={evt.id} className="flex items-start gap-2.5 p-2 rounded-lg hover:bg-surface-hover transition-colors">
                  <SeverityBadge severity={evt.severity} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-slate-300 leading-snug truncate">
                      {evt.description}
                    </p>
                    <p className="text-xs text-slate-600 mt-0.5">
                      {formatTime(evt.detected_at)}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Architecture note */}
      <div className="card border-brand-900/40 bg-brand-950/10">
        <div className="flex items-start gap-3">
          <Shield size={16} className="text-brand-400 mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-xs font-semibold text-brand-400 mb-1">Architecture: Phase 1–2 Active</p>
            <p className="text-xs text-slate-500 leading-relaxed">
              Repository structure, FastAPI backend, and YOLO inference pipeline are complete.
              The safety engine, zone detection, and real-time WebSocket are in Phase 3–11.
              Use <code className="font-mono bg-surface px-1 rounded text-slate-400">python ml/inference.py --input video.mp4</code> to test the CV pipeline.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
