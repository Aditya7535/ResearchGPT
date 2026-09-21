import React, { useState } from 'react';
import { 
  LayoutDashboard, 
  Search, 
  Filter, 
  FileText, 
  Quote, 
  Sparkles, 
  ChevronRight, 
  Layers,
  Info,
  ExternalLink,
  BookOpen
} from 'lucide-react';

export default function DashboardPage({ chunks, documents, onNavigateOutline }) {
  const [selectedSection, setSelectedSection] = useState('All');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeChunkModal, setActiveChunkModal] = useState(null);

  const sections = ['All', 'Introduction', 'Literature Review', 'Methods', 'Results', 'Discussion', 'Conclusion'];

  const filteredChunks = chunks.filter((chunk) => {
    const matchesSection = selectedSection === 'All' || chunk.section === selectedSection;
    const matchesSearch = 
      chunk.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
      chunk.filename.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSection && matchesSearch;
  });

  const sectionCounts = sections.reduce((acc, sec) => {
    if (sec === 'All') acc[sec] = chunks.length;
    else acc[sec] = chunks.filter((c) => c.section === sec).length;
    return acc;
  }, {});

  return (
    <div className="space-y-6 animate-fade-in max-w-6xl mx-auto pb-12">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-3">
            <span>Ingested Content Dashboard</span>
            <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono">
              Vector Index Active
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Browse extracted thesis content organized by academic section headers.
          </p>
        </div>

        <button
          onClick={onNavigateOutline}
          className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-sm shadow-glow-blue transition-all"
        >
          <span>Propose Thesis Outline</span>
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4">
        {/* Section Pills */}
        <div className="flex flex-wrap items-center gap-1.5 w-full md:w-auto">
          {sections.map((sec) => (
            <button
              key={sec}
              onClick={() => setSelectedSection(sec)}
              className={`px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
                selectedSection === sec
                  ? 'bg-brand-600 text-white shadow-glow-blue'
                  : 'bg-dark-900 border border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700'
              }`}
            >
              {sec}
              <span className="ml-1.5 opacity-60 font-mono">({sectionCounts[sec] || 0})</span>
            </button>
          ))}
        </div>

        {/* Search input */}
        <div className="relative w-full md:w-72">
          <Search className="h-4 w-4 text-slate-400 absolute left-3.5 top-3" />
          <input
            type="text"
            placeholder="Search chunks or filenames..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-dark-900 border border-slate-800 rounded-xl pl-10 pr-3 py-2 text-xs text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
          />
        </div>
      </div>

      {/* Chunks Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredChunks.map((chunk) => (
          <div
            key={chunk.id}
            onClick={() => setActiveChunkModal(chunk)}
            className="glass-card rounded-2xl p-5 space-y-3 cursor-pointer transition-all hover:border-brand-500/40 relative group"
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <span className="px-2.5 py-1 rounded-lg bg-brand-500/10 border border-brand-500/30 text-brand-400 text-xs font-semibold font-mono">
                {chunk.section}
              </span>

              <div className="flex items-center space-x-2 text-xs font-mono text-slate-400">
                <span>Score:</span>
                <span className="text-emerald-400 font-bold">{(chunk.similarity * 100).toFixed(1)}%</span>
              </div>
            </div>

            {/* Snippet Content */}
            <p className="text-xs text-slate-300 leading-relaxed line-clamp-3 font-sans">
              "{chunk.content}"
            </p>

            {/* Metadata Footer */}
            <div className="flex items-center justify-between pt-3 border-t border-slate-800/80 text-[11px] text-slate-400">
              <div className="flex items-center space-x-1.5 truncate max-w-[200px]">
                <FileText className="h-3.5 w-3.5 text-slate-500 shrink-0" />
                <span className="truncate">{chunk.filename}</span>
              </div>

              <div className="flex items-center space-x-3">
                <span className="font-mono text-slate-500">{chunk.wordCount} words</span>
                {chunk.citations?.length > 0 && (
                  <span className="flex items-center space-x-1 text-brand-400 font-mono font-medium">
                    <Quote className="h-3 w-3" />
                    <span>{chunk.citations.length} ref</span>
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {filteredChunks.length === 0 && (
        <div className="p-12 text-center border border-dashed border-slate-800 rounded-2xl bg-dark-900/40">
          <BookOpen className="h-10 w-10 text-slate-600 mx-auto mb-3" />
          <h3 className="text-slate-300 font-semibold">No section chunks match your filter</h3>
          <p className="text-xs text-slate-500 mt-1">Try selecting a different section or clear your search query.</p>
        </div>
      )}

      {/* Chunk Detail Modal */}
      {activeChunkModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="w-full max-w-xl bg-dark-900 border border-slate-700 rounded-2xl p-6 space-y-4 shadow-glow-blue-lg">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <span className="px-2.5 py-1 rounded bg-brand-500/10 border border-brand-500/30 text-brand-400 text-xs font-mono font-bold">
                  {activeChunkModal.section}
                </span>
                <span className="text-xs text-slate-400 font-mono">ID: {activeChunkModal.id}</span>
              </div>

              <button
                onClick={() => setActiveChunkModal(null)}
                className="text-slate-400 hover:text-white px-2 py-1 rounded-lg hover:bg-slate-800 text-xs font-mono"
              >
                Close [ESC]
              </button>
            </div>

            <div className="space-y-2">
              <h4 className="text-xs font-semibold uppercase text-slate-400 tracking-wider">Full Extracted Content</h4>
              <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 text-xs text-slate-200 leading-relaxed font-sans">
                {activeChunkModal.content}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800">
                <span className="text-slate-400">Source Document:</span>
                <p className="text-white font-medium truncate mt-0.5">{activeChunkModal.filename}</p>
              </div>

              <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800">
                <span className="text-slate-400">ChromaDB Cosine Score:</span>
                <p className="text-emerald-400 font-mono font-bold mt-0.5">
                  {(activeChunkModal.similarity * 100).toFixed(1)}% Match
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
