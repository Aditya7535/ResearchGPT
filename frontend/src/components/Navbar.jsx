import React from 'react';
import { BookOpen, Sparkles, ShieldCheck, User, Zap } from 'lucide-react';

export default function Navbar({ activeSubscription, onOpenStripe }) {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800 bg-dark-950/80 backdrop-blur-md px-6 py-3.5 flex items-center justify-between">
      <div className="flex items-center space-x-3">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-brand-600 to-blue-400 p-0.5 shadow-glow-blue flex items-center justify-center">
          <div className="h-full w-full bg-dark-950 rounded-[10px] flex items-center justify-center">
            <BookOpen className="h-5 w-5 text-brand-400" />
          </div>
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-lg tracking-tight text-white">Research<span className="text-brand-400">GPT</span></span>
            <span className="text-[10px] uppercase font-mono tracking-wider px-2 py-0.5 rounded-full bg-brand-500/10 border border-brand-500/30 text-brand-400 font-semibold">
              Thesis Engine v2.4
            </span>
          </div>
          <p className="text-xs text-slate-400">Document Assembly & Multi-Agent Intelligence</p>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        {/* Active plan badge */}
        <button
          onClick={onOpenStripe}
          className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-brand-500/40 transition-all text-xs"
        >
          <Zap className="h-3.5 w-3.5 text-yellow-400 fill-yellow-400/20" />
          <span className="text-slate-300">Plan:</span>
          <span className="font-semibold text-brand-400 capitalize">{activeSubscription}</span>
          <span className="text-[10px] text-slate-500 underline ml-1">Manage</span>
        </button>

        {/* System status pill */}
        <div className="hidden lg:flex items-center space-x-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-mono">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>ChromaDB + WeasyPrint Online</span>
        </div>

        {/* User avatar profile */}
        <div className="flex items-center space-x-3 pl-3 border-l border-slate-800">
          <div className="h-8 w-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 text-xs font-semibold">
            JS
          </div>
          <div className="hidden md:block text-left">
            <p className="text-xs font-medium text-slate-200">Jane Smith</p>
            <p className="text-[11px] text-slate-400">Computer Science Ph.D.</p>
          </div>
        </div>
      </div>
    </header>
  );
}
