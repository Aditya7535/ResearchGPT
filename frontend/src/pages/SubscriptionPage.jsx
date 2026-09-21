import React, { useState } from 'react';
import { 
  CreditCard, 
  Check, 
  Sparkles, 
  ShieldCheck, 
  Zap, 
  Lock, 
  HelpCircle,
  Building2,
  UserCheck
} from 'lucide-react';
import { SUBSCRIPTION_PLANS } from '../mockData';

export default function SubscriptionPage({ activeSubscription, onSelectPlan }) {
  const [billingInterval, setBillingInterval] = useState('month');

  return (
    <div className="space-y-8 animate-fade-in max-w-6xl mx-auto pb-12">
      {/* Title Header */}
      <div className="text-center max-w-2xl mx-auto space-y-3">
        <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-brand-500/10 border border-brand-500/30 text-brand-400 text-xs font-mono font-semibold">
          <Sparkles className="h-3.5 w-3.5" />
          <span>Stripe Billing & Subscription Engine</span>
        </div>

        <h1 className="text-3xl font-extrabold text-white tracking-tight">
          Flexible Pricing for Researchers & Universities
        </h1>
        
        <p className="text-sm text-slate-400">
          Unlock high-resolution PDF rendering, external Copyleaks plagiarism scanning, and unlimited document ingestion.
        </p>

        {/* Monthly vs Annual Toggle */}
        <div className="pt-2 flex items-center justify-center space-x-3">
          <span className={`text-xs ${billingInterval === 'month' ? 'text-white font-semibold' : 'text-slate-400'}`}>
            Monthly Billing
          </span>

          <button
            onClick={() => setBillingInterval(billingInterval === 'month' ? 'year' : 'month')}
            className="relative inline-flex h-6 w-11 items-center rounded-full bg-slate-800 transition-colors focus:outline-none"
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-brand-500 transition-transform ${
                billingInterval === 'year' ? 'translate-x-6' : 'translate-x-1'
              }`}
            />
          </button>

          <span className={`text-xs ${billingInterval === 'year' ? 'text-white font-semibold' : 'text-slate-400'}`}>
            Annual Billing <span className="text-emerald-400 font-mono text-[10px] font-bold">(Save 20%)</span>
          </span>
        </div>
      </div>

      {/* Pricing Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {SUBSCRIPTION_PLANS.map((plan) => {
          const isCurrent = activeSubscription === plan.id;
          const displayPrice = billingInterval === 'year' && plan.price > 0 
            ? Math.round(plan.price * 0.8) 
            : plan.price;

          return (
            <div
              key={plan.id}
              className={`glass-card rounded-2xl p-6 flex flex-col justify-between border relative transition-all duration-300 ${
                plan.popular
                  ? 'border-brand-500 bg-brand-600/10 shadow-glow-blue-lg scale-105 z-10'
                  : 'border-slate-800 hover:border-slate-700'
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full bg-brand-500 text-white font-mono text-[10px] font-bold tracking-wider uppercase shadow-glow-blue">
                  {plan.badge}
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-bold text-white">{plan.name}</h3>
                  <p className="text-xs text-slate-400 mt-1 min-h-[32px]">{plan.description}</p>
                </div>

                <div className="flex items-baseline space-x-1">
                  <span className="text-3xl font-extrabold text-white">${displayPrice}</span>
                  <span className="text-xs text-slate-400">/ {plan.interval}</span>
                </div>

                <div className="pt-4 border-t border-slate-800 space-y-2.5">
                  {plan.features.map((feature, idx) => (
                    <div key={idx} className="flex items-start space-x-2.5 text-xs text-slate-300">
                      <Check className="h-4 w-4 text-brand-400 shrink-0 mt-0.5" />
                      <span>{feature}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-6">
                <button
                  onClick={() => onSelectPlan(plan)}
                  disabled={isCurrent}
                  className={`w-full py-3 rounded-xl font-semibold text-xs transition-all shadow-glow-blue ${
                    isCurrent
                      ? 'bg-slate-800 text-slate-400 cursor-default border border-slate-700'
                      : plan.popular
                      ? 'bg-brand-600 hover:bg-brand-500 text-white'
                      : 'bg-slate-800 hover:bg-slate-700 text-white border border-slate-700'
                  }`}
                >
                  {isCurrent ? 'Current Plan' : `Upgrade to ${plan.name}`}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Feature Comparison Matrix */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-4">
        <h3 className="text-base font-bold text-white flex items-center space-x-2">
          <ShieldCheck className="h-5 w-5 text-brand-400" />
          <span>Detailed Feature Matrix</span>
        </h3>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-mono">
                <th className="py-3 px-4">Feature Capability</th>
                <th className="py-3 px-4 text-center">Free</th>
                <th className="py-3 px-4 text-center text-brand-400">Pro Academic</th>
                <th className="py-3 px-4 text-center">Enterprise</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              <tr>
                <td className="py-3 px-4 font-medium">ChromaDB Local Vector Corpus</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ 5 Docs</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Unlimited</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Dedicated DB</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-medium">WeasyPrint PDF High-Res Renderer</td>
                <td className="py-3 px-4 text-center text-slate-500">—</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Enabled</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Enabled</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-medium">Copyleaks External Similarity API</td>
                <td className="py-3 px-4 text-center text-slate-500">—</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Included</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Full API Access</td>
              </tr>
              <tr>
                <td className="py-3 px-4 font-medium">CrossRef DOI Automatic Metadata Parsing</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Basic</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Unlimited</td>
                <td className="py-3 px-4 text-center text-emerald-400 font-bold">✓ Batch DOI API</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
