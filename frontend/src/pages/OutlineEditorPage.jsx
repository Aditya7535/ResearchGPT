import React, { useState } from 'react';
import { 
  ListTree, 
  Plus, 
  Trash2, 
  GripVertical, 
  Sparkles, 
  CheckCircle2, 
  Quote, 
  Table, 
  ArrowRight,
  RefreshCw,
  Edit3,
  Bot
} from 'lucide-react';

export default function OutlineEditorPage({ outline, setOutline, onNavigateExport }) {
  const [editingSectionId, setEditingSectionId] = useState(null);
  const [newSectionName, setNewSectionName] = useState('');
  const [isGeneratingAgent, setIsGeneratingAgent] = useState(false);

  const handlePromptChange = (id, newPrompt) => {
    setOutline((prev) =>
      prev.map((sec) => (sec.id === id ? { ...sec, prompt: newPrompt } : sec))
    );
  };

  const handleNameChange = (id, newName) => {
    setOutline((prev) =>
      prev.map((sec) => (sec.id === id ? { ...sec, name: newName } : sec))
    );
  };

  const handleAddSection = () => {
    if (!newSectionName.trim()) return;
    const newSec = {
      id: `sec-${Date.now()}`,
      name: newSectionName,
      level: 1,
      prompt: `Custom synthesis prompt for ${newSectionName}.`,
      status: 'ready',
      citationsCount: 2,
      tablesCount: 0,
      words: 1000,
      subsections: []
    };
    setOutline((prev) => [...prev, newSec]);
    setNewSectionName('');
  };

  const handleDeleteSection = (id) => {
    setOutline((prev) => prev.filter((sec) => sec.id !== id));
  };

  const handleAgentReGenerate = () => {
    setIsGeneratingAgent(true);
    setTimeout(() => {
      setIsGeneratingAgent(false);
    }, 1500);
  };

  const totalWords = outline.reduce((sum, sec) => sum + sec.words, 0);

  return (
    <div className="space-y-6 animate-fade-in max-w-6xl mx-auto pb-12">
      {/* Title Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center space-x-3">
            <span>Thesis Outline Review & Editor</span>
            <span className="text-xs px-2.5 py-1 rounded-full bg-brand-500/10 border border-brand-500/30 text-brand-400 font-mono">
              Structuring Agent v1.2
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Review and adjust AI-proposed thesis sections. Prompts strictly draw from your uploaded source corpus.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleAgentReGenerate}
            disabled={isGeneratingAgent}
            className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium border border-slate-700 transition-all"
          >
            <RefreshCw className={`h-4 w-4 ${isGeneratingAgent ? 'animate-spin text-brand-400' : ''}`} />
            <span>Re-run Structuring Agent</span>
          </button>

          <button
            onClick={onNavigateExport}
            className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-sm shadow-glow-blue transition-all"
          >
            <span>Proceed to Export</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Metrics Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="glass-card p-4 rounded-2xl border border-slate-800 flex items-center space-x-4">
          <div className="h-10 w-10 rounded-xl bg-brand-500/10 border border-brand-500/30 flex items-center justify-center text-brand-400 font-bold font-mono">
            {outline.length}
          </div>
          <div>
            <p className="text-xs text-slate-400">Total Sections</p>
            <p className="text-sm font-semibold text-white">Full Thesis Structure</p>
          </div>
        </div>

        <div className="glass-card p-4 rounded-2xl border border-slate-800 flex items-center space-x-4">
          <div className="h-10 w-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold font-mono">
            {(totalWords / 1000).toFixed(1)}k
          </div>
          <div>
            <p className="text-xs text-slate-400">Estimated Target Words</p>
            <p className="text-sm font-semibold text-white">Academic Length</p>
          </div>
        </div>

        <div className="glass-card p-4 rounded-2xl border border-slate-800 flex items-center space-x-4">
          <div className="h-10 w-10 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400 font-bold font-mono">
            100%
          </div>
          <div>
            <p className="text-xs text-slate-400">Source Grounding</p>
            <p className="text-sm font-semibold text-white">Zero Invented Claims</p>
          </div>
        </div>
      </div>

      {/* Add New Section Inline Form */}
      <div className="flex items-center space-x-3 p-3 bg-dark-900 border border-slate-800 rounded-2xl">
        <input
          type="text"
          placeholder="Add custom thesis section heading (e.g., Experimental Setup)..."
          value={newSectionName}
          onChange={(e) => setNewSectionName(e.target.value)}
          className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2 text-xs text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none"
        />
        <button
          onClick={handleAddSection}
          className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold shadow-glow-blue"
        >
          <Plus className="h-4 w-4" />
          <span>Add Section</span>
        </button>
      </div>

      {/* Section List */}
      <div className="space-y-4">
        {outline.map((sec, idx) => (
          <div
            key={sec.id}
            className="glass-card rounded-2xl p-5 border border-slate-800 space-y-4 transition-all hover:border-slate-700"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <GripVertical className="h-5 w-5 text-slate-600 cursor-grab" />
                <span className="h-6 w-6 rounded-lg bg-slate-800 text-slate-300 font-mono text-xs font-bold flex items-center justify-center">
                  {idx + 1}
                </span>

                {editingSectionId === sec.id ? (
                  <input
                    type="text"
                    value={sec.name}
                    onChange={(e) => handleNameChange(sec.id, e.target.value)}
                    onBlur={() => setEditingSectionId(null)}
                    autoFocus
                    className="bg-slate-900 border border-brand-500 rounded-lg px-2.5 py-1 text-sm font-semibold text-white focus:outline-none"
                  />
                ) : (
                  <div className="flex items-center space-x-2">
                    <h3 className="text-base font-semibold text-white">{sec.name}</h3>
                    <button
                      onClick={() => setEditingSectionId(sec.id)}
                      className="text-slate-500 hover:text-brand-400 p-1"
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>

              <div className="flex items-center space-x-3 text-xs">
                <span className="flex items-center space-x-1 text-slate-400 font-mono">
                  <Quote className="h-3.5 w-3.5 text-brand-400" />
                  <span>{sec.citationsCount} citations</span>
                </span>

                {sec.tablesCount > 0 && (
                  <span className="flex items-center space-x-1 text-slate-400 font-mono">
                    <Table className="h-3.5 w-3.5 text-purple-400" />
                    <span>{sec.tablesCount} chart/table</span>
                  </span>
                )}

                <span className="px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono font-semibold">
                  ~{sec.words} words
                </span>

                <button
                  onClick={() => handleDeleteSection(sec.id)}
                  className="text-slate-500 hover:text-red-400 p-1 rounded hover:bg-red-500/10"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Prompt text area */}
            <div className="space-y-1.5 pl-9">
              <label className="text-[11px] font-semibold uppercase text-slate-400 tracking-wider flex items-center space-x-1.5">
                <Bot className="h-3.5 w-3.5 text-brand-400" />
                <span>Structuring Agent Synthesis Prompt</span>
              </label>
              <textarea
                value={sec.prompt}
                onChange={(e) => handlePromptChange(sec.id, e.target.value)}
                rows={2}
                className="w-full bg-slate-950/80 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 focus:border-brand-500 focus:outline-none resize-none font-sans leading-relaxed"
              />
            </div>

            {/* Subsections if any */}
            {sec.subsections?.length > 0 && (
              <div className="pl-9 space-y-2 pt-2 border-t border-slate-800/60">
                {sec.subsections.map((sub) => (
                  <div key={sub.id} className="p-3 bg-slate-900/60 rounded-xl border border-slate-800/80 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-300">2.1 {sub.name}</span>
                    <span className="font-mono text-slate-500">{sub.words} words</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
