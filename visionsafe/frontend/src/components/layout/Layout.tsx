import { NavLink, Outlet } from 'react-router-dom';
import {
  LayoutDashboard, AlertTriangle, Video, MapPin, Shield, BarChart3,
  Activity, Zap,
} from 'lucide-react';

const navItems = [
  { to: '/',          icon: LayoutDashboard, label: 'Dashboard',  end: true },
  { to: '/events',    icon: AlertTriangle,   label: 'Events' },
  { to: '/videos',    icon: Video,           label: 'Videos' },
  { to: '/zones',     icon: MapPin,          label: 'Zones' },
  { to: '/rules',     icon: Shield,          label: 'Rules' },
  { to: '/analytics', icon: BarChart3,       label: 'Analytics' },
];

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      {/* ── Sidebar ───────────────────────────────────────────── */}
      <aside className="w-60 flex-shrink-0 glass border-r border-surface-border flex flex-col">
        {/* Logo */}
        <div className="flex items-center gap-3 px-6 py-5 border-b border-surface-border">
          <div className="relative">
            <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center glow-brand">
              <Zap size={16} className="text-white" />
            </div>
            <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-green-400 rounded-full border border-surface animate-pulse" />
          </div>
          <div>
            <div className="font-bold text-sm text-gradient">VisionSafe</div>
            <div className="text-xs text-slate-500">Safety Platform</div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-150
                 ${isActive
                   ? 'bg-brand-600/20 text-brand-400 border border-brand-600/30'
                   : 'text-slate-400 hover:text-slate-100 hover:bg-surface-hover'
                 }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-surface-border">
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <Activity size={12} className="text-green-500" />
            <span>System Active</span>
          </div>
          <div className="text-xs text-slate-700 mt-1">v0.1.0 · Phase 1–2</div>
        </div>
      </aside>

      {/* ── Main content ──────────────────────────────────────── */}
      <main className="flex-1 overflow-auto">
        <div className="min-h-full p-6 animate-fade-in">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
