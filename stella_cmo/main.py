from dotenv import load_dotenv
import os
import json

from analytics.google_analytics import GoogleAnalyticsFetcher
from analytics.anomaly_detector import AnomalyDetector
from analytics.decision_logger import log_decision

from facebook.poster import FacebookPoster
from facebook.launch_poster import post_launch_to_facebook
from facebook.share_to_profile import get_permalink_url
from facebook.post_to_profile import post_directly_to_profile  # ✅ new

from linkedin.linkedin_poster import LinkedInPoster
from linkedin.linkedin_auth import get_authorization_code, exchange_code_for_token
from facebook.launch_poster import generate_launch_post  # ✅ needed for direct profile post

# Load environment variables
load_dotenv()

# GA4
GA4_PROPERTY_ID = os.getenv("GA4_PROPERTY_ID")
CREDENTIALS_PATH = os.getenv("GA4_CREDENTIALS_PATH")

# Facebook
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_PAGE_TOKEN = os.getenv("FB_PAGE_TOKEN")
FB_USER_TOKEN = os.getenv("FB_USER_TOKEN")  # Personal profile token

# LinkedIn
LINKEDIN_PERSON_URN = os.getenv("LINKEDIN_PERSON_URN")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")  # Can fallback to token.json


def run_stella_analytics():
    fetcher = GoogleAnalyticsFetcher(GA4_PROPERTY_ID, CREDENTIALS_PATH)
    fetcher.save_kpis_to_file()

    with open("analytics_data.json") as f:
        data = json.load(f)

    kpi_fields = {
        "bounceRate": [],
        "conversionRate": [],
        "avgSessionDuration": [],
        "pagesPerSession": []
    }

    detector = AnomalyDetector()
    any_anomalies = False

    print("\n📉 Anomaly Detection Results:")
    for item in data:
        for kpi in kpi_fields:
            if kpi in item:
                kpi_fields[kpi].append(item[kpi])

    for kpi, values in kpi_fields.items():
        result = detector.detect(values)
        log_decision("StellaAICMO", kpi, result, "Daily automated KPI scan")
        print(f"{kpi}: {result['status']}")
        print(f"  Current: {result['current']:.2f} | Avg: {result['average']:.2f} | Std Dev: {result['std_dev']:.2f}\n")
        if result["status"] == "anomaly_detected":
            any_anomalies = True

    return any_anomalies


if __name__ == "__main__":
    print("📊 StellaAICMO is collecting analytics data...")

    # STEP 1: Launch Post (Only Runs Once)
    launch_post = post_launch_to_facebook()

    # STEP 1.5: If launch was posted, replicate post directly to your profile
    if FB_USER_TOKEN and launch_post:
        print("📬 Posting launch content directly to your profile (not shared)...")
        message = generate_launch_post(
            product_name="FounderHub.ai",
            site_url="https://founderhub.ai",
            purpose="validate and refine startup ideas before founders spend time or money"
        )
        post_directly_to_profile(FB_USER_TOKEN, message)

    # STEP 2: Anomaly Monitoring + Social Posting
    found_anomaly = run_stella_analytics()

    if found_anomaly:
        message = "⚠️ Stella detected unusual activity in traffic. Adjustments underway. #AI #Marketing"
        print("🚨 Anomaly detected — posting update to Facebook and LinkedIn!")

        # Facebook Page Post
        post_result = None
        if FB_PAGE_TOKEN:
            fb_poster = FacebookPoster(FB_PAGE_TOKEN)
            post_result = fb_poster.post(message)

        # Direct Post to Facebook Profile (no more share headaches)
        if FB_USER_TOKEN and post_result:
            print("📬 Posting anomaly message directly to personal profile...")
            post_directly_to_profile(FB_USER_TOKEN, message)

        # LinkedIn Token Check
        if not LINKEDIN_ACCESS_TOKEN:
            try:
                with open("linkedin/token.json") as f:
                    LINKEDIN_ACCESS_TOKEN = json.load(f).get("access_token")
            except Exception:
                pass

        if not LINKEDIN_ACCESS_TOKEN:
            print("🔑 No LinkedIn token found. Starting OAuth...")
            code = get_authorization_code()
            if code:
                LINKEDIN_ACCESS_TOKEN = exchange_code_for_token(code)
                if LINKEDIN_ACCESS_TOKEN:
                    print("✅ Token received. Saving to linkedin/token.json...")
                    os.makedirs("linkedin", exist_ok=True)
                    with open("linkedin/token.json", "w") as f:
                        json.dump({"access_token": LINKEDIN_ACCESS_TOKEN}, f)
            else:
                print("❌ OAuth failed. Could not get authorization code.")

        # LinkedIn Post
        if LINKEDIN_ACCESS_TOKEN:
            linkedin_poster = LinkedInPoster(LINKEDIN_ACCESS_TOKEN, LINKEDIN_PERSON_URN)
            linkedin_poster.post(message)
        else:
            print("🚫 Skipping LinkedIn post — access token not available.")
    else:
        print("✅ All clear. No anomalies today.")
