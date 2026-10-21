import { useEffect, useState, useRef } from 'react';
import { getVideos, uploadVideo, startProcessing, type Video } from '../services/api';
import {
  Upload,
  Play,
  Clock,
  Film,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Download,
  Eye,
  X,
  RefreshCw,
} from 'lucide-react';

const API_BASE = import.meta.env?.VITE_API_URL ?? 'http://localhost:8000';

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
  const [activeModalVideo, setActiveModalVideo] = useState<{ url: string; title: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => getVideos().then(setVideos).catch(() => {});

  useEffect(() => {
    load();
    const interval = setInterval(load, 3000);
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
          <p className="text-sm text-slate-500 mt-0.5">Upload construction site footage for safety analysis</p>
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
          {videos.map(video => {
            const hasAnnotated = Boolean(video.annotated_video_url);
            const isCompleted = video.job?.status === 'COMPLETED';
            const isRunning = video.job?.status === 'RUNNING';

            return (
              <div key={video.id} className="card space-y-3 flex flex-col justify-between">
                <div className="space-y-3">
                  {/* Thumbnail / Preview Area */}
                  <div
                    className="w-full h-36 bg-surface rounded-lg border border-surface-border flex flex-col items-center justify-center relative overflow-hidden group cursor-pointer"
                    onClick={() => {
                      if (hasAnnotated) {
                        setActiveModalVideo({
                          url: `${API_BASE}${video.annotated_video_url}`,
                          title: `Annotated: ${video.filename}`,
                        });
                      } else {
                        setActiveModalVideo({
                          url: `${API_BASE}/videos/${video.filename}`,
                          title: video.filename,
                        });
                      }
                    }}
                  >
                    <Film size={32} className="text-slate-600 group-hover:text-brand-400 transition-colors" />
                    <span className="text-[11px] text-slate-500 mt-2 flex items-center gap-1 group-hover:text-brand-300">
                      <Play size={10} /> Click to preview
                    </span>
                    {hasAnnotated && (
                      <span className="absolute top-2 right-2 bg-brand-900/80 text-brand-300 border border-brand-700/50 text-[10px] px-1.5 py-0.5 rounded">
                        Annotated ✓
                      </span>
                    )}
                  </div>

                  <div>
                    <p className="font-medium text-slate-200 text-sm truncate" title={video.filename}>
                      {video.filename}
                    </p>
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      {video.duration_seconds && (
                        <span className="metric-pill text-slate-400 text-xs">
                          <Clock size={10} />
                          {video.duration_seconds.toFixed(1)}s
                        </span>
                      )}
                      {video.fps && (
                        <span className="metric-pill text-slate-400 text-xs">
                          {video.fps.toFixed(0)} fps
                        </span>
                      )}
                      {video.width && (
                        <span className="metric-pill text-slate-400 text-xs">
                          {video.width}×{video.height}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Job status */}
                  {video.job && (
                    <div className="bg-surface rounded-lg p-2.5 space-y-1.5 border border-surface-border/50">
                      <div className="flex items-center justify-between">
                        <StatusBadge status={video.job.status} />
                        {video.job.fps_achieved && (
                          <span className="text-xs text-slate-500 font-mono">
                            {video.job.fps_achieved.toFixed(1)} FPS
                          </span>
                        )}
                      </div>
                      {isRunning && video.job.progress !== null && (
                        <div>
                          <div className="h-1 bg-surface-border rounded-full overflow-hidden">
                            <div
                              className="h-full bg-brand-500 rounded-full transition-all duration-300"
                              style={{ width: `${video.job.progress}%` }}
                            />
                          </div>
                          <div className="flex justify-between items-center text-xs text-slate-500 mt-1">
                            <span>Processing frames...</span>
                            <span>{video.job.progress.toFixed(0)}%</span>
                          </div>
                        </div>
                      )}
                      {video.job.error && (
                        <p className="text-xs text-red-400 leading-tight">{video.job.error}</p>
                      )}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="pt-2 border-t border-surface-border/50 space-y-2">
                  {(!video.job || video.job.status === 'FAILED') && (
                    <button
                      className="btn-primary w-full justify-center text-xs py-2"
                      onClick={() => handleProcess(video.id)}
                    >
                      <Play size={13} /> Run Safety Analysis
                    </button>
                  )}

                  {isCompleted && (
                    <div className="space-y-1.5">
                      {hasAnnotated && (
                        <div className="flex gap-2">
                          <button
                            className="btn-primary flex-1 justify-center text-xs py-2"
                            onClick={() => setActiveModalVideo({
                              url: `${API_BASE}${video.annotated_video_url}`,
                              title: `Annotated: ${video.filename}`,
                            })}
                          >
                            <Eye size={13} /> Watch Annotated
                          </button>
                          <a
                            href={`${API_BASE}${video.annotated_video_url}`}
                            download
                            className="btn-ghost px-2.5 py-2 text-xs flex items-center justify-center hover:text-brand-400"
                            title="Download Annotated MP4"
                          >
                            <Download size={13} />
                          </a>
                        </div>
                      )}
                      <button
                        className="btn-ghost w-full justify-center text-xs py-1.5 text-slate-400"
                        onClick={() => handleProcess(video.id)}
                      >
                        <RefreshCw size={11} /> Re-Analyze
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Video Player Modal */}
      {activeModalVideo && (
        <div
          className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setActiveModalVideo(null)}
        >
          <div
            className="card w-full max-w-4xl p-4 bg-slate-900 border border-slate-700 animate-slide-in space-y-3"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-2 border-b border-surface-border">
              <h3 className="font-semibold text-slate-200 text-sm flex items-center gap-2">
                <Film size={16} className="text-brand-400" />
                {activeModalVideo.title}
              </h3>
              <button
                onClick={() => setActiveModalVideo(null)}
                className="p-1 hover:bg-surface-hover rounded text-slate-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>
            <div className="bg-black rounded-lg overflow-hidden aspect-video flex items-center justify-center">
              <video
                src={activeModalVideo.url}
                controls
                autoPlay
                className="w-full h-full object-contain"
              >
                Your browser does not support the video tag.
              </video>
            </div>
            <div className="flex justify-between items-center text-xs text-slate-500 pt-1">
              <span>Playing from VisionSafe media service</span>
              <a
                href={activeModalVideo.url}
                download
                className="text-brand-400 hover:underline flex items-center gap-1"
              >
                <Download size={12} /> Download Video File
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
