import os
import json
import time
import requests
from datetime import datetime, timezone
from typing import Dict, Optional


class TokenManager:
    """Manages Dhan API access tokens with automatic renewal."""
    
    def __init__(self, token_file_path="dhan_token.json"):
        """
        Initialize TokenManager.
        
        Args:
            token_file_path: Path to JSON file storing token data
        """
        self.token_file_path = token_file_path
        self.renew_url = "https://api.dhan.co/v2/RenewToken"
        
    def load_token(self) -> Optional[Dict]:
        """
        Load token data from file.
        
        Returns:
            Dict with token data or None if file doesn't exist
        """
        if not os.path.exists(self.token_file_path):
            print(f"[TokenManager] Token file not found: {self.token_file_path}")
            return None
            
        try:
            with open(self.token_file_path, 'r') as f:
                data = json.load(f)
            print(f"[TokenManager] Loaded token from {self.token_file_path}")
            return data
        except Exception as e:
            print(f"[TokenManager] Error loading token: {e}")
            return None
    
    def save_token(self, access_token: str, client_id: str, expires_at: Optional[int] = None):
        """
        Save token data to file.
        
        Args:
            access_token: The access token string
            client_id: Dhan client ID
            expires_at: Unix timestamp of expiry (optional, extracted from JWT if not provided)
        """
        # Extract expiry from JWT if not provided
        if expires_at is None:
            expires_at = self._extract_expiry_from_jwt(access_token)
        
        data = {
            "access_token": access_token,
            "client_id": client_id,
            "expires_at": expires_at,
            "renewed_at": int(time.time())
        }
        
        try:
            with open(self.token_file_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"[TokenManager] Saved token to {self.token_file_path}")
            print(f"[TokenManager] Token expires at: {datetime.fromtimestamp(expires_at, tz=timezone.utc)}")
        except Exception as e:
            print(f"[TokenManager] Error saving token: {e}")
    
    def _extract_expiry_from_jwt(self, token: str) -> int:
        """
        Extract expiry timestamp from JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Expiry timestamp or 0 if extraction fails
        """
        try:
            import base64
            # JWT format: header.payload.signature
            parts = token.split('.')
            if len(parts) != 3:
                return 0
            
            # Decode payload (add padding if needed)
            payload = parts[1]
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.b64decode(payload)
            payload_data = json.loads(decoded)
            
            return payload_data.get('exp', 0)
        except Exception as e:
            print(f"[TokenManager] Error extracting expiry from JWT: {e}")
            return 0
    
    def is_token_expired(self, token_data: Dict, buffer_seconds: int = 300) -> bool:
        """
        Check if token is expired or about to expire.
        
        Args:
            token_data: Token data dict
            buffer_seconds: Renew if expires within this many seconds (default: 5 minutes)
            
        Returns:
            True if expired or about to expire
        """
        if not token_data or 'expires_at' not in token_data:
            return True
        
        expires_at = token_data['expires_at']
        now = int(time.time())
        time_until_expiry = expires_at - now
        
        if time_until_expiry <= buffer_seconds:
            print(f"[TokenManager] Token expires in {time_until_expiry} seconds, needs renewal")
            return True
        
        print(f"[TokenManager] Token valid for {time_until_expiry // 3600} hours")
        return False
    
    def renew_token(self, current_token: str, client_id: str) -> Optional[str]:
        """
        Renew token using Dhan API.
        
        Args:
            current_token: Current access token
            client_id: Dhan client ID
            
        Returns:
            New access token or None if renewal failed
        """
        headers = {
            "access-token": current_token,
            "dhanClientId": client_id
        }
        
        try:
            print(f"[TokenManager] Renewing token via API...")
            response = requests.get(self.renew_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                new_token = data.get('access_token') or data.get('data', {}).get('access_token')
                
                if new_token:
                    print(f"[TokenManager] ✅ Token renewed successfully")
                    # Save the new token
                    self.save_token(new_token, client_id)
                    return new_token
                else:
                    print(f"[TokenManager] ❌ No token in response: {data}")
                    return None
            else:
                print(f"[TokenManager] ❌ Renewal failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"[TokenManager] ❌ Error renewing token: {e}")
            return None
    
    def get_valid_token(self) -> tuple[Optional[str], Optional[str]]:
        """
        Get a valid token, renewing if necessary.
        
        Returns:
            Tuple of (access_token, client_id) or (None, None) if failed
        """
        # Load existing token
        token_data = self.load_token()
        
        if not token_data:
            print("[TokenManager] ❌ No token file found. Please create dhan_token.json first.")
            return None, None
        
        access_token = token_data.get('access_token')
        client_id = token_data.get('client_id')
        
        if not access_token or not client_id:
            print("[TokenManager] ❌ Invalid token data in file")
            return None, None
        
        # Check if renewal needed
        if self.is_token_expired(token_data):
            new_token = self.renew_token(access_token, client_id)
            if new_token:
                return new_token, client_id
            else:
                print("[TokenManager] ⚠️ Renewal failed, using existing token")
                return access_token, client_id
        
        return access_token, client_id


if __name__ == "__main__":
    # Test the TokenManager
    manager = TokenManager()
    token, client_id = manager.get_valid_token()
    
    if token:
        print(f"\n✅ Got valid token for client {client_id}")
        print(f"Token length: {len(token)} chars")
    else:
        print("\n❌ Failed to get valid token")
