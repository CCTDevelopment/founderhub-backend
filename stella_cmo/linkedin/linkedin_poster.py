import requests

class LinkedInPoster:
    def __init__(self, access_token, person_urn):
        self.token = access_token
        self.person_urn = person_urn
        self.api_url = "https://api.linkedin.com/v2/ugcPosts"

    def post(self, message):
        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": message
                    },
                    "shareMediaCategory": "NONE"
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        response = requests.post(self.api_url, json=payload, headers=headers)
        if response.status_code == 201:
            print("✅ LinkedIn post published!")
            print(response.json())
        else:
            print("❌ Failed to post:", response.text)
