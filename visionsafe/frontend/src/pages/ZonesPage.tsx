import { useEffect, useState, useRef } from 'react';
import { getZones, createZone, deleteZone, type Zone } from '../services/api';
import {
  MapPin,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  MousePointer,
  RotateCcw,
  Check,
  Sparkles,
  Layers,
} from 'lucide-react';

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

const CANVAS_WIDTH = 640;
const CANVAS_HEIGHT = 360;

export default function ZonesPage() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<Partial<Zone>>(DEFAULT_ZONE);
  const [polygon, setPolygon] = useState<[number, number][]>([]);
  const [polygonClosed, setPolygonClosed] = useState(false);
  const [mousePos, setMousePos] = useState<[number, number] | null>(null);
  const [jsonMode, setJsonMode] = useState(false);
  const [polygonText, setPolygonText] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const load = () => getZones().then(setZones).catch(() => {});
  useEffect(() => { load(); }, []);

  // Sync drawn polygon with text representation
  useEffect(() => {
    setPolygonText(JSON.stringify(polygon));
  }, [polygon]);

  // Redraw canvas whenever polygon, cursor, or zone list changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear background
    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

    // Draw grid
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    const gridSize = 40;
    for (let x = 0; x < CANVAS_WIDTH; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, CANVAS_HEIGHT);
      ctx.stroke();
    }
    for (let y = 0; y < CANVAS_HEIGHT; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(CANVAS_WIDTH, y);
      ctx.stroke();
    }

    // Draw existing zones in background
    zones.forEach(z => {
      if (!z.polygon || z.polygon.length < 3) return;
      ctx.beginPath();
      ctx.moveTo(z.polygon[0][0], z.polygon[0][1]);
      for (let i = 1; i < z.polygon.length; i++) {
        ctx.lineTo(z.polygon[i][0], z.polygon[i][1]);
      }
      ctx.closePath();
      ctx.fillStyle = (z.color || '#ef4444') + '22';
      ctx.fill();
      ctx.strokeStyle = (z.color || '#ef4444') + '88';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Label at first point
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px monospace';
      ctx.fillText(z.name, z.polygon[0][0] + 4, z.polygon[0][1] - 4);
    });

    // Draw current in-progress polygon
    if (polygon.length > 0) {
      ctx.beginPath();
      ctx.moveTo(polygon[0][0], polygon[0][1]);
      for (let i = 1; i < polygon.length; i++) {
        ctx.lineTo(polygon[i][0], polygon[i][1]);
      }

      if (polygonClosed) {
        ctx.closePath();
        ctx.fillStyle = (form.color || '#ef4444') + '44';
        ctx.fill();
        ctx.strokeStyle = form.color || '#ef4444';
        ctx.lineWidth = 2.5;
        ctx.stroke();
      } else {
        // Line in progress
        ctx.strokeStyle = form.color || '#ef4444';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Guide line to cursor
        if (mousePos) {
          ctx.beginPath();
          ctx.setLineDash([4, 4]);
          ctx.moveTo(polygon[polygon.length - 1][0], polygon[polygon.length - 1][1]);
          ctx.lineTo(mousePos[0], mousePos[1]);
          ctx.strokeStyle = '#38bdf8';
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      // Draw vertex handles
      polygon.forEach(([px, py], idx) => {
        ctx.beginPath();
        ctx.arc(px, py, idx === 0 ? 6 : 4, 0, Math.PI * 2);
        ctx.fillStyle = idx === 0 ? '#38bdf8' : (form.color || '#ef4444');
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Point index
        ctx.fillStyle = '#ffffff';
        ctx.font = '9px monospace';
        ctx.fillText(`P${idx + 1}`, px + 8, py - 4);
      });
    }
  }, [polygon, polygonClosed, mousePos, form.color, zones]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (polygonClosed) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);

    // If clicking near first point and have >= 3 points, close it
    if (polygon.length >= 3) {
      const [firstX, firstY] = polygon[0];
      const dist = Math.hypot(x - firstX, y - firstY);
      if (dist < 15) {
        setPolygonClosed(true);
        return;
      }
    }

    setPolygon(prev => [...prev, [x, y]]);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (polygonClosed) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);
    setMousePos([x, y]);
  };

  const handleClosePolygon = () => {
    if (polygon.length >= 3) {
      setPolygonClosed(true);
    }
  };

  const handleUndoPoint = () => {
    setPolygon(prev => prev.slice(0, -1));
    setPolygonClosed(false);
  };

  const handleClearCanvas = () => {
    setPolygon([]);
    setPolygonClosed(false);
  };

  const applyPreset = (presetPoints: [number, number][], defaultName: string, type: string, color: string) => {
    setPolygon(presetPoints);
    setPolygonClosed(true);
    setForm(f => ({
      ...f,
      name: f.name || defaultName,
      zone_type: type,
      color: color,
    }));
  };

  const handleCreate = async () => {
    setError('');
    let finalPoly: [number, number][] = polygon;

    if (jsonMode) {
      try {
        finalPoly = JSON.parse(polygonText);
        if (!Array.isArray(finalPoly) || finalPoly.length < 3) throw new Error();
      } catch {
        setError('Polygon must be a valid JSON array of at least 3 [x, y] coordinates.');
        return;
      }
    } else {
      if (finalPoly.length < 3) {
        setError('Please place at least 3 points on the canvas and close the polygon.');
        return;
      }
    }

    if (!form.name?.trim()) {
      setError('Zone name is required.');
      return;
    }

    setSaving(true);
    try {
      await createZone({ ...form, polygon: finalPoly });
      setShowForm(false);
      setForm(DEFAULT_ZONE);
      setPolygon([]);
      setPolygonClosed(false);
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
    LOW: 'text-green-400',
    MEDIUM: 'text-amber-400',
    HIGH: 'text-red-400',
    CRITICAL: 'text-red-300',
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Safety Zones</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Interactive visual polygon safety zone designer for video streams
          </p>
        </div>
        <button
          className="btn-primary"
          onClick={() => {
            setShowForm(v => !v);
            if (!showForm) {
              setPolygon([]);
              setPolygonClosed(false);
            }
          }}
        >
          <Plus size={16} /> {showForm ? 'Close Designer' : 'New Zone'}
        </button>
      </div>

      {/* Interactive Zone Creator */}
      {showForm && (
        <div className="card border-brand-800/40 space-y-5 animate-fade-in">
          <div className="flex items-center justify-between pb-3 border-b border-surface-border">
            <h2 className="text-sm font-semibold text-brand-400 flex items-center gap-2">
              <MapPin size={16} /> Interactive Zone Designer
            </h2>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className={`text-xs px-2.5 py-1 rounded transition-colors ${!jsonMode ? 'bg-brand-600 text-white' : 'btn-ghost'}`}
                onClick={() => setJsonMode(false)}
              >
                <MousePointer size={12} className="inline mr-1" /> Canvas Tool
              </button>
              <button
                type="button"
                className={`text-xs px-2.5 py-1 rounded transition-colors ${jsonMode ? 'bg-brand-600 text-white' : 'btn-ghost'}`}
                onClick={() => setJsonMode(true)}
              >
                <Layers size={12} className="inline mr-1" /> Raw Coordinates
              </button>
            </div>
          </div>

          {/* Form Fields */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Zone Name *</label>
              <input
                className="input"
                placeholder="e.g. Danger Excavation Area"
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
              <label className="text-xs text-slate-500 mb-1 block">Zone Color</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  className="h-9 w-12 rounded border border-surface-border bg-surface cursor-pointer p-0"
                  value={form.color || '#ef4444'}
                  onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                />
                <input
                  type="text"
                  className="input font-mono text-xs flex-1"
                  value={form.color || '#ef4444'}
                  onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                />
              </div>
            </div>
          </div>

          {/* Canvas or JSON Editor */}
          {!jsonMode ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>Click on the canvas to place polygon vertices. Click near the blue starting point or 'Close Polygon' when done.</span>
                <span className="font-mono text-brand-400">
                  {polygon.length} points placed {polygonClosed ? '(Closed ✓)' : ''}
                </span>
              </div>

              {/* Canvas viewport */}
              <div className="relative border border-surface-border rounded-lg overflow-hidden bg-slate-950 flex justify-center items-center">
                <canvas
                  ref={canvasRef}
                  width={CANVAS_WIDTH}
                  height={CANVAS_HEIGHT}
                  onClick={handleCanvasClick}
                  onMouseMove={handleMouseMove}
                  onMouseLeave={() => setMousePos(null)}
                  className={`max-w-full h-auto cursor-crosshair ${polygonClosed ? 'cursor-default' : ''}`}
                />
                {!polygonClosed && polygon.length === 0 && (
                  <div className="absolute inset-0 pointer-events-none flex items-center justify-center text-slate-600 text-xs">
                    Click anywhere to start drawing polygon vertices
                  </div>
                )}
              </div>

              {/* Drawing Toolbar & Presets */}
              <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    className="btn-ghost text-xs py-1.5"
                    onClick={handleUndoPoint}
                    disabled={polygon.length === 0}
                  >
                    <RotateCcw size={12} /> Undo Point
                  </button>
                  <button
                    type="button"
                    className="btn-ghost text-xs py-1.5"
                    onClick={handleClearCanvas}
                    disabled={polygon.length === 0}
                  >
                    Clear Canvas
                  </button>
                  <button
                    type="button"
                    className={`btn-primary text-xs py-1.5 ${polygon.length >= 3 && !polygonClosed ? 'ring-2 ring-brand-500' : ''}`}
                    onClick={handleClosePolygon}
                    disabled={polygon.length < 3 || polygonClosed}
                  >
                    <Check size={12} /> Close Polygon
                  </button>
                </div>

                {/* Instant Presets */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-slate-500 flex items-center gap-1">
                    <Sparkles size={12} /> Presets:
                  </span>
                  <button
                    type="button"
                    className="btn-ghost text-xs py-1 px-2 text-slate-400 hover:text-slate-200"
                    onClick={() => applyPreset([[40, 40], [220, 40], [220, 320], [40, 320]], 'Loading Dock (Left)', 'restricted', '#ef4444')}
                  >
                    Left Bay
                  </button>
                  <button
                    type="button"
                    className="btn-ghost text-xs py-1 px-2 text-slate-400 hover:text-slate-200"
                    onClick={() => applyPreset([[250, 30], [390, 30], [390, 330], [250, 330]], 'Forklift Corridor', 'forklift', '#f59e0b')}
                  >
                    Forklift Lane
                  </button>
                  <button
                    type="button"
                    className="btn-ghost text-xs py-1 px-2 text-slate-400 hover:text-slate-200"
                    onClick={() => applyPreset([[420, 70], [600, 70], [600, 290], [420, 290]], 'PPE Mandatory Area', 'ppe_required', '#3b82f6')}
                  >
                    PPE Zone
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div>
              <label className="text-xs text-slate-500 mb-1 block">Polygon Coordinates JSON</label>
              <textarea
                className="input font-mono text-xs h-28 resize-none"
                placeholder='[[100,50],[400,50],[400,300],[100,300]]'
                value={polygonText}
                onChange={e => {
                  setPolygonText(e.target.value);
                  try {
                    const parsed = JSON.parse(e.target.value);
                    if (Array.isArray(parsed)) {
                      setPolygon(parsed);
                      setPolygonClosed(true);
                    }
                  } catch {}
                }}
              />
            </div>
          )}

          {/* Required PPE */}
          <div>
            <label className="text-xs text-slate-500 mb-1 block">Required PPE Items inside Zone</label>
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

          {error && (
            <div className="text-red-400 text-xs bg-red-950/20 border border-red-800/30 rounded-lg p-3 whitespace-pre-line">
              {error}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button className="btn-primary" onClick={handleCreate} disabled={saving}>
              {saving ? 'Saving…' : 'Save Zone'}
            </button>
            <button
              className="btn-ghost"
              onClick={() => {
                setShowForm(false);
                setError('');
              }}
            >
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
            No zones configured. Click "New Zone" above to define safety polygons.
          </div>
        ) : zones.map(zone => (
          <div key={zone.id} className="card space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="w-3.5 h-3.5 rounded-full flex-shrink-0"
                  style={{ background: zone.color }}
                />
                <h3 className="font-semibold text-slate-200 text-sm">{zone.name}</h3>
              </div>
              <div className="flex items-center gap-1.5">
                <span className={`text-xs font-semibold ${severityColor[zone.severity]}`}>
                  {zone.severity}
                </span>
                <button
                  className="p-1 hover:bg-surface-hover rounded text-slate-600 hover:text-red-400 transition-colors"
                  onClick={() => handleDelete(zone.id)}
                  title="Delete Zone"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>

            <div className="flex gap-2 flex-wrap">
              <span className="badge-low text-xs">{zone.zone_type}</span>
              {zone.required_ppe.map(p => (
                <span key={p} className="inline-flex px-1.5 py-0.5 bg-brand-900/30 text-brand-400 text-xs rounded border border-brand-800/30">
                  {p}
                </span>
              ))}
            </div>

            <div className="text-xs text-slate-500 font-mono bg-surface rounded p-2 flex items-center justify-between">
              <span>{zone.polygon.length} polygon vertices</span>
              <span className="text-slate-600">ID #{zone.id}</span>
            </div>

            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              {zone.enabled
                ? <><ToggleRight size={14} className="text-green-400" /> Active</>
                : <><ToggleLeft size={14} className="text-slate-600" /> Disabled</>
              }
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
