import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Folder, FileCode, FileText, Database, Shield, Brain, Activity, Terminal, LayoutDashboard, ChevronRight, ChevronDown, Copy, Check } from 'lucide-react';

// --- MOCK FILE CONTENT FOR VIEWING PURPOSES ---
const FILES = {
  "README.md": `# 🤖 AI-Quantamental Trading Bot (Zenith Architecture)

## Philosophy
"Logic protects Capital. AI provides Opportunity. Code provides Speed."

## Architecture
1. **The Head Hunter (Screener):** Fundamental Analysis (ROE, PEG).
2. **The Radar (Scout):** Crypto Volatility Scanner.
3. **The Spy (Data):** Technicals & News.
4. **The Strategist (AI):** Gemini Reasoning Engine.
5. **The Judge (Risk):** Logic-based Guardrail.
6. **The Sniper (Execution):** Order Management.

## Setup
1. Fill in \`.env\`
2. Run \`setup_database.py\` in Supabase SQL Editor.
3. \`docker-compose up\``,

  "requirements.txt": `python-dotenv>=1.0.0
pandas>=2.0.0
numpy>=1.24.0
pydantic>=2.0.0
tenacity>=8.2.0
supabase>=2.0.0
ccxt>=4.0.0
yfinance>=0.2.0
pandas_ta>=0.3.14
google-generativeai>=0.3.0
beautifulsoup4>=4.12.0
feedparser>=6.0.10
aiohttp>=3.8.0
apscheduler>=3.10.0
streamlit>=1.28.0
plotly>=5.18.0`,

  ".env.example": `SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_KEY="your-service-role-key"
GEMINI_API_KEY="your-gemini-key"
BINANCE_API_KEY="your-binance-key"
BINANCE_SECRET="your-binance-secret"
ENV="development"`,

  "setup_database.py": `"""
[ZENITH ARCHITECT]
Run this SQL script in Supabase SQL Editor to initialize the schema.
"""

SQL_SCHEMA = """
-- Enable UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Assets
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL UNIQUE,
    market_type TEXT CHECK (market_type IN ('spot', 'futures')),
    status TEXT DEFAULT 'active',
    fundamentals JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Market Snapshots
CREATE TABLE IF NOT EXISTS market_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID REFERENCES assets(id),
    timeframe TEXT DEFAULT '1h',
    close_price NUMERIC,
    rsi NUMERIC,
    macd NUMERIC,
    atr NUMERIC,
    extra_indicators JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. AI Analysis
CREATE TABLE IF NOT EXISTS ai_analysis (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    snapshot_id UUID REFERENCES market_snapshots(id),
    sentiment_score NUMERIC,
    ai_confidence NUMERIC,
    reasoning TEXT,
    model_version TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Trade Signals
CREATE TABLE IF NOT EXISTS trade_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID REFERENCES assets(id),
    signal_type TEXT,
    entry_target NUMERIC,
    stop_loss NUMERIC,
    take_profit NUMERIC,
    status TEXT DEFAULT 'pending',
    judge_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Positions
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id UUID REFERENCES assets(id),
    side TEXT,
    entry_avg NUMERIC,
    quantity NUMERIC,
    unrealized_pnl NUMERIC,
    is_open BOOLEAN DEFAULT TRUE
);

-- 6. Bot Config
CREATE TABLE IF NOT EXISTS bot_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT
);
"""

print(SQL_SCHEMA)`,

  "src/database.py": `import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            if not url or not key:
                raise ValueError("Missing Supabase Credentials")
            cls._instance = create_client(url, key)
        return cls._instance

def get_db() -> Client:
    return Database()`,

  "src/roles/job_ai_analyst.py": `import google.generativeai as genai
import os
import json
from tenacity import retry, stop_after_attempt, wait_fixed
from src.database import get_db

class Strategist:
    """
    The Strategist (AI Analyst)
    Role: Analyze technical data and news to provide a sentiment score and reasoning.
    """
    def __init__(self):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.db = get_db()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def analyze_market(self, snapshot_id, asset_symbol, tech_data):
        prompt = f"""
        Role: Senior Crypto Trader (Zenith Persona).
        Task: Analyze {asset_symbol}.
        Data: {json.dumps(tech_data)}
        
        Output JSON only:
        {{
            "sentiment_score": (float -1.0 to 1.0),
            "confidence": (int 0-100),
            "reasoning": "Concise logic.",
            "recommendation": "BUY/SELL/WAIT"
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            text = response.text.replace('\\\`\\\`\\\`json', '').replace('\\\`\\\`\\\`', '')
            analysis = json.loads(text)
            return analysis
        except Exception as e:
            print(f"Strategist Error: {e}")
            return None`,

  "src/roles/job_judge.py": `from pydantic import BaseModel, Field
from src.database import get_db

class TradeDecision(BaseModel):
    decision: str = Field(pattern="^(APPROVED|REJECTED)$")
    size: float
    reason: str

class Judge:
    """
    The Judge (Risk Manager)
    Role: The Guardrail. Final authority on all trades.
    """
    def __init__(self):
        self.db = get_db()
        self.config = self._load_config()

    def _load_config(self):
        data = self.db.table("bot_config").select("*").execute().data
        return {item['key']: item['value'] for item in data}

    def evaluate(self, ai_data, tech_data, portfolio_balance):
        rsi = tech_data.get('rsi')
        ai_conf = ai_data.get('confidence')
        ai_rec = ai_data.get('recommendation')

        # Rule 1: Guardrails
        rsi_limit = float(self.config.get('RSI_OVERBOUGHT', 70))
        if rsi > rsi_limit and ai_rec == 'BUY':
            return TradeDecision(decision="REJECTED", size=0, reason=f"RSI {rsi} > {rsi_limit}")

        # Rule 2: AI Confidence
        min_conf = float(self.config.get('AI_MIN_CONFIDENCE', 75))
        if ai_conf < min_conf:
            return TradeDecision(decision="REJECTED", size=0, reason=f"Confidence {ai_conf}% < {min_conf}%")

        # Rule 3: Position Sizing (Spot)
        # Allocate 5% of portfolio per trade
        size = portfolio_balance * 0.05 
        
        return TradeDecision(
            decision="APPROVED",
            size=size,
            reason=f"Clean Signal. AI Conf: {ai_conf}%"
        )`,

  "dashboard/app.py": `import streamlit as st
import pandas as pd
from src.database import get_db

st.set_page_config(page_title="Zenith AI Bot", layout="wide", page_icon="🤖")
db = get_db()

st.title("🤖 Zenith AI-Quantamental Dashboard")

# --- SIDEBAR ---
st.sidebar.header("Control Center")
if st.sidebar.button("🚨 EMERGENCY STOP"):
    db.table("bot_config").upsert({"key": "BOT_STATUS", "value": "STOPPED"}).execute()
    st.sidebar.error("BOT STOPPED!")

# --- COCKPIT ---
st.subheader("📊 Portfolio Overview")
col1, col2, col3 = st.columns(3)
col1.metric("Total Equity", "$12,450", "+2.4%")
col2.metric("Active Positions", "3")
col3.metric("Win Rate (24h)", "65%")

# --- POSITIONS ---
st.subheader("⚡ Active Positions")
positions = db.table("positions").select("*, assets(symbol)").eq("is_open", True).execute()
if positions.data:
    df = pd.DataFrame(positions.data)
    df['symbol'] = df['assets'].apply(lambda x: x['symbol'])
    st.dataframe(df[['symbol', 'side', 'entry_avg', 'unrealized_pnl', 'quantity']])
else:
    st.info("No active positions. The Sniper is waiting.")

# --- AUDIT LOGS ---
st.subheader("🕵️ Reasoning Audit")
logs = db.table("trade_signals").select("*, assets(symbol), ai_analysis(reasoning, ai_confidence)").order("created_at", desc=True).limit(5).execute()

for trade in logs.data or []:
    with st.expander(f"{trade['signal_type']} {trade['assets']['symbol']} | Judge: {trade['status']}"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**The Judge:**")
            st.warning(trade['judge_reason'])
        with c2:
            st.markdown(f"**The Strategist ({trade['ai_analysis']['ai_confidence']}%)**")
            st.info(trade['ai_analysis']['reasoning'])
`
};

