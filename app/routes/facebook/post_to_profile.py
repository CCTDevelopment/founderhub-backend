import requests

def post_directly_to_profile(user_token, message):
    """
    Post directly to your Facebook personal profile feed.
    """
    url = "https://graph.facebook.com/me/feed"
    payload = {
        "message": message,
        "access_token": user_token
    }

    print("📬 Posting directly to your personal Facebook profile...")

    response = requests.post(url, data=payload)

    try:
        response.raise_for_status()
        data = response.json()
        print("✅ Direct post published to your profile!")
        print("🆔 Post ID:", data.get("id"))
        return data.get("id")
    except requests.exceptions.HTTPError:
        print("❌ Failed to post directly:")
        try:
            print(response.json())
        except:
            print("⚠️ Raw response:", response.text)
        return None
