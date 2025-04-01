import os
import json
import psycopg2
from cryptography.fernet import Fernet
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Metric,
    Dimension
)
from dotenv import load_dotenv

# Load environment variables (ideally once in your main entry point)
load_dotenv()

def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT", 5432)
    )

def decrypt(encrypted_text: str) -> str:
    key = os.getenv("ENCRYPTION_KEY")
    fernet = Fernet(key.encode())
    return fernet.decrypt(encrypted_text.encode()).decode()

class GoogleAnalyticsFetcher:
    def __init__(self, site_id: str):
        self.site_id = site_id
        self.site_details = self._load_site_details()
        self.property_id = self.site_details["ga4_property_id"]
        self.tenant_id = self.site_details["tenant_id"]
        # Credentials are stored encrypted in the DB; decrypt and load them.
        credentials_json = decrypt(self.site_details["ga4_credentials_json"])
        self.credentials = json.loads(credentials_json)
        self.client = self._create_client()

    def _load_site_details(self) -> dict:
        """Load GA site details from the database using the site ID."""
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tenant_id, ga4_property_id, ga4_credentials_json 
                    FROM ga_sites 
                    WHERE id = %s
                    """,
                    (self.site_id,)
                )
                row = cur.fetchone()
                if not row:
                    raise Exception(f"Site ID not found: {self.site_id}")
                return {
                    "tenant_id": row[0],
                    "ga4_property_id": row[1],
                    "ga4_credentials_json": row[2]
                }

    def _create_client(self) -> BetaAnalyticsDataClient:
        """Create a GA Data API client using credentials from the database."""
        credentials = service_account.Credentials.from_service_account_info(self.credentials)
        return BetaAnalyticsDataClient(credentials=credentials)

    def fetch_kpis(self) -> list:
        """
        Fetch KPIs from Google Analytics using an expanded set of dimensions and metrics.
        Adjust the lists below as needed to capture every detail.
        """
        request = RunReportRequest(
            property=f"properties/{self.property_id}",
            dimensions=[
                Dimension(name="sessionSource"),
                Dimension(name="sessionMedium"),
                Dimension(name="sessionCampaign"),
                Dimension(name="country"),
                Dimension(name="deviceCategory"),
                Dimension(name="browser"),
                Dimension(name="landingPage")
            ],
            metrics=[
                Metric(name="bounceRate"),
                Metric(name="sessionConversionRate"),
                Metric(name="averageSessionDuration"),
                Metric(name="screenPageViewsPerSession"),
                Metric(name="sessions"),
                Metric(name="users"),
                Metric(name="newUsers"),
                Metric(name="engagementRate"),
                Metric(name="eventCount")
            ],
            date_ranges=[DateRange(start_date="7daysAgo", end_date="today")]
        )

        response = self.client.run_report(request)
        kpi_data = []
        for row in response.rows:
            data = {
                "sessionSource": row.dimension_values[0].value,
                "sessionMedium": row.dimension_values[1].value,
                "sessionCampaign": row.dimension_values[2].value,
                "country": row.dimension_values[3].value,
                "deviceCategory": row.dimension_values[4].value,
                "browser": row.dimension_values[5].value,
                "landingPage": row.dimension_values[6].value,
                "bounceRate": float(row.metric_values[0].value),
                "conversionRate": float(row.metric_values[1].value),
                "avgSessionDuration": float(row.metric_values[2].value),
                "pagesPerSession": float(row.metric_values[3].value),
                "sessions": float(row.metric_values[4].value),
                "users": float(row.metric_values[5].value),
                "newUsers": float(row.metric_values[6].value),
                "engagementRate": float(row.metric_values[7].value),
                "eventCount": float(row.metric_values[8].value)
            }
            kpi_data.append(data)
        return kpi_data

    def save_kpis_to_db(self) -> None:
        """
        Saves all fetched KPI details into the SQL table.
        Ensure that your 'ga_metrics' table includes columns for every detail below.
        """
        metrics = self.fetch_kpis()

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for row in metrics:
                    cur.execute(
                        """
                        INSERT INTO ga_metrics (
                            site_id, tenant_id, property_id, report_date,
                            session_source, session_medium, session_campaign, country,
                            device_category, browser, landing_page,
                            bounce_rate, conversion_rate, avg_session_duration,
                            pages_per_session, sessions, users, new_users, engagement_rate,
                            event_count
                        ) VALUES (%s, %s, %s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            self.site_id,
                            self.tenant_id,
                            self.property_id,
                            row["sessionSource"],
                            row["sessionMedium"],
                            row["sessionCampaign"],
                            row["country"],
                            row["deviceCategory"],
                            row["browser"],
                            row["landingPage"],
                            row["bounceRate"],
                            row["conversionRate"],
                            row["avgSessionDuration"],
                            row["pagesPerSession"],
                            row["sessions"],
                            row["users"],
                            row["newUsers"],
                            row["engagementRate"],
                            row["eventCount"]
                        )
                    )
            conn.commit()
        print(f"✅ GA metrics saved for site {self.site_id}")
