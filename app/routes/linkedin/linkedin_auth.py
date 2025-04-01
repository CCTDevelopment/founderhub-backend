import os
import requests
import webbrowser
import json
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
import psycopg2
import uuid
from datetime import datetime
from cryptography.fernet import Fernet

# Load environment variables for things that remain in env (e.g. encryption key and DB credentials)
load_dotenv()

# Constant URLs (these remain unchanged)
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"

# Encryption key (should remain in env for security)
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise RuntimeError("ENCRYPTION_KEY environment variable is not set!")
fernet = Fernet(ENCRYPTION_KEY.encode())

def get_db_connection():
    """
    Establishes and returns a connection to the Postgres database.
    """
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def get_linkedin_config() -> dict:
    """
    Fetches LinkedIn OAuth credentials from the SQL table 'linkedin_config'.
    Assumes the table has columns: client_id, client_secret, redirect_uri.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT client_id, client_secret, redirect_uri FROM linkedin_config LIMIT 1")
            row = cur.fetchone()
            if not row:
                raise Exception("LinkedIn configuration not found in the database.")
            return {
                "client_id": row[0],
                "client_secret": row[1],
                "redirect_uri": row[2]
            }
    finally:
        conn.close()

def encrypt_token(token: str) -> str:
    """Encrypts the provided token using Fernet encryption."""
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypts the provided encrypted token."""
    return fernet.decrypt(encrypted_token.encode()).decode()

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

def get_authorization_code() -> str | None:
    """
    Opens a browser window for LinkedIn OAuth authorization and waits for the callback.
    Returns the authorization code if successful.
    """
    # Fetch LinkedIn configuration from SQL
    config = get_linkedin_config()
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "scope": "w_member_social"
    }

    url = f"{AUTH_URL}?{requests.compat.urlencode(params)}"
    print(f"🔗 Opening browser to: {url}")
    webbrowser.open(url)

    server = HTTPServer(("localhost", 3000), OAuthCallbackHandler)
    print("⏳ Waiting for LinkedIn OAuth callback on http://localhost:3000...")
    server.handle_request()
    return getattr(server, "auth_code", None)

def exchange_code_for_token(code: str) -> str:
    """
    Exchanges the provided authorization code for an access token, encrypts it,
    and stores the encrypted token in the SQL database.
    Returns the raw access token.
    """
    # Fetch LinkedIn configuration from SQL
    config = get_linkedin_config()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config["redirect_uri"],
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
    }

    response = requests.post(TOKEN_URL, data=data)
    response.raise_for_status()
    token = response.json().get("access_token")

    if token:
        print("✅ Access token retrieved.")
        encrypted_token = encrypt_token(token)
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO linkedin_tokens (id, access_token, created_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                        SET access_token = EXCLUDED.access_token,
                            created_at = EXCLUDED.created_at
                    """,
                    (str(uuid.uuid4()), encrypted_token, datetime.utcnow())
                )
            conn.commit()
            print("✅ Access token encrypted and stored in SQL.")
        finally:
            conn.close()
    else:
        print("❌ Failed to retrieve access token.")

    return token
