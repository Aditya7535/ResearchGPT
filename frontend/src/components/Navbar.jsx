import React, { useState, useEffect } from 'react';
import { BookOpen, Sparkles, ShieldCheck, User, Zap, Activity } from 'lucide-react';
import { checkHealth } from '../services/api';

export default function Navbar({ activeSubscription, onOpenStripe }) {
  const [backendHealth, setBackendHealth] = useState({ online: false, checking: true });

  useEffect(() => {
    let isMounted = true;
    async function verify() {
      try {
        const res = await checkHealth();
        if (isMounted) {
          setBackendHealth({ online: res.online, checking: false, ...res });
        }
      } catch (e) {
        if (isMounted) setBackendHealth({ online: false, checking: false });
      }
    }
    verify();
    const interval = setInterval(verify, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800 bg-dark-950/90 backdrop-blur-md px-6 py-3 flex items-center justify-between">
      {/* Brand Logo & Title */}
      <div className="flex items-center space-x-3.5">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-brand-600 to-blue-400 p-0.5 shadow-glow-blue flex items-center justify-center shrink-0">
          <div className="h-full w-full bg-dark-950 rounded-[10px] flex items-center justify-center">
            <BookOpen className="h-5 w-5 text-brand-400" />
          </div>
        </div>
        <div>
          <div className="flex items-center space-x-2.5">
            <span className="font-bold text-lg tracking-tight text-white leading-none">
              Research<span className="text-brand-400">GPT</span>
            </span>
            <span className="text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded-full bg-brand-500/10 border border-brand-500/30 text-brand-400 font-semibold leading-none">
              Thesis Engine v2.4
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 leading-none">Document Assembly & Multi-Agent Intelligence</p>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center space-x-3 sm:space-x-4">
        {/* Active plan badge */}
        <button
          onClick={onOpenStripe}
          className="hidden sm:inline-flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-brand-500/40 transition-all text-xs"
          title="Manage Subscription"
        >
          <Zap className="h-3.5 w-3.5 text-yellow-400 fill-yellow-400/20" />
          <span className="text-slate-300">Plan:</span>
          <span className="font-semibold text-brand-400 capitalize">{activeSubscription}</span>
          <span className="text-[10px] text-slate-500 underline ml-1">Manage</span>
        </button>

        {/* Dynamic System status pill */}
        <div className={`hidden lg:inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-mono border ${
          backendHealth.online
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
            : backendHealth.checking
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
            : 'bg-slate-800/80 border-slate-700 text-slate-400'
        }`}>
          <span className={`h-2 w-2 rounded-full ${
            backendHealth.online
              ? 'bg-emerald-400 animate-pulse'
              : backendHealth.checking
              ? 'bg-amber-400 animate-ping'
              : 'bg-slate-500'
          }`} />
          <span>
            {backendHealth.online
              ? 'ChromaDB + WeasyPrint Online'
              : backendHealth.checking
              ? 'Connecting to Backend...'
              : 'ChromaDB (Local Mode)'}
          </span>
        </div>

        {/* User profile avatar */}
        <div className="flex items-center space-x-3 pl-3 border-l border-slate-800">
          <div className="h-9 w-9 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-200 text-xs font-bold shadow-inner shrink-0">
            JS
          </div>
          <div className="hidden md:block text-left">
            <p className="text-xs font-semibold text-slate-200 leading-tight">Jane Smith</p>
            <p className="text-[11px] text-slate-400 leading-tight mt-0.5">Computer Science Ph.D.</p>
          </div>
        </div>
      </div>
    </header>
  );
}
