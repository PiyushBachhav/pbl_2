import { useEffect, useState } from 'react';
import { getEvents, updateEventStatus, type SafetyEvent } from '../services/api';
import { AlertTriangle, Filter, CheckCircle2, X, Eye } from 'lucide-react';

function SeverityBadge({ s }: { s: string }) {
  const cls = { LOW: 'badge-low', MEDIUM: 'badge-medium', HIGH: 'badge-high', CRITICAL: 'badge-critical' }[s] || 'badge-medium';
  return <span className={cls}>{s}</span>;
}

function StatusBadge({ s }: { s: string }) {
  const cls = {
    OPEN: 'status-open',
    ACKNOWLEDGED: 'status-acknowledged',
    RESOLVED: 'status-resolved',
    FALSE_POSITIVE: 'status-false_positive',
  }[s] || 'status-open';
  return <span className={cls}>{s.replace('_', ' ')}</span>;
}

export default function EventsPage() {
  const [events, setEvents] = useState<SafetyEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [severityFilter, setSeverityFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<SafetyEvent | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const evts = await getEvents({
        severity: severityFilter || undefined,
        status: statusFilter || undefined,
        limit: 200,
      });
      setEvents(evts);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [severityFilter, statusFilter]);

  const handleStatus = async (id: number, status: string) => {
    await updateEventStatus(id, status);
    setSelected(null);
    load();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Safety Events</h1>
          <p className="text-sm text-slate-500 mt-0.5">{events.length} events</p>
        </div>
      </div>

      {/* Filters */}
      <div className="card flex items-center gap-3 py-3">
        <Filter size={14} className="text-slate-500 flex-shrink-0" />
        <select
          className="input w-40 text-xs py-1.5"
          value={severityFilter}
          onChange={e => setSeverityFilter(e.target.value)}
        >
          <option value="">All Severities</option>
          {['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          className="input w-44 text-xs py-1.5"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="">All Statuses</option>
          {['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'FALSE_POSITIVE'].map(s => (
            <option key={s} value={s}>{s.replace('_', ' ')}</option>
          ))}
        </select>
        {(severityFilter || statusFilter) && (
          <button className="btn-ghost py-1.5 text-xs" onClick={() => { setSeverityFilter(''); setStatusFilter(''); }}>
            <X size={12} /> Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-surface-border">
              <th className="table-head text-left">Event</th>
              <th className="table-head text-left">Worker</th>
              <th className="table-head text-left">Severity</th>
              <th className="table-head text-left">Status</th>
              <th className="table-head text-left">Time</th>
              <th className="table-head text-left">Duration</th>
              <th className="table-head text-left">Conf.</th>
              <th className="table-head"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="table-cell text-center py-12 text-slate-600">Loading…</td></tr>
            ) : events.length === 0 ? (
              <tr><td colSpan={8} className="table-cell text-center py-12 text-slate-600">No events found</td></tr>
            ) : events.map(evt => (
              <tr key={evt.id} className="table-row">
                <td className="table-cell">
                  <div className="font-medium text-slate-200 text-xs">
                    {evt.event_type.replace(/_/g, ' ')}
                  </div>
                  <div className="text-slate-600 text-xs truncate max-w-[200px]">{evt.description}</div>
                </td>
                <td className="table-cell font-mono text-xs text-slate-400">
                  {evt.subject_track_id !== null ? `Worker #${evt.subject_track_id}` : '—'}
                </td>
                <td className="table-cell"><SeverityBadge s={evt.severity} /></td>
                <td className="table-cell"><StatusBadge s={evt.status} /></td>
                <td className="table-cell text-xs text-slate-500 font-mono">
                  {new Date(evt.detected_at).toLocaleTimeString()}
                </td>
                <td className="table-cell text-xs text-slate-500">
                  {evt.duration_seconds ? `${evt.duration_seconds.toFixed(1)}s` : '—'}
                </td>
                <td className="table-cell text-xs text-slate-500">
                  {evt.confidence ? `${(evt.confidence * 100).toFixed(0)}%` : '—'}
                </td>
                <td className="table-cell">
                  <button
                    className="p-1.5 hover:bg-surface-hover rounded text-slate-500 hover:text-brand-400 transition-colors"
                    onClick={() => setSelected(evt)}
                  >
                    <Eye size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detail modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <div className="card w-full max-w-lg animate-slide-in" onClick={e => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="font-semibold text-slate-100">{selected.event_type.replace(/_/g, ' ')}</h2>
                <p className="text-xs text-slate-500 mt-0.5">Event #{selected.id}</p>
              </div>
              <button onClick={() => setSelected(null)} className="p-1 hover:bg-surface-hover rounded"><X size={16} /></button>
            </div>

            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-surface rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Severity</div>
                  <SeverityBadge s={selected.severity} />
                </div>
                <div className="bg-surface rounded-lg p-3">
                  <div className="text-xs text-slate-500 mb-1">Status</div>
                  <StatusBadge s={selected.status} />
                </div>
              </div>

              <div className="bg-surface rounded-lg p-3">
                <div className="text-xs text-slate-500 mb-1">Description</div>
                <p className="text-slate-300 text-xs leading-relaxed">{selected.description}</p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div><span className="text-slate-500">Worker: </span><span className="font-mono">{selected.subject_track_id !== null ? `#${selected.subject_track_id}` : '—'}</span></div>
                <div><span className="text-slate-500">Zone: </span>{selected.zone_id ?? '—'}</div>
                <div><span className="text-slate-500">Detected: </span><span className="font-mono">{new Date(selected.detected_at).toLocaleString()}</span></div>
                <div><span className="text-slate-500">Duration: </span>{selected.duration_seconds ? `${selected.duration_seconds.toFixed(1)}s` : '—'}</div>
              </div>

              {selected.evidence_frame_path && (
                <div>
                  <div className="text-xs text-slate-500 mb-2">Evidence Frame</div>
                  <img
                    src={`http://localhost:8000${selected.evidence_frame_path}`}
                    alt="Evidence frame"
                    className="w-full rounded-lg border border-surface-border"
                  />
                </div>
              )}
            </div>

            {selected.status === 'OPEN' && (
              <div className="flex gap-2 mt-4 pt-4 border-t border-surface-border">
                <button className="btn-primary flex-1 justify-center text-xs" onClick={() => handleStatus(selected.id, 'ACKNOWLEDGED')}>
                  <CheckCircle2 size={14} /> Acknowledge
                </button>
                <button className="btn-ghost flex-1 justify-center text-xs" onClick={() => handleStatus(selected.id, 'RESOLVED')}>
                  Resolve
                </button>
                <button className="btn-danger flex-1 justify-center text-xs" onClick={() => handleStatus(selected.id, 'FALSE_POSITIVE')}>
                  False Positive
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
