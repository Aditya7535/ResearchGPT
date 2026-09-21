import React from 'react';
import { 
  UploadCloud, 
  LayoutDashboard, 
  ListTree, 
  Quote, 
  FileCheck2, 
  CreditCard,
  ChevronRight,
  Sparkles
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, counts }) {
  const navItems = [
    {
      id: 'upload',
      label: 'Document Ingestion',
      icon: UploadCloud,
      badge: counts.documents ? `${counts.documents} files` : null,
      desc: 'Upload PDF / DOCX'
    },
    {
      id: 'dashboard',
      label: 'Section Dashboard',
      icon: LayoutDashboard,
      badge: counts.chunks ? `${counts.chunks} chunks` : null,
      desc: 'Ingested content & vectors'
    },
    {
      id: 'outline',
      label: 'Outline Reviewer',
      icon: ListTree,
      badge: 'Agent Ready',
      badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      desc: 'Thesis structure & prompts'
    },
    {
      id: 'citation',
      label: 'Citation Style',
      icon: Quote,
      badge: counts.citations ? `${counts.citations} refs` : null,
      desc: 'APA, Vancouver, IEEE'
    },
    {
      id: 'export',
      label: 'Export Thesis',
      icon: FileCheck2,
      badge: 'Word + PDF',
      badgeColor: 'bg-brand-500/10 text-brand-400 border-brand-500/30',
      desc: 'Assembler & Matplotlib'
    },
    {
      id: 'subscription',
      label: 'Billing & Plan',
      icon: CreditCard,
      badge: 'Stripe',
      desc: 'Upgrade to PRO'
    }
  ];

  return (
    <aside className="w-72 bg-dark-900 border-r border-slate-800 flex flex-col justify-between h-[calc(100vh-65px)] sticky top-[65px] shrink-0">
      <div className="p-4 space-y-1.5 overflow-y-auto">
        <div className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Navigation
        </div>

        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full text-left flex items-start space-x-3 px-3.5 py-3 rounded-xl transition-all duration-200 group relative ${
                isActive
                  ? 'bg-brand-600/15 border border-brand-500/40 text-white shadow-glow-blue'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent'
              }`}
            >
              {isActive && (
                <div className="absolute left-0 top-2 bottom-2 w-1 bg-brand-500 rounded-r-full shadow-glow-blue" />
              )}
              
              <Icon className={`h-5 w-5 mt-0.5 shrink-0 transition-colors ${
                isActive ? 'text-brand-400' : 'text-slate-400 group-hover:text-slate-300'
              }`} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-sm font-medium whitespace-nowrap ${
                    isActive ? 'text-white font-semibold' : ''
                  }`}>
                    {item.label}
                  </span>

                  {item.badge && (
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded border whitespace-nowrap shrink-0 ${
                      item.badgeColor || (isActive 
                        ? 'bg-brand-500/20 text-brand-300 border-brand-400/30' 
                        : 'bg-slate-800 text-slate-400 border-slate-700')
                    }`}>
                      {item.badge}
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-400 truncate mt-0.5">{item.desc}</p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer info box */}
      <div className="p-4 border-t border-slate-800/80">
        <div className="rounded-xl bg-gradient-to-b from-slate-900 to-dark-850 p-3.5 border border-slate-800 text-xs">
          <div className="flex items-center space-x-2 text-brand-400 font-semibold mb-1">
            <Sparkles className="h-4 w-4" />
            <span>Multi-Agent Engine</span>
          </div>
          <p className="text-slate-400 text-[11px] leading-relaxed">
            Structuring, Citation, Formatting & Plagiarism agents ready.
          </p>
        </div>
      </div>
    </aside>
  );
}
