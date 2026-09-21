export const MOCK_DOCUMENTS = [
  {
    id: "doc-1",
    filename: "Deep_Learning_Survey_2024.pdf",
    size: "4.2 MB",
    uploadedAt: "2026-08-09 14:30",
    sectionsFound: ["Introduction", "Literature Review", "Methods"],
    chunkCount: 24,
    status: "indexed",
    vectors: 24
  },
  {
    id: "doc-2",
    filename: "Transformer_Citation_Analysis.docx",
    size: "1.8 MB",
    uploadedAt: "2026-08-09 16:15",
    sectionsFound: ["Methods", "Results", "Discussion"],
    chunkCount: 18,
    status: "indexed",
    vectors: 18
  },
  {
    id: "doc-3",
    filename: "University_Formatting_Guidelines.txt",
    size: "450 KB",
    uploadedAt: "2026-08-10 09:10",
    sectionsFound: ["Introduction", "Conclusion"],
    chunkCount: 8,
    status: "indexed",
    vectors: 8
  }
];

export const MOCK_CHUNKS = [
  {
    id: "chunk-101",
    documentId: "doc-1",
    filename: "Deep_Learning_Survey_2024.pdf",
    section: "Introduction",
    content: "Citation management is a critical aspect of academic writing. Manual reference tracking is error-prone, leading to incorrect DOIs, missing author names, and inconsistent formatting across publications. Deep neural networks provide a robust semantic retrieval layer for automated citation integrity.",
    wordCount: 42,
    similarity: 0.94,
    citations: ["smith2020"]
  },
  {
    id: "chunk-102",
    documentId: "doc-1",
    filename: "Deep_Learning_Survey_2024.pdf",
    section: "Literature Review",
    content: "Recent studies by Vaswani et al. (2017) and Devlin et al. (2019) demonstrated that attention mechanisms capture long-range contextual dependencies across academic prose. Transformer models applied to PubMed and arXiv corpora outperform traditional TF-IDF vectorizers by 28.4% in semantic retrieval accuracy.",
    wordCount: 46,
    similarity: 0.91,
    citations: ["vaswani2017", "devlin2019"]
  },
  {
    id: "chunk-103",
    documentId: "doc-2",
    filename: "Transformer_Citation_Analysis.docx",
    section: "Methods",
    content: "We collected 500 peer-reviewed papers from PubMed Central and manually annotated 2,500 citation contexts. Texts were parsed into section chunks (Introduction, Methods, Results, Discussion) using PyMuPDF and python-docx, then stored as 1536-dimensional dense embeddings in ChromaDB.",
    wordCount: 41,
    similarity: 0.96,
    citations: ["jones2019"]
  },
  {
    id: "chunk-104",
    documentId: "doc-2",
    filename: "Transformer_Citation_Analysis.docx",
    section: "Results",
    content: "The proposed model achieved 94.2% accuracy on the PubMed test set, 88.7% on arXiv, and 91.3% on IEEE IEEE Xplore. Fine-tuning on CSL citation templates improved bibliography formatting compliance from 71.2% to 99.4%.",
    wordCount: 36,
    similarity: 0.93,
    citations: []
  },
  {
    id: "chunk-105",
    documentId: "doc-2",
    filename: "Transformer_Citation_Analysis.docx",
    section: "Discussion",
    content: "Our experimental results confirm that automated citation alignment reduces manual formatting burden significantly. However, multi-lingual citations and non-standard DOI patterns still require human verification.",
    wordCount: 30,
    similarity: 0.88,
    citations: []
  },
  {
    id: "chunk-106",
    documentId: "doc-3",
    filename: "University_Formatting_Guidelines.txt",
    section: "Conclusion",
    content: "Automating thesis assembly with university-grade typography, dynamic chart embedding, and real-time plagiarism detection delivers print-ready academic dissertations adhering to 1.5-inch margins and double line spacing.",
    wordCount: 30,
    similarity: 0.92,
    citations: []
  }
];

export const MOCK_OUTLINE = [
  {
    id: "sec-1",
    name: "Introduction",
    level: 1,
    prompt: "Synthesize background on neural citation indexing and state the primary research questions.",
    status: "ready",
    citationsCount: 3,
    tablesCount: 0,
    words: 1250,
    subsections: []
  },
  {
    id: "sec-2",
    name: "Literature Review",
    level: 1,
    prompt: "Review transformer architectures applied to NLP citation management and semantic search.",
    status: "ready",
    citationsCount: 8,
    tablesCount: 1,
    words: 2800,
    subsections: [
      {
        id: "sec-2-1",
        name: "Attention Mechanisms in Academic Text",
        level: 2,
        prompt: "Focus on contextual embedding representation for academic citations.",
        status: "ready",
        citationsCount: 4,
        tablesCount: 0,
        words: 1100
      }
    ]
  },
  {
    id: "sec-3",
    name: "Methodology",
    level: 1,
    prompt: "Detail the ChromaDB vector pipeline, python-docx assembly engine, and WeasyPrint PDF renderer.",
    status: "ready",
    citationsCount: 5,
    tablesCount: 1,
    words: 1950,
    subsections: []
  },
  {
    id: "sec-4",
    name: "Results & Evaluation",
    level: 1,
    prompt: "Present accuracy metrics across PubMed, arXiv, and IEEE datasets using matplotlib charts.",
    status: "ready",
    citationsCount: 2,
    tablesCount: 2,
    words: 2100,
    subsections: []
  },
  {
    id: "sec-5",
    name: "Discussion & Future Work",
    level: 1,
    prompt: "Analyze findings, limitations, and future extensions to multi-modal citation reasoning.",
    status: "ready",
    citationsCount: 4,
    tablesCount: 0,
    words: 1400,
    subsections: []
  },
  {
    id: "sec-6",
    name: "Conclusion",
    level: 1,
    prompt: "Summarize major contributions to automated thesis generation.",
    status: "ready",
    citationsCount: 1,
    tablesCount: 0,
    words: 850,
    subsections: []
  }
];

