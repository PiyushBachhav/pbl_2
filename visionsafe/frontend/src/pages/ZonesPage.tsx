import { useEffect, useState } from 'react';
import { getZones, createZone, deleteZone, type Zone } from '../services/api';
import { MapPin, Plus, Trash2, ToggleLeft, ToggleRight } from 'lucide-react';

const ZONE_TYPES = ['restricted', 'ppe_required', 'forklift', 'caution', 'safe'];
const SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const PPE_OPTIONS = ['helmet', 'vest'];

const DEFAULT_ZONE: Partial<Zone> = {
  name: '',
  zone_type: 'restricted',
  severity: 'HIGH',
  polygon: [],
  required_ppe: ['helmet', 'vest'],
  enabled: true,
  color: '#ef4444',
};

export default function ZonesPage() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Partial<Zone>>(DEFAULT_ZONE);
  const [polygonText, setPolygonText] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = () => getZones().then(setZones).catch(() => {});
  useEffect(() => { load(); }, []);

  const handleCreate = async () => {
    setError('');
    let polygon: [number, number][] = [];
    try {
      polygon = JSON.parse(polygonText);
      if (!Array.isArray(polygon) || polygon.length < 3) throw new Error();
    } catch {
      setError('Polygon must be a JSON array of at least 3 [x, y] pairs.\nExample: [[10,10],[200,10],[200,200],[10,200]]');
      return;
    }

    if (!form.name?.trim()) { setError('Zone name is required.'); return; }

    setSaving(true);
    try {
      await createZone({ ...form, polygon });
      setShowForm(false);
      setForm(DEFAULT_ZONE);
      setPolygonText('');
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create zone');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this zone?')) return;
    await deleteZone(id).catch(() => {});
    await load();
  };

  const severityColor: Record<string, string> = {
    LOW: 'text-green-400', MEDIUM: 'text-amber-400',
    HIGH: 'text-red-400', CRITICAL: 'text-red-300',
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Safety Zones</h1>
          <p className="text-sm text-slate-500 mt-0.5">Configure polygon safety zones for cameras</p>
        </div>
        <button className="btn-primary" onClick={() => setShowForm(v => !v)}>
          <Plus size={16} /> New Zone
        </button>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="card border-brand-800/40 space-y-4 animate-fade-in">
          <h2 className="text-sm font-semibold text-brand-400 flex items-center gap-2">
            <MapPin size={14} /> Define New Zone
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Zone Name *</label>
              <input
                className="input"
                placeholder="e.g. Excavation Area"
                value={form.name || ''}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Zone Type</label>
              <select
                className="input"
                value={form.zone_type}
                onChange={e => setForm(f => ({ ...f, zone_type: e.target.value }))}
              >
                {ZONE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Severity</label>
              <select
                className="input"
                value={form.severity}
                onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}
              >
                {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Color</label>
              <input
                type="color"
                className="h-10 w-full rounded-lg border border-surface-border bg-surface cursor-pointer"
                value={form.color || '#ef4444'}
                onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-500 mb-1 block">Required PPE</label>
            <div className="flex gap-4">
              {PPE_OPTIONS.map(ppe => (
                <label key={ppe} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.required_ppe?.includes(ppe)}
                    onChange={e => setForm(f => ({
                      ...f,
                      required_ppe: e.target.checked
                        ? [...(f.required_ppe || []), ppe]
                        : (f.required_ppe || []).filter(p => p !== ppe),
                    }))}
                    className="accent-brand-500"
                  />
                  <span className="text-sm text-slate-300 capitalize">{ppe}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-500 mb-1 block">
              Polygon Points (JSON) *
            </label>
            <textarea
              className="input font-mono text-xs h-24 resize-none"
              placeholder='[[100,50],[400,50],[400,300],[100,300]]'
              value={polygonText}
              onChange={e => setPolygonText(e.target.value)}
            />
            <p className="text-xs text-slate-600 mt-1">
              Enter pixel coordinates as JSON array of [x, y] pairs. Minimum 3 points.
              In Phase 5, you'll be able to draw zones interactively on the camera frame.
            </p>
          </div>

          {error && (
            <div className="text-red-400 text-xs bg-red-950/20 border border-red-800/30 rounded-lg p-3 whitespace-pre-line">{error}</div>
          )}

          <div className="flex gap-3">
            <button className="btn-primary" onClick={handleCreate} disabled={saving}>
              {saving ? 'Saving…' : 'Create Zone'}
            </button>
            <button className="btn-ghost" onClick={() => { setShowForm(false); setError(''); }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Zone list */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {zones.length === 0 ? (
          <div className="card col-span-full text-center py-12 text-slate-600">
            <MapPin size={32} className="mx-auto mb-3 opacity-30" />
            No zones configured. Create your first zone above.
          </div>
        ) : zones.map(zone => (
          <div key={zone.id} className="card space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ background: zone.color }}
                />
                <h3 className="font-semibold text-slate-200 text-sm">{zone.name}</h3>
              </div>
              <div className="flex items-center gap-1">
                <span className={`text-xs font-medium ${severityColor[zone.severity]}`}>
                  {zone.severity}
                </span>
                <button
                  className="p-1 hover:bg-surface-hover rounded text-slate-600 hover:text-red-400"
                  onClick={() => handleDelete(zone.id)}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>

            <div className="flex gap-2 flex-wrap">
              <span className="badge-low text-xs">{zone.zone_type}</span>
              {zone.required_ppe.map(p => (
                <span key={p} className="inline-flex px-1.5 py-0.5 bg-brand-900/30 text-brand-400 text-xs rounded border border-brand-800/30">{p}</span>
              ))}
            </div>

            <div className="text-xs text-slate-500 font-mono bg-surface rounded p-2">
              {zone.polygon.length} polygon points
            </div>

            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              {zone.enabled
                ? <><ToggleRight size={14} className="text-green-400" /> Enabled</>
                : <><ToggleLeft size={14} className="text-slate-600" /> Disabled</>
              }
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
