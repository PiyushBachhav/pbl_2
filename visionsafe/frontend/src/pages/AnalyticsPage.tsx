import { useEffect, useState } from 'react';
import { getSummary, getViolationsByType } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend } from 'recharts';
import { BarChart3 } from 'lucide-react';

const CHART_COLORS = ['#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f97316', '#eab308'];

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<{ total_events: number; open_events: number; high_critical_events: number; resolved_events: number } | null>(null);
  const [violations, setViolations] = useState<{ event_type: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [sum, viol] = await Promise.all([getSummary(), getViolationsByType()]);
        setSummary(sum);
        setViolations(viol);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const fmt = (t: string) => t.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  const statusData = summary ? [
    { name: 'Open', value: summary.open_events, fill: '#ef4444' },
    { name: 'Resolved', value: summary.resolved_events, fill: '#22c55e' },
    { name: 'High/Critical', value: summary.high_critical_events, fill: '#dc2626' },
  ] : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-sm text-slate-500 mt-0.5">Historical safety performance — based on real database data</p>
      </div>

      {loading ? (
        <div className="card text-center py-12 text-slate-600">Loading analytics…</div>
      ) : (
        <>
          {/* Summary row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: 'Total Events', value: summary?.total_events ?? 0 },
              { label: 'Open', value: summary?.open_events ?? 0 },
              { label: 'High / Critical', value: summary?.high_critical_events ?? 0 },
              { label: 'Resolved', value: summary?.resolved_events ?? 0 },
            ].map(({ label, value }) => (
              <div key={label} className="stat-card">
                <span className="stat-label">{label}</span>
                <span className="stat-value">{value}</span>
              </div>
            ))}
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Bar chart */}
            <div className="card">
              <div className="flex items-center gap-2 mb-4">
                <BarChart3 size={16} className="text-brand-400" />
                <h2 className="text-sm font-semibold">Violations by Type</h2>
              </div>
              {violations.length === 0 ? (
                <div className="h-48 flex items-center justify-center text-slate-600 text-sm">
                  No violation data yet
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={violations} barSize={28}>
                    <XAxis dataKey="event_type" tickFormatter={fmt} tick={{ fill: '#64748b', fontSize: 9 }} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
                    <Tooltip
                      contentStyle={{ background: '#161b27', border: '1px solid #1f2937', borderRadius: '8px', color: '#e2e8f0', fontSize: '12px' }}
                      formatter={(v) => [v, 'Events']}
                      labelFormatter={(t) => fmt(String(t))}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {violations.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Pie chart */}
            <div className="card">
              <h2 className="text-sm font-semibold mb-4">Event Status Distribution</h2>
              {statusData.every(d => d.value === 0) ? (
                <div className="h-48 flex items-center justify-center text-slate-600 text-sm">
                  No events to display
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie
                      data={statusData.filter(d => d.value > 0)}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      label={({ name, value }) => `${name}: ${value}`}
                      labelLine={false}
                    >
                      {statusData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ background: '#161b27', border: '1px solid #1f2937', borderRadius: '8px', color: '#e2e8f0', fontSize: '12px' }} />
                    <Legend wrapperStyle={{ fontSize: '12px', color: '#94a3b8' }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Note */}
          <div className="text-xs text-slate-600 italic">
            Analytics derive from real database events. No synthetic data is used.
            Additional time-series charts will appear as events are generated in Phase 6+.
          </div>
        </>
      )}
    </div>
  );
}
