import React, { useState } from 'react';
import { X, CreditCard, Lock, CheckCircle2, ShieldCheck, Sparkles, Loader2 } from 'lucide-react';

export default function StripeModal({ plan, onClose, onSuccess }) {
  const [processing, setProcessing] = useState(false);
  const [cardNumber, setCardNumber] = useState('4242 •••• •••• 4242');
  const [expiry, setExpiry] = useState('12/28');
  const [cvc, setCvc] = useState('888');
  const [name, setName] = useState('Jane Smith');

  const handlePay = (e) => {
    e.preventDefault();
    setProcessing(true);
    setTimeout(() => {
      setProcessing(false);
      onSuccess(plan.id);
    }, 1800);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-lg bg-dark-900 border border-slate-700/80 rounded-2xl shadow-glow-blue-lg overflow-hidden">
        {/* Header banner */}
        <div className="bg-gradient-to-r from-brand-900 via-brand-700 to-brand-600 p-6 text-white relative">
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-white/70 hover:text-white p-1 rounded-full hover:bg-white/10 transition-all"
          >
            <X className="h-5 w-5" />
          </button>
          
          <div className="flex items-center space-x-2 text-brand-200 text-xs font-semibold uppercase tracking-wider mb-1">
            <Sparkles className="h-4 w-4" />
            <span>Powered by Stripe Checkout</span>
          </div>

          <h3 className="text-2xl font-bold">{plan.name} Upgrade</h3>
          <p className="text-sm text-brand-100/90 mt-1">
            ${plan.price} / {plan.interval} — Cancel anytime in settings
          </p>
        </div>

        {/* Form Body */}
        <form onSubmit={handlePay} className="p-6 space-y-4">
          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Cardholder Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-white focus:border-brand-500 focus:outline-none"
              required
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-slate-300">Card Number</label>
            <div className="relative">
              <input
                type="text"
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 text-sm text-white font-mono focus:border-brand-500 focus:outline-none"
                required
              />
              <CreditCard className="h-4 w-4 text-slate-400 absolute left-3.5 top-3" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">Expires</label>
              <input
                type="text"
                value={expiry}
                onChange={(e) => setExpiry(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-white font-mono focus:border-brand-500 focus:outline-none"
                required
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">CVC / CWW</label>
              <input
                type="text"
                value={cvc}
                onChange={(e) => setCvc(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-xl px-3.5 py-2.5 text-sm text-white font-mono focus:border-brand-500 focus:outline-none"
                required
              />
            </div>
          </div>

          <div className="pt-2">
            <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800 flex items-center space-x-3 text-xs text-slate-400">
              <ShieldCheck className="h-5 w-5 text-emerald-400 shrink-0" />
              <span>
                Encrypted 256-bit TLS connection. Stripe handles card security without storing details on our server.
              </span>
            </div>
          </div>

          <div className="pt-2 flex items-center justify-end space-x-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl border border-slate-700 text-slate-300 text-sm font-medium hover:bg-slate-800"
            >
              Cancel
            </button>
            
            <button
              type="submit"
              disabled={processing}
              className="flex items-center space-x-2 px-6 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-sm shadow-glow-blue transition-all disabled:opacity-50"
            >
              {processing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Processing Payment...</span>
                </>
              ) : (
                <>
                  <Lock className="h-4 w-4" />
                  <span>Pay ${plan.price}.00 Now</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
