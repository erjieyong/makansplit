import json
import os
from typing import Optional, Dict


class PayNowStorage:
    """Store and retrieve user PayNow information."""

    def __init__(self, storage_file: str = "user_paynow.json"):
        self.storage_file = storage_file
        self._load_storage()

    def _load_storage(self):
        """Load storage from file."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def _save_storage(self):
        """Save storage to file."""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"Error saving PayNow storage: {e}")

    def get_user_paynow(self, user_id: int) -> Optional[Dict[str, str]]:
        """
        Get PayNow info for a user.

        Args:
            user_id: Telegram user ID

        Returns:
            Dict with 'phone' and 'name' keys, or None if not found
        """
        user_key = str(user_id)
        return self.data.get(user_key)

    def save_user_paynow(self, user_id: int, phone: str, name: str):
        """
        Save PayNow info for a user.

        Args:
            user_id: Telegram user ID
            phone: Phone number with country code
            name: Recipient name
        """
        user_key = str(user_id)
        self.data[user_key] = {
            'phone': phone,
            'name': name
        }
        self._save_storage()

    def delete_user_paynow(self, user_id: int):
        """
        Delete PayNow info for a user.

        Args:
            user_id: Telegram user ID
        """
        user_key = str(user_id)
        if user_key in self.data:
            del self.data[user_key]
            self._save_storage()
