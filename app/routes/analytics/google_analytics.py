import os
import json
import psycopg2
from cryptography.fernet import Fernet
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Metric, Dimension
from dotenv import load_dotenv

# Load .env configuration
load_dotenv()

# Database connection
def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

# Decrypt the encrypted JSON blob from DB
def decrypt(encrypted_text):
    key = os.getenv("ENCRYPTION_KEY")
    fernet = Fernet(key.encode())
    return fernet.decrypt(encrypted_text.encode()).decode()

class GoogleAnalyticsFetcher:
    def __init__(self, site_id):
        self.site_id = site_id
        self.site_details = self._load_site()
        self.property_id = self.site_details["ga4_property_id"]
        self.tenant_id = self.site_details["tenant_id"]
        self.credentials = json.loads(decrypt(self.site_details["ga4_credentials_json"]))
        self.client = self._create_client()

    def _load_site(self):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tenant_id, ga4_property_id, ga4_credentials_json 
                    FROM ga_sites 
                    WHERE id = %s
                """, (self.site_id,))
                row = cur.fetchone()
                if not row:
                    raise Exception(f"Site ID not found: {self.site_id}")
                return {
                    "tenant_id": row[0],
                    "ga4_property_id": row[1],
                    "ga4_credentials_json": row[2]
                }

    def _create_client(self):
        credentials = service_account.Credentials.from_service_account_info(self.credentials)
        return BetaAnalyticsDataClient(credentials=credentials)

    def fetch_kpis(self):
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            dimensions=[Dimension(name="sessionSource")],
            metrics=[
                Metric(name="bounceRate"),
                Metric(name="sessionConversionRate"),
                Metric(name="averageSessionDuration"),
                Metric(name="screenPageViewsPerSession")
            ],
            date_ranges=[DateRange(start_date="7daysAgo", end_date="today")]
        )

        response = self.client.run_report(request)

        kpi_data = []
        for row in response.rows:
            kpi_data.append({
                "source": row.dimension_values[0].value,
                "bounceRate": float(row.metric_values[0].value),
                "conversionRate": float(row.metric_values[1].value),
                "avgSessionDuration": float(row.metric_values[2].value),
                "pagesPerSession": float(row.metric_values[3].value)
            })

        return kpi_data

    def save_kpis_to_db(self):
        metrics = self.fetch_kpis()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for row in metrics:
                    cur.execute("""
                        INSERT INTO ga_metrics (
                            site_id, tenant_id, property_id, report_date,
                            session_source, bounce_rate, conversion_rate,
                            avg_session_duration, pages_per_session
                        ) VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s)
                    """, (
                        self.site_id,
                        self.tenant_id,
                        self.property_id,
                        row["source"],
                        row["bounceRate"],
                        row["conversionRate"],
                        row["avgSessionDuration"],
                        row["pagesPerSession"]
                    ))
            conn.commit()
        print(f"✅ GA metrics saved for site {self.site_id}")
