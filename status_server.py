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
import pytz

# Thailand timezone
THAILAND_TZ = pytz.timezone('Asia/Bangkok')

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
            recent_activity = self._get_recent_activity(db, limit=5)
            live_logs = self._get_recent_activity(db, limit=50)
            pnl_summary = self._get_pnl_summary(db)
            uptime = self._get_uptime(db)

            # Generate HTML
            html = self._generate_html(bot_status, heartbeat, api_status, recent_activity, live_logs, pnl_summary, uptime)
            
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
            
            status = str(config.get('BOT_STATUS', 'UNKNOWN')).replace('"', '').strip()
            mode = str(config.get('MODE', 'UNKNOWN')).replace('"', '').strip()
            
            return {
                'status': status,
                'mode': mode,
                'running': status != 'STOPPED'
            }
        except:
            return {'status': 'ERROR', 'mode': 'UNKNOWN', 'running': False}

    def _get_uptime(self, db):
        """Get bot uptime"""
        try:
            result = db.table("bot_config").select("value").eq("key", "BOT_START_TIME").execute()
            if result.data:
                start_ts = float(result.data[0]['value'])
                
                # Sanity check: If start time is 0 or very old (e.g. > 10 years ago), it's likely a reset placeholder
                if start_ts < 10000 or (time.time() - start_ts) > (3650 * 86400):
                    return {
                        'duration': 'Just Reset',
                        'start_time': 'Initializing...',
                        'is_valid': True
                    }

                diff = time.time() - start_ts
                
                # Convert to readable format
                m, s = divmod(diff, 60)
                h, m = divmod(m, 60)
                d, h = divmod(h, 24)
                
                if d > 0:
                    uptime_str = f"{int(d)}d {int(h)}h {int(m)}m"
                elif h > 0:
                    uptime_str = f"{int(h)}h {int(m)}m {int(s)}s"
                else:
                    uptime_str = f"{int(m)}m {int(s)}s"

                # Calculate start time string (Thai time)
                utc_time = datetime.fromtimestamp(start_ts, tz=pytz.UTC)
                thailand_time = utc_time.astimezone(THAILAND_TZ)
                start_str = thailand_time.strftime('%Y-%m-%d %H:%M:%S')

                return {
                    'duration': uptime_str,
                    'start_time': start_str,
                    'is_valid': True
                }
        except:
            pass
        return {'duration': 'N/A', 'start_time': 'Unknown', 'is_valid': False}
    
    def _get_heartbeat(self, db):
        """Get last heartbeat"""
        try:
            result = db.table("bot_config").select("value").eq("key", "LAST_HEARTBEAT").execute()
            if result.data:
                last_hb = float(result.data[0]['value'])
                diff = time.time() - last_hb
                
                # Convert to Thailand time
                utc_time = datetime.fromtimestamp(last_hb, tz=pytz.UTC)
                thailand_time = utc_time.astimezone(THAILAND_TZ)
                
                return {
                    'timestamp': thailand_time.strftime('%Y-%m-%d %H:%M:%S'),
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
        
        # Binance - actually test connectivity
        try:
            import requests as req
            api_url = os.environ.get("BINANCE_API_URL", "https://api.binance.com")
            api_key = os.environ.get("BINANCE_API_KEY")
            if api_key:
                try:
                    ping_url = f"{api_url}/api/v1/ping"
                    resp = req.get(ping_url, timeout=5)
                    if resp.status_code == 200:
                        apis['Binance'] = {'status': f'✅ Connected ({api_url})', 'healthy': True}
                    else:
                        apis['Binance'] = {'status': f'⚠️ Reachable but returned {resp.status_code}', 'healthy': False}
                except Exception:
                    apis['Binance'] = {'status': f'❌ Unreachable ({api_url})', 'healthy': False}
            else:
                apis['Binance'] = {'status': '⚠️ Not Configured', 'healthy': False}
        except:
            apis['Binance'] = {'status': '❌ Error', 'healthy': False}

        # Gemini AI + Show current model
        try:
            gemini_key = os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                # Get current AI model from database
                try:
                    result = db.table("bot_config").select("value").eq("key", "AI_MODEL").execute()
                    if result.data:
                        ai_model = result.data[0]['value']
                        apis['Gemini AI'] = {'status': f'✅ Active ({ai_model})', 'healthy': True}
                    else:
                        apis['Gemini AI'] = {'status': '✅ Configured', 'healthy': True}
                except:
                    apis['Gemini AI'] = {'status': '✅ Configured', 'healthy': True}
            else:
                apis['Gemini AI'] = {'status': '⚠️ Not Configured', 'healthy': False}
        except:
            apis['Gemini AI'] = {'status': '❌ Error', 'healthy': False}
        
        return apis
    
    def _get_recent_activity(self, db, limit=5):
        """Get recent bot activity"""
        try:
            # Get recent logs
            logs = db.table("system_logs")\
                .select("role, message, level, created_at")\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()

            return logs.data if logs.data else []
        except:
            return []

    def _get_pnl_summary(self, db):
        """Get P&L summary for both live and sim modes"""
        try:
            result = {
                'live': {'total_pnl': 0, 'win_rate': 0, 'trades': 0, 'wins': 0},
                'sim': {'total_pnl': 0, 'win_rate': 0, 'trades': 0, 'wins': 0}
            }

            # Live positions
            live_closed = db.table("positions").select("pnl").eq("is_sim", False).eq("is_open", False).execute()
            if live_closed.data:
                pnl_values = [float(p['pnl']) for p in live_closed.data if p.get('pnl') is not None]
                if pnl_values:
                    result['live']['total_pnl'] = sum(pnl_values)
                    result['live']['trades'] = len(pnl_values)
                    result['live']['wins'] = len([p for p in pnl_values if p > 0])
                    result['live']['win_rate'] = (result['live']['wins'] / len(pnl_values) * 100)

            # Sim positions
            sim_closed = db.table("positions").select("pnl").eq("is_sim", True).eq("is_open", False).execute()
            if sim_closed.data:
                pnl_values = [float(p['pnl']) for p in sim_closed.data if p.get('pnl') is not None]
                if pnl_values:
                    result['sim']['total_pnl'] = sum(pnl_values)
                    result['sim']['trades'] = len(pnl_values)
                    result['sim']['wins'] = len([p for p in pnl_values if p > 0])
                    result['sim']['win_rate'] = (result['sim']['wins'] / len(pnl_values) * 100)

            return result
        except:
            return {'live': {'total_pnl': 0, 'win_rate': 0, 'trades': 0}, 'sim': {'total_pnl': 0, 'win_rate': 0, 'trades': 0}}
    
    def _generate_html(self, bot_status, heartbeat, api_status, recent_activity, live_logs, pnl_summary=None, uptime=None):
        """Generate status HTML"""

        # Status color
        status_color = '#00ff00' if bot_status['running'] else '#ff0000'
        hb_color = '#00ff00' if heartbeat['healthy'] else '#ff0000'

        # P&L colors
        if pnl_summary:
            live_pnl_color = '#00ff00' if pnl_summary['live']['total_pnl'] >= 0 else '#ff0000'
            sim_pnl_color = '#00ff00' if pnl_summary['sim']['total_pnl'] >= 0 else '#ff0000'
        else:
            live_pnl_color = '#888'
            sim_pnl_color = '#888'
        
        # Uptime String
        if uptime and uptime['is_valid']:
            uptime_display = uptime['duration']
            start_display = uptime['start_time']
        else:
            uptime_display = "N/A"
            start_display = "Unknown"

        # Dead time calculation (if unseen for > 2 mins)
        dead_time_html = ""
        if not heartbeat['healthy']:
            dead_mins = int(heartbeat['ago_seconds'] / 60)
            dead_time_html = f'<div class="metric"><div class="label" style="color: #ff0000;">⚠️ OFFLINE FOR</div><div class="value" style="color: #ff0000;">{dead_mins} mins</div></div>'
        
        # Recent activity HTML
        activity_html = ""
        for log in recent_activity:
            level_color = {
                'SUCCESS': '#00ff00',
                'ERROR': '#ff0000',
                'WARNING': '#ffaa00',
                'INFO': '#00aaff'
            }.get(log.get('level', 'INFO'), '#ffffff')
            
            # Convert timestamp to Thailand time
            try:
                created_at_str = log.get('created_at', 'N/A')
                if created_at_str != 'N/A':
                    # Parse UTC time from database
                    utc_time = datetime.strptime(created_at_str[:19], '%Y-%m-%dT%H:%M:%S')
                    utc_time = pytz.UTC.localize(utc_time)
                    thailand_time = utc_time.astimezone(THAILAND_TZ)
                    time_display = thailand_time.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_display = 'N/A'
            except:
                time_display = created_at_str[:19]
            
            activity_html += f"""
            <tr>
                <td style="color: #888;">{time_display}</td>
                <td style="color: #00aaff;">{log.get('role', 'N/A')}</td>
                <td style="color: {level_color};">{log.get('message', 'N/A')[:100]}</td>
            </tr>
            """

        # Live logs HTML (last 50)
        live_logs_html = ""
        for log in live_logs:
            level_color = {
                'SUCCESS': '#00ff00',
                'ERROR': '#ff0000',
                'WARNING': '#ffaa00',
                'INFO': '#00aaff'
            }.get(log.get('level', 'INFO'), '#ffffff')

            # Convert timestamp to Thailand time
            try:
                created_at_str = log.get('created_at', 'N/A')
                if created_at_str != 'N/A':
                    utc_time = datetime.strptime(created_at_str[:19], '%Y-%m-%dT%H:%M:%S')
                    utc_time = pytz.UTC.localize(utc_time)
                    thailand_time = utc_time.astimezone(THAILAND_TZ)
                    time_display = thailand_time.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_display = 'N/A'
            except:
                time_display = created_at_str[:19]

            msg = log.get('message', 'N/A')
            role = log.get('role', 'N/A')
            level = log.get('level', 'INFO')
            live_logs_html += (
                f"<div class='log-line'>[{time_display}] "
                f"<span style='color:#00aaff'>{role}</span> "
                f"<span style='color:{level_color}'>[{level}]</span> "
                f"{msg}</div>"
            )
        
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
                .log-panel {{
                    background: #0f0f0f;
                    border: 1px solid #222;
                    padding: 10px;
                    height: 320px;
                    overflow-y: auto;
                    font-size: 0.9em;
                }}
                .log-line {{
                    padding: 2px 0;
                    border-bottom: 1px dotted #222;
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
                    <div class="label">Active Duration</div>
                    <div class="value" style="color: #00aaff;">{uptime_display}</div>
                </div>

                {dead_time_html}
                
                <div class="metric">
                    <div class="label">Last Heartbeat</div>
                    <div class="value" style="color: {hb_color};">{heartbeat['ago_seconds']}s ago</div>
                </div>
                
                <h2>📡 API Connections</h2>
                <table>
                    {api_html}
                </table>

                <h2>📈 Trading Performance</h2>
                <table>
                    <tr>
                        <td style="color: #00aaff;">LIVE Trading</td>
                        <td style="color: {live_pnl_color};">${pnl_summary['live']['total_pnl']:,.2f}</td>
                        <td>Win Rate: {pnl_summary['live']['win_rate']:.1f}%</td>
                        <td>{pnl_summary['live']['trades']} trades</td>
                    </tr>
                    <tr>
                        <td style="color: #00aaff;">SIM Trading</td>
                        <td style="color: {sim_pnl_color};">${pnl_summary['sim']['total_pnl']:,.2f}</td>
                        <td>Win Rate: {pnl_summary['sim']['win_rate']:.1f}%</td>
                        <td>{pnl_summary['sim']['trades']} trades</td>
                    </tr>
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

                <h2>🧾 Live Logs (Last 50)</h2>
                <div class="log-panel">
                    {live_logs_html}
                </div>
                
                <div class="footer">
                    Auto-refresh every 10 seconds | Last updated: {datetime.now(THAILAND_TZ).strftime('%Y-%m-%d %H:%M:%S')} (Thailand Time)
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
