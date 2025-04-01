import os
import requests
import webbrowser
import json
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI")

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        code = query_params.get("code", [None])[0]

        if code:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write("<h1>✅ Authorization successful! You can close this window.</h1>".encode("utf-8"))
            self.server.auth_code = code
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("<h1>Authorization failed. No code found.</h1>".encode("utf-8"))

def get_authorization_code():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "w_member_social"
    }

    url = f"{AUTH_URL}?{requests.compat.urlencode(params)}"
    print(f"🔗 Opening browser to: {url}")
    webbrowser.open(url)

    server = HTTPServer(("localhost", 3000), OAuthCallbackHandler)
    print("⏳ Waiting for LinkedIn OAuth callback on http://localhost:3000...")
    server.handle_request()
    return getattr(server, "auth_code", None)

def exchange_code_for_token(code):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    response = requests.post(TOKEN_URL, data=data)
    response.raise_for_status()
    token = response.json().get("access_token")

    if token:
        print("✅ Access token retrieved and saved.")
        os.makedirs("linkedin", exist_ok=True)
        with open("linkedin/token.json", "w") as f:
            json.dump({"access_token": token}, f)
    else:
        print("❌ Failed to retrieve access token.")

    return token
