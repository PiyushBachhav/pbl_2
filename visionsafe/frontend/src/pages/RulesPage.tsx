import { useEffect, useState } from 'react';
import { getRules, createRule, updateRule, type Rule } from '../services/api';
import { Shield, Plus, ToggleRight, ToggleLeft } from 'lucide-react';

const RULE_TYPES = ['NO_HELMET', 'NO_VEST', 'RESTRICTED_ZONE_ENTRY', 'FORKLIFT_PROXIMITY', 'PERSISTENT_PPE_VIOLATION'];
const SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

const severityColor: Record<string, string> = {
  LOW: 'badge-low', MEDIUM: 'badge-medium', HIGH: 'badge-high', CRITICAL: 'badge-critical',
};

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Partial<Rule>>({
    name: '', rule_type: 'NO_HELMET', severity: 'HIGH',
    enabled: true, temporal_threshold_seconds: 2.0,
  });
  const [saving, setSaving] = useState(false);

  const load = () => getRules().then(setRules).catch(() => {});
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    if (!form.name?.trim()) return;
    setSaving(true);
    try {
      await createRule(form);
      setShowForm(false);
      await load();
    } finally {
      setSaving(false);
    }
  };

  const toggleRule = async (rule: Rule) => {
    await updateRule(rule.id, { ...rule, enabled: !rule.enabled }).catch(() => {});
    await load();
  };

  const ruleTypeLabel: Record<string, string> = {
    NO_HELMET: 'Helmet required',
    NO_VEST: 'Vest required',
    RESTRICTED_ZONE_ENTRY: 'Restricted zone entry',
    FORKLIFT_PROXIMITY: 'Forklift proximity',
    PERSISTENT_PPE_VIOLATION: 'Persistent PPE violation',
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Safety Rules</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Rules determine what constitutes a safety violation — YOLO only detects objects
          </p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(v => !v)}>
          <Plus size={16} /> New Rule
        </button>
      </div>

      {/* Architecture principle callout */}
      <div className="card border-brand-900/30 bg-brand-950/10 text-xs text-slate-500 leading-relaxed">
        <Shield size={12} className="inline mr-2 text-brand-400" />
        <strong className="text-brand-400">Architecture principle:</strong> YOLO detects objects.
        Rules determine danger. This separation keeps the safety engine deterministic and auditable.
        Each rule has a temporal persistence threshold — a single frame never generates an event.
      </div>

      {showForm && (
        <div className="card border-brand-800/40 space-y-4 animate-fade-in">
          <h2 className="text-sm font-semibold text-brand-400">New Rule</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Rule Name *</label>
              <input className="input" placeholder="e.g. Helmet required in excavation zone"
                value={form.name || ''} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Rule Type</label>
              <select className="input" value={form.rule_type}
                onChange={e => setForm(f => ({ ...f, rule_type: e.target.value }))}>
                {RULE_TYPES.map(t => <option key={t} value={t}>{ruleTypeLabel[t] || t}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Severity</label>
              <select className="input" value={form.severity}
                onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}>
                {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">
                Persistence threshold (seconds)
              </label>
              <input type="number" className="input" min={0.5} step={0.5}
                value={form.temporal_threshold_seconds || 2}
                onChange={e => setForm(f => ({ ...f, temporal_threshold_seconds: parseFloat(e.target.value) }))} />
              <p className="text-xs text-slate-600 mt-1">
                Violation must persist this long before an event is created.
              </p>
            </div>
          </div>
          <div className="flex gap-3">
            <button className="btn-primary" onClick={handleCreate} disabled={saving || !form.name?.trim()}>
              {saving ? 'Saving…' : 'Create Rule'}
            </button>
            <button className="btn-ghost" onClick={() => setShowForm(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {rules.length === 0 ? (
          <div className="card text-center py-12 text-slate-600">
            <Shield size={32} className="mx-auto mb-3 opacity-30" />
            No rules configured. Create your first rule above.
          </div>
        ) : rules.map(rule => (
          <div key={rule.id} className="card flex items-start justify-between gap-4">
            <div className="flex items-start gap-3 min-w-0">
              <div className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${rule.enabled ? 'bg-green-400' : 'bg-slate-600'}`} />
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <p className="font-medium text-slate-200 text-sm">{rule.name}</p>
                  <span className={severityColor[rule.severity] || ''}>{rule.severity}</span>
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-slate-500 font-mono">{rule.rule_type}</span>
                  <span className="text-xs text-slate-600">
                    Persistence: {rule.temporal_threshold_seconds}s
                  </span>
                </div>
                {rule.description && (
                  <p className="text-xs text-slate-600 mt-1">{rule.description}</p>
                )}
              </div>
            </div>
            <button
              className="flex-shrink-0 p-1 hover:bg-surface-hover rounded transition-colors"
              onClick={() => toggleRule(rule)}
              title={rule.enabled ? 'Disable' : 'Enable'}
            >
              {rule.enabled
                ? <ToggleRight size={20} className="text-green-400" />
                : <ToggleLeft size={20} className="text-slate-600" />
              }
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
