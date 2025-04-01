import requests
import json

def get_permalink_url(page_id, post_id, page_token):
    """
    Get the permalink URL of a Facebook Page post.
    """
    full_post_id = f"{page_id}_{post_id}"
    url = f"https://graph.facebook.com/v18.0/{full_post_id}"
    params = {
        "fields": "permalink_url",
        "access_token": page_token
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        permalink = response.json().get("permalink_url")
        print(f"🔗 Permalink fetched: {permalink}")
        return permalink
    else:
        print("❌ Failed to fetch permalink:")
        print(json.dumps(response.json(), indent=2))
        return None


def share_post_to_profile(user_token, message, link):
    url = "https://graph.facebook.com/me/feed"
    payload = {
        "message": message,
        "link": link,
        "access_token": user_token
    }

    print("📤 Attempting to share to personal profile...")
    print(f"📝 Message: {message}")
    print(f"🔗 Link: {link}")

    response = requests.post(url, data=payload)

    try:
        response.raise_for_status()
        data = response.json()
        print("✅ Successfully shared to your personal profile!")
        print("🆔 Shared Post ID:", data.get("id"))
        return data.get("id")
    except requests.exceptions.HTTPError:
        print("❌ Failed to share to profile:")
        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print("⚠️ Raw response:", response.text)
        return None
