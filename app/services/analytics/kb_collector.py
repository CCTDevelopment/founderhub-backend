import json
import uuid
import logging
from datetime import datetime
from typing import Any

from google.analytics.data_v1beta import (
    BetaAnalyticsDataClient,
    RunReportRequest,
    DateRange,
    Metric,
    Dimension
)
from google.oauth2 import service_account

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

async def collect_kpi_snapshots(db: Any, site_id: str) -> bool:
    """
    Production-ready function to collect Google Analytics KPI snapshots for a given site.

    Steps:
    1. Retrieve site details from the 'ga_sites' table.
    2. Load GA credentials (as JSON) from the database record.
    3. Instantiate the BetaAnalyticsDataClient using the service account credentials.
    4. Build and send a RunReportRequest for key metrics over the past 7 days.
    5. Parse the response and insert each KPI snapshot into the 'ga_kpi_snapshots' table.

    Assumptions:
      - The 'ga_sites' table has columns: tenant_id, ga4_property_id, ga4_credentials_json.
      - The 'ga_kpi_snapshots' table is structured as shown above.
    """
    # Step 1: Retrieve site details.
    query = """
    SELECT tenant_id, ga4_property_id, ga4_credentials_json
    FROM ga_sites
    WHERE id = :site_id
    """
    site = await db.fetch_one(query=query, values={"site_id": site_id})
    if not site:
        logger.error("Site %s not found.", site_id)
        raise Exception("Site not found.")

    tenant_id = site["tenant_id"]
    property_id = site["ga4_property_id"]
    credentials_json = site["ga4_credentials_json"]

    # Step 2: Load GA credentials.
    try:
        credentials_info = json.loads(credentials_json)
    except Exception as e:
        logger.error("Error parsing GA credentials for site %s: %s", site_id, e)
        raise

    # Step 3: Instantiate the GA client.
    try:
        credentials = service_account.Credentials.from_service_account_info(credentials_info)
        client = BetaAnalyticsDataClient(credentials=credentials)
    except Exception as e:
        logger.error("Error creating GA client for site %s: %s", site_id, e)
        raise

    # Step 4: Build and send the RunReportRequest.
    report_request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="sessionSource")],
        metrics=[
            Metric(name="bounceRate"),
            Metric(name="sessionConversionRate"),
            Metric(name="averageSessionDuration"),
            Metric(name="screenPageViewsPerSession")
        ],
        date_ranges=[DateRange(start_date="7daysAgo", end_date="today")]
    )
    try:
        response = client.run_report(report_request)
    except Exception as e:
        logger.error("Error running GA report for site %s: %s", site_id, e)
        raise

    # Step 5: Parse the response and store snapshots.
    report_date = datetime.utcnow().date()  # Use current date as report date.
    now = datetime.utcnow()
    insert_query = """
    INSERT INTO ga_kpi_snapshots 
    (id, site_id, tenant_id, property_id, kpi_name, value, report_date, created_at)
    VALUES (:id, :site_id, :tenant_id, :property_id, :kpi_name, :value, :report_date, :created_at)
    """
    try:
        for row in response.rows:
            # We assume one dimension; we ignore its value for now.
            bounce_rate = float(row.metric_values[0].value)
            conversion_rate = float(row.metric_values[1].value)
            avg_session_duration = float(row.metric_values[2].value)
            pages_per_session = float(row.metric_values[3].value)

            # Create a snapshot entry for each KPI.
            for kpi_name, value in [
                ("bounce_rate", bounce_rate),
                ("conversion_rate", conversion_rate),
                ("avg_session_duration", avg_session_duration),
                ("pages_per_session", pages_per_session)
            ]:
                snapshot_values = {
                    "id": str(uuid.uuid4()),
                    "site_id": site_id,
                    "tenant_id": tenant_id,
                    "property_id": property_id,
                    "kpi_name": kpi_name,
                    "value": value,
                    "report_date": report_date,
                    "created_at": now,
                }
                await db.execute(query=insert_query, values=snapshot_values)
        logger.info("KPI snapshots collected successfully for site %s", site_id)
    except Exception as e:
        logger.error("Error storing KPI snapshots for site %s: %s", site_id, e)
        raise

    return True
