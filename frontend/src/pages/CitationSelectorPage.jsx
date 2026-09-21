import React, { useState } from 'react';
import { 
  Quote, 
  Check, 
  Upload, 
  Search, 
  ExternalLink, 
  Sparkles, 
  BookOpen,
  ArrowRight,
  Globe,
  RefreshCw
} from 'lucide-react';
import { MOCK_CITATION_STYLES, MOCK_BIBLIOGRAPHY } from '../mockData';

export default function CitationSelectorPage({ 
  selectedStyle, 
  setSelectedStyle, 
  bibliography, 
  setBibliography,
  onNavigateExport 
}) {
  const [doiQuery, setDoiQuery] = useState('');
  const [isFetchingDoi, setIsFetchingDoi] = useState(false);
  const [doiStatus, setDoiStatus] = useState(null);

  const handleFetchDoi = (e) => {
    e.preventDefault();
    if (!doiQuery.trim()) return;
    
    setIsFetchingDoi(true);
    setDoiStatus(null);

    setTimeout(() => {
      setIsFetchingDoi(false);
      const newRef = {
        id: `doi-${Date.now()}`,
        title: "Attention Mechanisms in Automated Academic Citation Assembly",
        authors: "Chen, M., & Rodriguez, K.",
        year: 2025,
        journal: "IEEE Transactions on Knowledge Engineering",
        doi: doiQuery,
        verified: true
      };
      setBibliography((prev) => [newRef, ...prev]);
      setDoiStatus(`Successfully retrieved metadata for ${doiQuery} via CrossRef API!`);
      setDoiQuery('');
    }, 1200);
  };

  const currentStyleObj = MOCK_CITATION_STYLES.find((s) => s.id === selectedStyle) || MOCK_CITATION_STYLES[0];

  return (
    <div className="space-y-6 animate-fade-in max-w-6xl mx-auto pb-12">
      {/* Title Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-3">
            <span>Citation Style & Bibliography Engine</span>
            <span className="text-xs px-2.5 py-1 rounded-full bg-brand-500/10 border border-brand-500/30 text-brand-400 font-mono">
              citeproc-py + CSL Styles
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Choose your citation formatting standard and manage CrossRef-indexed references.
          </p>
        </div>

        <button
          onClick={onNavigateExport}
          className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-sm shadow-glow-blue transition-all"
        >
          <span>Proceed to Assembly & Export</span>
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>

      {/* CrossRef DOI Lookup Bar */}
      <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-xs font-semibold uppercase text-brand-400 tracking-wider">
            <Globe className="h-4 w-4" />
            <span>CrossRef API Auto-Fill</span>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">Auto-fetches DOI metadata</span>
        </div>

        <form onSubmit={handleFetchDoi} className="flex items-center space-x-3">
          <div className="relative flex-1">
            <Search className="h-4 w-4 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="text"
              placeholder="Enter DOI (e.g., 10.1038/s42256-019-0081-3 or 10.1016/j.jair.2020)..."
              value={doiQuery}
              onChange={(e) => setDoiQuery(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none font-mono"
            />
          </div>

          <button
            type="submit"
            disabled={isFetchingDoi}
            className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-glow-blue transition-all disabled:opacity-50"
          >
            {isFetchingDoi ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                <span>Querying CrossRef...</span>
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                <span>Parse DOI</span>
              </>
            )}
          </button>
        </form>

        {doiStatus && (
          <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-400 flex items-center space-x-2">
            <Check className="h-4 w-4 shrink-0" />
            <span>{doiStatus}</span>
          </div>
        )}
      </div>

      {/* Style Grid Selector */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold uppercase text-slate-400 tracking-wider">
          Available Citation Standards (CSL)
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MOCK_CITATION_STYLES.map((style) => {
            const isSelected = selectedStyle === style.id;
            return (
              <div
                key={style.id}
                onClick={() => setSelectedStyle(style.id)}
                className={`glass-card p-5 rounded-2xl border cursor-pointer transition-all relative ${
                  isSelected
                    ? 'border-brand-500 bg-brand-500/10 shadow-glow-blue'
                    : 'border-slate-800 hover:border-slate-700'
                }`}
              >
                {isSelected && (
                  <div className="absolute top-4 right-4 h-6 w-6 rounded-full bg-brand-500 text-white flex items-center justify-center shadow-glow-blue">
                    <Check className="h-4 w-4" />
                  </div>
                )}

                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                  {style.category}
                </span>

                <h4 className="text-base font-bold text-white mt-2">{style.name}</h4>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">{style.description}</p>

                <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-1 text-[11px]">
                  <span className="text-slate-500 font-mono">In-Text Preview:</span>
                  <p className="text-brand-300 font-mono bg-slate-950/60 p-1.5 rounded border border-slate-800/80">
                    {style.sampleInText}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Active References & Formatting Preview */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <BookOpen className="h-5 w-5 text-brand-400" />
            <h3 className="text-base font-bold text-white">
              Formatted Bibliography Preview ({currentStyleObj.name})
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-mono">{bibliography.length} references</span>
        </div>

        <div className="space-y-3">
          {bibliography.map((ref, idx) => (
            <div key={ref.id} className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-1 text-xs">
              <div className="flex items-center justify-between text-slate-400 font-mono text-[11px]">
                <span>[{idx + 1}] ID: {ref.id}</span>
                <span className="text-emerald-400">Verified DOI</span>
              </div>
              <p className="text-slate-200 font-serif leading-relaxed">
                {ref.authors} ({ref.year}). <span className="italic">{ref.title}</span>. <em>{ref.journal}</em>. https://doi.org/{ref.doi}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
