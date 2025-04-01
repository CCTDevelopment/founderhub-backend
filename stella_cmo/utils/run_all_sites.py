import os
import psycopg2
from dotenv import load_dotenv
from google_analytics import GoogleAnalyticsFetcher

load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def run_all_sites():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM ga_sites")
            rows = cur.fetchall()

    for (site_id,) in rows:
        try:
            print(f"📊 Processing site: {site_id}")
            fetcher = GoogleAnalyticsFetcher(site_id)
            fetcher.save_kpis_to_db()
        except Exception as e:
            print(f"❌ Failed for site {site_id}: {e}")

if __name__ == "__main__":
    run_all_sites()
