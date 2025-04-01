import os
import json
import uuid
import psycopg2
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def encrypt(text):
    key = os.getenv("ENCRYPTION_KEY")
    fernet = Fernet(key.encode())
    return fernet.encrypt(text.encode()).decode()

def insert_site_credentials(tenant_id, site_name, property_id, credentials_json_path):
    with open(credentials_json_path, 'r') as f:
        creds = f.read()

    encrypted_creds = encrypt(creds)
    site_id = str(uuid.uuid4())

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ga_sites (id, tenant_id, site_name, ga4_property_id, ga4_credentials_json)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                site_id,
                tenant_id,
                site_name,
                property_id,
                encrypted_creds
            ))
            conn.commit()

    print(f"✅ Site credentials inserted for '{site_name}' with site_id: {site_id}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Encrypt and insert GA credentials into DB")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument("--site-name", required=True, help="Name of the site")
    parser.add_argument("--property-id", required=True, help="GA4 Property ID")
    parser.add_argument("--creds", required=True, help="Path to the credentials JSON file")

    args = parser.parse_args()

    insert_site_credentials(
        tenant_id=args.tenant_id,
        site_name=args.site_name,
        property_id=args.property_id,
        credentials_json_path=args.creds
    )
