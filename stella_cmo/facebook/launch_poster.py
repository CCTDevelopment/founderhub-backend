import os
import json
import openai
from facebook.poster import FacebookPoster  # ✅ Adjust this if needed

openai.api_key = os.getenv("OPENAI_API_KEY")
LAUNCH_LOG = "logs/launch_posted.json"

def generate_launch_post(product_name, site_url, purpose):
    prompt = (
        f"Write a high-converting Facebook launch post for a new product called {product_name}.\n"
        f"The product helps users: {purpose}.\n"
        f"The website is {site_url}.\n"
        "The tone should be exciting, confident, and founder-to-founder. "
        "Include a clear call-to-action and 2 relevant hashtags."
    )

    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=200
    )

    return response.choices[0].message.content.strip()

def has_already_launched():
    return os.path.exists(LAUNCH_LOG)

def mark_as_launched():
    os.makedirs("logs", exist_ok=True)
    with open(LAUNCH_LOG, "w") as f:
        json.dump({"posted": True}, f)

def post_launch_to_facebook():
    if has_already_launched():
        print("✅ Launch post already published. Skipping.")
        return None  # Must return None if nothing posted

    product_name = "FounderHub.ai"
    site_url = "https://founderhub.ai"
    purpose = "validate and refine startup ideas before founders spend time or money"

    print("🚀 Generating and publishing your launch post...")
    message = generate_launch_post(product_name, site_url, purpose)

    page_token = os.getenv("FB_PAGE_TOKEN")
    poster = FacebookPoster(page_token)
    post_result = poster.post(message)  # post_result is a dict

    if post_result:
        mark_as_launched()
        print("✅ Launch post published and logged.")
        return post_result  # ✅ You MUST return the dict
    else:
        print("❌ Failed to publish launch post.")
        return None
