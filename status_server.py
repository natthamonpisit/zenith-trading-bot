"""
Simple HTTP Status Server for Railway
Shows bot health and API connection status
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time
from datetime import datetime
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database import get_db

class StatusHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for bot status"""
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            # Get bot status from database
            db = get_db()
            
            # Fetch key metrics
            bot_status = self._get_bot_status(db)
            heartbeat = self._get_heartbeat(db)
            api_status = self._check_api_connections(db)
            recent_activity = self._get_recent_activity(db)
            
            # Generate HTML
            html = self._generate_html(bot_status, heartbeat, api_status, recent_activity)
            
            # Send response
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
            
        except Exception as e:
            # Error response
            self.send_response(500)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            error_html = f"""
            <html>
            <head><title>Bot Status - Error</title></head>
            <body style="font-family: monospace; padding: 20px; background: #1a1a1a; color: #fff;">
                <h1>❌ Error</h1>
                <pre>{str(e)}</pre>
            </body>
            </html>
            """
            self.wfile.write(error_html.encode())
    
    def _get_bot_status(self, db):
        """Get bot status from config"""
        try:
            result = db.table("bot_config").select("key, value").execute()
            config = {item['key']: item['value'] for item in result.data}
            
            status = config.get('BOT_STATUS', 'UNKNOWN')
            mode = config.get('MODE', 'UNKNOWN')
            
            return {
                'status': status,
                'mode': mode,
                'running': status != 'STOPPED'
            }
        except:
            return {'status': 'ERROR', 'mode': 'UNKNOWN', 'running': False}
    
    def _get_heartbeat(self, db):
        """Get last heartbeat"""
        try:
            result = db.table("bot_config").select("value").eq("key", "LAST_HEARTBEAT").execute()
            if result.data:
                last_hb = float(result.data[0]['value'])
                diff = time.time() - last_hb
                
                return {
                    'timestamp': datetime.fromtimestamp(last_hb).strftime('%Y-%m-%d %H:%M:%S'),
                    'ago_seconds': int(diff),
                    'healthy': diff < 120
                }
        except:
            pass
        
        return {'timestamp': 'N/A', 'ago_seconds': 9999, 'healthy': False}
    
    def _check_api_connections(self, db):
        """Check API connection status"""
        apis = {}
        
        # Supabase (already connected if we got here)
        apis['Supabase'] = {'status': '✅ Connected', 'healthy': True}
        
        # Binance
        try:
            import ccxt
            api_key = os.environ.get("BINANCE_API_KEY")
            api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
            
            if api_key:
                apis['Binance'] = {'status': f'✅ Configured ({api_url})', 'healthy': True}
            else:
                apis['Binance'] = {'status': '⚠️ Not Configured', 'healthy': False}
        except:
            apis['Binance'] = {'status': '❌ Error', 'healthy': False}
        
        # Gemini AI
        try:
            gemini_key = os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                apis['Gemini AI'] = {'status': '✅ Configured', 'healthy': True}
            else:
                apis['Gemini AI'] = {'status': '⚠️ Not Configured', 'healthy': False}
        except:
            apis['Gemini AI'] = {'status': '❌ Error', 'healthy': False}
        
        return apis
    
    def _get_recent_activity(self, db):
        """Get recent bot activity"""
        try:
            # Get recent logs
            logs = db.table("system_logs")\
                .select("role, message, level, created_at")\
                .order("created_at", desc=True)\
                .limit(5)\
                .execute()
            
            return logs.data if logs.data else []
        except:
            return []
    
    def _generate_html(self, bot_status, heartbeat, api_status, recent_activity):
        """Generate status HTML"""
        
        # Status color
        status_color = '#00ff00' if bot_status['running'] else '#ff0000'
        hb_color = '#00ff00' if heartbeat['healthy'] else '#ff0000'
        
        # Recent activity HTML
        activity_html = ""
        for log in recent_activity:
            level_color = {
                'SUCCESS': '#00ff00',
                'ERROR': '#ff0000',
                'WARNING': '#ffaa00',
                'INFO': '#00aaff'
            }.get(log.get('level', 'INFO'), '#ffffff')
            
            activity_html += f"""
            <tr>
                <td style="color: #888;">{log.get('created_at', 'N/A')[:19]}</td>
                <td style="color: #00aaff;">{log.get('role', 'N/A')}</td>
                <td style="color: {level_color};">{log.get('message', 'N/A')[:100]}</td>
            </tr>
            """
        
        # API status HTML
        api_html = ""
        for name, info in api_status.items():
            api_html += f"""
            <tr>
                <td style="color: #00aaff;">{name}</td>
                <td>{info['status']}</td>
            </tr>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Zenith Bot Status</title>
            <meta charset="UTF-8">
            <meta http-equiv="refresh" content="10">
            <style>
                body {{
                    font-family: 'Courier New', monospace;
                    background: #0a0a0a;
                    color: #00ff00;
                    padding: 20px;
                    margin: 0;
                }}
                .container {{
                    max-width: 1000px;
                    margin: 0 auto;
                }}
                h1 {{
                    color: #00ff00;
                    border-bottom: 2px solid #00ff00;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #00aaff;
                    margin-top: 30px;
                    border-bottom: 1px solid #00aaff;
                    padding-bottom: 5px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                }}
                td {{
                    padding: 8px;
                    border-bottom: 1px solid #333;
                }}
                .metric {{
                    display: inline-block;
                    margin: 10px 20px 10px 0;
                }}
                .label {{
                    color: #888;
                    font-size: 0.9em;
                }}
                .value {{
                    font-size: 1.2em;
                    font-weight: bold;
                }}
                .footer {{
                    margin-top: 40px;
                    text-align: center;
                    color: #666;
                    font-size: 0.8em;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Zenith Trading Bot - Status Monitor</h1>
                
                <div class="metric">
                    <div class="label">Bot Status</div>
                    <div class="value" style="color: {status_color};">{bot_status['status']}</div>
                </div>
                
                <div class="metric">
                    <div class="label">Mode</div>
                    <div class="value">{bot_status['mode']}</div>
                </div>
                
                <div class="metric">
                    <div class="label">Last Heartbeat</div>
                    <div class="value" style="color: {hb_color};">{heartbeat['ago_seconds']}s ago</div>
                </div>
                
                <h2>📡 API Connections</h2>
                <table>
                    {api_html}
                </table>
                
                <h2>📋 Recent Activity (Last 5)</h2>
                <table>
                    <thead>
                        <tr style="color: #888;">
                            <td>Time</td>
                            <td>Role</td>
                            <td>Message</td>
                        </tr>
                    </thead>
                    <tbody>
                        {activity_html}
                    </tbody>
                </table>
                
                <div class="footer">
                    Auto-refresh every 10 seconds | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def start_server(port=8080):
    """Start HTTP status server"""
    server = HTTPServer(('0.0.0.0', port), StatusHandler)
    print(f"🚀 Status server running on port {port}")
    print(f"📊 Visit http://localhost:{port}")
    server.serve_forever()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    start_server(port)
