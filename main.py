from commands.telegram_bot import start_bot
from config.config_loader import CONFIG
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import os

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"ArcReactor Bot is running")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    print(f"[Web] Dummy server listening on port {port}")
    server.serve_forever()

if __name__ == "__main__":
    # Start the dummy web server in a background thread
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("[ArcReactor] Launching Telegram Commander...")
    start_bot(CONFIG)
