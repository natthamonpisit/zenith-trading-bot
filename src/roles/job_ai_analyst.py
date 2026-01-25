import google.generativeai as genai
import os
import json
from tenacity import retry, stop_after_attempt, wait_fixed
from src.database import get_db

class Strategist:
    """
    THE STRATEGIST (AI Reasoning Engine)
    Uses Google Gemini to analyze technical indicators and news sentiment.
    """
    def __init__(self):
        # Ensure API Key is loaded
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        # Using Gemini 2.0 Flash for speed and reasoning balance
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.db = get_db()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def analyze_market(self, snapshot_id, asset_symbol, tech_data):
        """
        Sends market data to Gemini and expects a strict JSON response.
        """
        
        prompt = f"""
        You are a Senior Crypto Trader & Risk Analyst (The Strategist). 
        Analyze the following asset: {asset_symbol}.
        
        Technical Data:
        Technical Data:
        {json.dumps(tech_data, default=str)}
        
        Task:
        1. Evaluate the trend based on RSI, MACD, and ATR.
        2. Assign a sentiment score (-1.0 to 1.0).
        3. Provide a confidence level (0-100%).
        4. Explain your reasoning concisely.
        
        Output format: VALID JSON ONLY.
        {{
            "sentiment_score": float,
            "confidence": int,
            "reasoning": "string",
            "recommendation": "BUY" | "SELL" | "WAIT"
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            # Cleanup potential markdown formatting
            text = response.text.replace('```json', '').replace('```', '').strip()
            analysis = json.loads(text)
            
            # Save to Database (Mock implementation for Blueprint)
            # self.db.table("ai_analysis").insert({...}).execute()
            
            return analysis
            
        except Exception as e:
            print(f"Stratgeist Error: {e}")
            return None

    def generate_performance_report(self, trade_history, days_range):
        """
        Generates a summary report of trading performance.
        """
        prompt = f"""
        You are a Portfolio Manager writing a performance review.
        Period: Last {days_range} days.
        
        Trade History Data:
        {json.dumps(trade_history, default=str)}
        
        Task:
        1. Summarize the overall trading activity (Total signals, Win Rate if applicable, Strategy behavior).
        2. Identify patterns in the AI's decision making (Why were certain trades rejected?).
        3. Give constructive feedback on the strategy settings.
        4. Use a professional, encouraging tone.
        
        Output: Markdown formatted text.
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Failed to generate report: {e}"