export const MOCK_CITATION_STYLES = [
  {
    id: "apa",
    name: "APA 7th Edition",
    category: "Author-Date",
    description: "American Psychological Association standard for social and computer sciences.",
    sampleInText: "(Smith & Jones, 2024, p. 45)",
    sampleBib: "Smith, J., & Jones, A. (2024). Deep learning for citation management. Journal of Artificial Intelligence Research, 45(2), 112–128."
  },
  {
    id: "vancouver",
    name: "Vancouver / PubMed",
    category: "Numeric",
    description: "International Committee of Medical Journal Editors standard for biomedical sciences.",
    sampleInText: "[1, pp. 45]",
    sampleBib: "1. Smith J, Jones A. Deep learning for citation management. J Artif Intell Res. 2024;45(2):112-128."
  },
  {
    id: "ieee",
    name: "IEEE Standard",
    category: "Numeric Bracket",
    description: "Institute of Electrical and Electronics Engineers standard for engineering and tech.",
    sampleInText: "[1]",
    sampleBib: "J. Smith and A. Jones, \"Deep learning for citation management,\" J. Artif. Intell. Res., vol. 45, no. 2, pp. 112–128, 2024."
  },
  {
    id: "harvard",
    name: "Harvard Reference Style",
    category: "Author-Date",
    description: "Widely adopted across UK and Commonwealth academic institutions.",
    sampleInText: "(Smith and Jones 2024)",
    sampleBib: "Smith, J. and Jones, A. (2024) 'Deep learning for citation management', Journal of Artificial Intelligence Research, 45(2), pp. 112–128."
  },
  {
    id: "chicago",
    name: "Chicago Manual of Style (Notes)",
    category: "Footnote / Endnote",
    description: "Standard for humanities and historical research dissertations.",
    sampleInText: "1. John Smith and Alice Jones, 112.",
    sampleBib: "Smith, John, and Alice Jones. \"Deep Learning for Citation Management.\" Journal of Artificial Intelligence Research 45, no. 2 (2024): 112–28."
  }
];

export const MOCK_BIBLIOGRAPHY = [
  {
    id: "smith2020",
    title: "Deep Learning for NLP and Citation Alignment",
    authors: "Smith, J., & Wang, L.",
    year: 2020,
    journal: "Journal of Artificial Intelligence Research",
    doi: "10.1016/j.jair.2020.04.012",
    verified: true
  },
  {
    id: "jones2019",
    title: "Transformer Survey in Automated Dissertation Systems",
    authors: "Jones, A., Miller, R., & Gupta, P.",
    year: 2019,
    journal: "Nature Machine Intelligence",
    doi: "10.1038/s42256-019-0081-3",
    verified: true
  },
  {
    id: "vaswani2017",
    title: "Attention Is All You Need",
    authors: "Vaswani, A., Shazeer, N., Parmar, N., et al.",
    year: 2017,
    journal: "Advances in Neural Information Processing Systems",
    doi: "10.48550/arXiv.1706.03762",
    verified: true
  }
];

export const SUBSCRIPTION_PLANS = [
  {
    id: "free",
    name: "Free Tier",
    price: 0,
    interval: "forever",
    description: "Essential thesis draft generation & local corpus checking",
    features: [
      "Up to 5 document uploads per project",
      "Standard Word (.docx) export",
      "Internal ChromaDB corpus plagiarism check",
      "APA & Vancouver citation styles",
      "Basic Matplotlib charts (Bar & Line)"
    ],
    cta: "Current Plan",
    popular: false,
    badge: "Free"
  },
  {
    id: "pro",
    name: "Pro Academic",
    price: 29,
    interval: "month",
    description: "Advanced multi-agent thesis assembly with Web similarity & PDF rendering",
    features: [
      "Unlimited research document uploads",
      "High-resolution PDF export via WeasyPrint",
      "External Copyleaks & PlagiarismCheck web similarity",
      "All 5+ citation styles & custom CSL upload",
      "All chart types (Pie, Scatter, Histogram)",
      "University template customization",
      "Priority multi-agent LLM structuring"
    ],
    cta: "Upgrade to Pro",
    popular: true,
    badge: "Most Popular"
  },
  {
    id: "enterprise",
    name: "University Enterprise",
    price: 199,
    interval: "month",
    description: "Department-wide deployment with dedicated vector storage & custom branding",
    features: [
      "Unlimited department seats & collaborative workspaces",
      "Dedicated SQLCipher encrypted storage",
      "Custom university XML/JSON template builder",
      "Deep Copyleaks LMS & turnitin integration",
      "SLA 99.9% uptime & dedicated account manager",
      "Custom CSL & citation metadata auto-fill via CrossRef"
    ],
    cta: "Contact Sales",
    popular: false,
    badge: "Enterprise"
  }
];
