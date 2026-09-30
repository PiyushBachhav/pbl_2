// VisionSafe API client
// All API calls go through this service

const API_URL = import.meta.env?.VITE_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API error');
  }
  return res.json();
}

// ── Health ─────────────────────────────────────────────────
export const getHealth = () => request<{ status: string; version: string }>('/health');

// ── Analytics ──────────────────────────────────────────────
export const getSummary = () =>
  request<{
    total_events: number;
    open_events: number;
    high_critical_events: number;
    resolved_events: number;
  }>('/api/analytics/summary');

export const getViolationsByType = () =>
  request<{ event_type: string; count: number }[]>('/api/analytics/violations');

// ── Events ─────────────────────────────────────────────────
export interface SafetyEvent {
  id: number;
  event_type: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | 'FALSE_POSITIVE';
  subject_track_id: number | null;
  related_track_id: number | null;
  camera_id: number | null;
  video_id: number | null;
  zone_id: number | null;
  rule_id: number | null;
  started_at: string | null;
  detected_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
  confidence: number | null;
  description: string;
  evidence_frame_path: string | null;
  metadata: Record<string, unknown>;
}

export const getEvents = (params?: {
  severity?: string;
  status?: string;
  event_type?: string;
  camera_id?: number;
  zone_id?: number;
  limit?: number;
  offset?: number;
}) => {
  const q = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) q.set(k, String(v));
    });
  }
  return request<SafetyEvent[]>(`/api/events/?${q.toString()}`);
};

export const updateEventStatus = (id: number, status: string) =>
  request<SafetyEvent>(`/api/events/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });

// ── Videos ─────────────────────────────────────────────────
export interface Video {
  id: number;
  filename: string;
  fps: number | null;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  total_frames: number | null;
  job: {
    status: string | null;
    progress: number | null;
    fps_achieved: number | null;
    error: string | null;
  } | null;
}

export const getVideos = () => request<Video[]>('/api/videos/');

export const uploadVideo = async (file: File): Promise<{ id: number; filename: string }> => {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_URL}/api/videos/`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error('Upload failed');
  return res.json();
};

export const startProcessing = (videoId: number) =>
  request<{ job_id: number; status: string }>(`/api/videos/${videoId}/process`, {
    method: 'POST',
  });

// ── Zones ──────────────────────────────────────────────────
export interface Zone {
  id: number;
  name: string;
  description: string | null;
  camera_id: number | null;
  zone_type: string;
  severity: string;
  polygon: [number, number][];
  required_ppe: string[];
  allowed_roles: string[];
  enabled: boolean;
  color: string;
}

export const getZones = () => request<Zone[]>('/api/zones/');

export const createZone = (data: Partial<Zone>) =>
  request<Zone>('/api/zones/', { method: 'POST', body: JSON.stringify(data) });

export const updateZone = (id: number, data: Partial<Zone>) =>
  request<Zone>(`/api/zones/${id}`, { method: 'PUT', body: JSON.stringify(data) });

export const deleteZone = (id: number) =>
  request<void>(`/api/zones/${id}`, { method: 'DELETE' });

// ── Cameras ────────────────────────────────────────────────
export interface Camera {
  id: number;
  name: string;
  location: string | null;
  description: string | null;
  enabled: boolean;
}

export const getCameras = () => request<Camera[]>('/api/cameras/');

export const createCamera = (data: Partial<Camera>) =>
  request<Camera>('/api/cameras/', { method: 'POST', body: JSON.stringify(data) });

// ── Rules ──────────────────────────────────────────────────
export interface Rule {
  id: number;
  name: string;
  description: string | null;
  rule_type: string;
  enabled: boolean;
  severity: string;
  temporal_threshold_seconds: number;
  conditions: Record<string, unknown>;
}

export const getRules = () => request<Rule[]>('/api/rules/');

export const createRule = (data: Partial<Rule>) =>
  request<Rule>('/api/rules/', { method: 'POST', body: JSON.stringify(data) });

export const updateRule = (id: number, data: Partial<Rule>) =>
  request<Rule>(`/api/rules/${id}`, { method: 'PUT', body: JSON.stringify(data) });
