import requests

class FacebookPoster:
    def __init__(self, page_token: str):
        self.api_url = "https://graph.facebook.com/me/feed"
        self.page_token = page_token

    def post(self, message: str) -> dict | None:
        """
        Posts a message to the Facebook feed using the provided page token.
        Returns a dict containing the post details if successful; otherwise, returns None.
        """
        payload = {
            "message": message,
            "access_token": self.page_token
        }

        try:
            response = requests.post(self.api_url, data=payload)
            response.raise_for_status()
            result = response.json()
            full_post_id = result.get("id")

            if full_post_id:
                print(f"✅ Post published! Post ID: {full_post_id}")
                if "_" in full_post_id:
                    page_id, post_id = full_post_id.split("_")
                else:
                    page_id = "UNKNOWN"
                    post_id = full_post_id

                return {
                    "post_id": post_id,
                    "page_id": page_id,
                    "full_id": full_post_id
                }
            else:
                print("⚠️ Post published but no post ID returned.")
                return None

        except requests.exceptions.RequestException as e:
            print("❌ Failed to post:", str(e))
            try:
                error_data = response.json()
                print("📡 Facebook error response:", error_data)
            except Exception:
                print("⚠️ Raw response:", response.text)
            return None
