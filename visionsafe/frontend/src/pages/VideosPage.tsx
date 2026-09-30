import { useEffect, useState, useRef } from 'react';
import { getVideos, uploadVideo, startProcessing, type Video } from '../services/api';
import { Upload, Play, Clock, Film, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-slate-600 text-xs">—</span>;
  const map: Record<string, string> = {
    PENDING: 'text-slate-400 bg-slate-800',
    RUNNING: 'text-blue-400 bg-blue-900/40',
    COMPLETED: 'text-green-400 bg-green-900/40',
    FAILED: 'text-red-400 bg-red-900/40',
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${map[status] || ''}`}>
      {status === 'RUNNING' && <Loader2 size={10} className="animate-spin" />}
      {status === 'COMPLETED' && <CheckCircle2 size={10} />}
      {status === 'FAILED' && <AlertCircle size={10} />}
      {status}
    </span>
  );
}

export default function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => getVideos().then(setVideos).catch(() => {});

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError('');
    try {
      await uploadVideo(file);
      await load();
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleProcess = async (videoId: number) => {
    try {
      await startProcessing(videoId);
      await load();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : 'Failed to start processing');
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Videos</h1>
          <p className="text-sm text-slate-500 mt-0.5">Upload MP4 files for safety analysis</p>
        </div>
        <div>
          <input
            ref={fileRef}
            type="file"
            accept="video/mp4,video/avi,video/quicktime,video/x-matroska"
            className="hidden"
            onChange={handleUpload}
            id="video-upload"
          />
          <label htmlFor="video-upload">
            <span className={`btn-primary cursor-pointer ${uploading ? 'opacity-50 cursor-not-allowed' : ''}`}>
              {uploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              {uploading ? 'Uploading…' : 'Upload Video'}
            </span>
          </label>
        </div>
      </div>

      {uploadError && (
        <div className="card border-red-800/50 bg-red-950/20 text-red-300 text-sm flex items-center gap-2">
          <AlertCircle size={16} /> {uploadError}
        </div>
      )}

      {/* Video grid */}
      {videos.length === 0 ? (
        <div className="card flex flex-col items-center justify-center py-16 gap-4">
          <div className="w-16 h-16 rounded-2xl bg-surface flex items-center justify-center border border-surface-border">
            <Film size={28} className="text-slate-600" />
          </div>
          <div className="text-center">
            <p className="text-slate-400 font-medium">No videos uploaded yet</p>
            <p className="text-slate-600 text-sm mt-1">Upload a construction site video to begin analysis</p>
          </div>
          <label htmlFor="video-upload" className="btn-primary cursor-pointer">
            <Upload size={16} /> Upload your first video
          </label>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {videos.map(video => (
            <div key={video.id} className="card space-y-3">
              {/* Thumbnail placeholder */}
              <div className="w-full h-36 bg-surface rounded-lg border border-surface-border flex items-center justify-center">
                <Film size={32} className="text-slate-600" />
              </div>

              <div>
                <p className="font-medium text-slate-200 text-sm truncate">{video.filename}</p>
                <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                  {video.duration_seconds && (
                    <span className="metric-pill text-slate-400">
                      <Clock size={10} />
                      {video.duration_seconds.toFixed(1)}s
                    </span>
                  )}
                  {video.fps && (
                    <span className="metric-pill text-slate-400">
                      {video.fps.toFixed(0)} fps
                    </span>
                  )}
                  {video.width && (
                    <span className="metric-pill text-slate-400">
                      {video.width}×{video.height}
                    </span>
                  )}
                </div>
              </div>

              {/* Job status */}
              {video.job && (
                <div className="bg-surface rounded-lg p-2.5 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <StatusBadge status={video.job.status} />
                    {video.job.fps_achieved && (
                      <span className="text-xs text-slate-500 font-mono">
                        {video.job.fps_achieved.toFixed(1)} FPS
                      </span>
                    )}
                  </div>
                  {video.job.status === 'RUNNING' && video.job.progress !== null && (
                    <div>
                      <div className="h-1 bg-surface-border rounded-full overflow-hidden">
                        <div
                          className="h-full bg-brand-600 rounded-full transition-all duration-500"
                          style={{ width: `${video.job.progress}%` }}
                        />
                      </div>
                      <p className="text-xs text-slate-600 mt-1">{video.job.progress.toFixed(0)}%</p>
                    </div>
                  )}
                  {video.job.error && (
                    <p className="text-xs text-red-400">{video.job.error}</p>
                  )}
                </div>
              )}

              {/* Actions */}
              {(!video.job || video.job.status === 'FAILED') && (
                <button
                  className="btn-primary w-full justify-center text-sm"
                  onClick={() => handleProcess(video.id)}
                >
                  <Play size={14} /> Analyze Video
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
