import requests
from typing import Optional, Dict, Any

class LinkedInPoster:
    def __init__(self, access_token: str, person_urn: str) -> None:
        self.token: str = access_token
        self.person_urn: str = person_urn
        self.api_url: str = "https://api.linkedin.com/v2/ugcPosts"

    def post(self, message: str) -> Optional[Dict[str, Any]]:
        """
        Publishes a post to LinkedIn using the UGC API.
        
        Args:
            message (str): The text content of the post.
        
        Returns:
            dict: The JSON response from LinkedIn if the post is successful.
            None: If the post fails.
        """
        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": message},
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
            result = response.json()
            print(result)
            return result
        else:
            print("❌ Failed to post:", response.text)
            return None