// --- UI COMPONENTS ---

interface FileTreeItemProps {
  name: string;
  type: string;
  depth?: number;
  isOpen?: boolean;
  onToggle?: () => void;
  isSelected?: boolean;
  onSelect?: () => void;
}

const FileTreeItem = ({ 
  name, 
  type, 
  depth = 0, 
  isOpen = false, 
  onToggle = () => {}, 
  isSelected = false, 
  onSelect = () => {} 
}: FileTreeItemProps) => {
  const Icon = type === 'folder' ? Folder : (name.endsWith('.py') ? FileCode : FileText);
  
  return (
    <div 
      className={`flex items-center py-1 px-2 cursor-pointer hover:bg-gray-800 transition-colors ${isSelected ? 'bg-gray-800 text-blue-400' : 'text-gray-300'}`}
      style={{ paddingLeft: `${depth * 1.25 + 0.5}rem` }}
      onClick={() => type === 'folder' ? onToggle() : onSelect()}
    >
      {type === 'folder' && (
        <span className="mr-1">
          {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      )}
      <Icon size={16} className={`mr-2 ${type === 'folder' ? 'text-yellow-500' : 'text-blue-400'}`} />
      <span className="text-sm font-medium">{name}</span>
    </div>
  );
};

const FileViewer = ({ filename, content }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col h-full bg-gray-900 text-gray-200">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center space-x-2">
          <FileCode size={18} className="text-blue-400" />
          <span className="font-mono text-sm font-bold text-gray-100">{filename}</span>
        </div>
        <button 
          onClick={handleCopy}
          className="flex items-center space-x-2 px-3 py-1.5 rounded-md bg-gray-800 hover:bg-gray-700 text-xs transition-colors border border-gray-700"
        >
          {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
          <span>{copied ? "Copied" : "Copy Code"}</span>
        </button>
      </div>
      <div className="flex-1 overflow-auto p-4 font-mono text-sm leading-relaxed custom-scrollbar">
        <pre className="text-gray-300">
          <code>{content}</code>
        </pre>
      </div>
    </div>
  );
};

const App = () => {
  const [selectedFile, setSelectedFile] = useState("README.md");
  const [foldersOpen, setFoldersOpen] = useState({ "src": true, "src/roles": true, "dashboard": true });

  const toggleFolder = (folder) => {
    setFoldersOpen(prev => ({ ...prev, [folder]: !prev[folder] }));
  };

  const fileStructure = [
    { name: ".env.example", type: "file" },
    { name: "requirements.txt", type: "file" },
    { name: "README.md", type: "file" },
    { name: "setup_database.py", type: "file" },
    { name: "dashboard", type: "folder", children: [
        { name: "app.py", type: "file" }
      ] 
    },
    { name: "src", type: "folder", children: [
        { name: "database.py", type: "file" },
        { name: "roles", type: "folder", children: [
            { name: "job_ai_analyst.py", type: "file" },
            { name: "job_judge.py", type: "file" },
          ]
        }
      ]
    }
  ];

  const getFileContent = (path) => {
    // Helper to map UI path to FILES object keys
    if (FILES[path]) return FILES[path];
    
    // Check nested paths
    const parts = path.split('/');
    const filename = parts[parts.length - 1];
    if (FILES[filename]) return FILES[filename]; // Fallback for simple demo
    
    // Explicit mapping for nested in demo
    if (path === "dashboard/app.py") return FILES["dashboard/app.py"];
    if (path === "src/database.py") return FILES["src/database.py"];
    if (path === "src/roles/job_ai_analyst.py") return FILES["src/roles/job_ai_analyst.py"];
    if (path === "src/roles/job_judge.py") return FILES["src/roles/job_judge.py"];

    return "# Content not loaded in this preview.";
  };

  const renderTree = (items, basePath = "") => {
    return items.map((item) => {
      const fullPath = basePath ? `${basePath}/${item.name}` : item.name;
      if (item.type === 'folder') {
        return (
          <div key={fullPath}>
            <FileTreeItem 
              name={item.name} 
              type="folder" 
              depth={basePath.split('/').filter(Boolean).length}
              isOpen={foldersOpen[fullPath]} 
              onToggle={() => toggleFolder(fullPath)} 
            />
            {foldersOpen[fullPath] && renderTree(item.children, fullPath)}
          </div>
        );
      }
      return (
        <FileTreeItem 
          key={fullPath}
          name={item.name} 
          type="file" 
          depth={basePath.split('/').filter(Boolean).length}
          isSelected={selectedFile === fullPath}
          onSelect={() => setSelectedFile(fullPath)}
        />
      );
    });
  };

  return (
    <div className="flex h-screen bg-gray-950 text-gray-200 overflow-hidden font-sans selection:bg-blue-500/30">
      {/* Sidebar / Explorer */}
      <div className="w-72 border-r border-gray-800 flex flex-col bg-gray-950">
        <div className="p-4 border-b border-gray-800 flex items-center space-x-2 bg-gray-900/50">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
            <Shield size={18} className="text-white" />
          </div>
          <div>
            <h2 className="font-bold text-gray-100 tracking-tight">ZENITH BOT</h2>
            <p className="text-xs text-blue-400 font-medium">Architecture Blueprint</p>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
          <div className="px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">Project Files</div>
          {renderTree(fileStructure)}
        </div>
        <div className="p-4 border-t border-gray-800 bg-gray-900/30">
           <div className="flex items-center space-x-2 text-xs text-gray-500">
             <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
             <span>System Status: Online</span>
           </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full overflow-hidden relative">
        <FileViewer 
          filename={selectedFile} 
          content={getFileContent(selectedFile)} 
        />
      </div>
    </div>
  );
};

export default App;