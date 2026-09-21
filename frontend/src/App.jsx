import React, { useState } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import StripeModal from './components/StripeModal';

import UploadPage from './pages/UploadPage';
import DashboardPage from './pages/DashboardPage';
import OutlineEditorPage from './pages/OutlineEditorPage';
import CitationSelectorPage from './pages/CitationSelectorPage';
import ExportPage from './pages/ExportPage';
import SubscriptionPage from './pages/SubscriptionPage';

import { MOCK_DOCUMENTS, MOCK_CHUNKS, MOCK_OUTLINE, MOCK_BIBLIOGRAPHY } from './mockData';

export default function App() {
  const [activeTab, setActiveTab] = useState('upload'); // 'upload', 'dashboard', 'outline', 'citation', 'export', 'subscription'
  const [activeSubscription, setActiveSubscription] = useState('free'); // 'free', 'pro', 'enterprise'
  
  const [documents, setDocuments] = useState(MOCK_DOCUMENTS);
  const [chunks, setChunks] = useState(MOCK_CHUNKS);
  const [outline, setOutline] = useState(MOCK_OUTLINE);
  const [bibliography, setBibliography] = useState(MOCK_BIBLIOGRAPHY);
  const [selectedCitationStyle, setSelectedCitationStyle] = useState('apa');

  const [selectedStripePlan, setSelectedStripePlan] = useState(null);

  const handleStripeSuccess = (planId) => {
    setActiveSubscription(planId);
    setSelectedStripePlan(null);
  };

  return (
    <div className="min-h-screen bg-dark-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header Navbar */}
      <Navbar
        activeSubscription={activeSubscription}
        onOpenStripe={() => setActiveTab('subscription')}
      />

      {/* Main Layout Body */}
      <div className="flex-1 flex">
        {/* Sidebar Navigation */}
        <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          counts={{
            documents: documents.length,
            chunks: chunks.length,
            citations: bibliography.length
          }}
        />

        {/* Content Area */}
        <main className="flex-1 p-6 md:p-8 overflow-y-auto">
          {activeTab === 'upload' && (
            <UploadPage
              documents={documents}
              setDocuments={setDocuments}
              chunks={chunks}
              setChunks={setChunks}
              onContinue={() => setActiveTab('dashboard')}
            />
          )}

          {activeTab === 'dashboard' && (
            <DashboardPage
              chunks={chunks}
              documents={documents}
              onNavigateOutline={() => setActiveTab('outline')}
            />
          )}

          {activeTab === 'outline' && (
            <OutlineEditorPage
              outline={outline}
              setOutline={setOutline}
              onNavigateExport={() => setActiveTab('citation')}
            />
          )}

          {activeTab === 'citation' && (
            <CitationSelectorPage
              selectedStyle={selectedCitationStyle}
              setSelectedStyle={setSelectedCitationStyle}
              bibliography={bibliography}
              setBibliography={setBibliography}
              onNavigateExport={() => setActiveTab('export')}
            />
          )}

          {activeTab === 'export' && (
            <ExportPage
              documents={documents}
              chunks={chunks}
              outline={outline}
              activeSubscription={activeSubscription}
              onOpenStripe={() => setActiveTab('subscription')}
            />
          )}

          {activeTab === 'subscription' && (
            <SubscriptionPage
              activeSubscription={activeSubscription}
              onSelectPlan={(plan) => setSelectedStripePlan(plan)}
            />
          )}
        </main>
      </div>

      {/* Stripe Payment Modal */}
      {selectedStripePlan && (
        <StripeModal
          plan={selectedStripePlan}
          onClose={() => setSelectedStripePlan(null)}
          onSuccess={handleStripeSuccess}
        />
      )}
    </div>
  );
}
