import json
import os
from typing import Dict, Optional, List
from PIL import Image
import google.generativeai as genai
from config import GEMINI_API_KEY, TEMP_DIR

genai.configure(api_key=GEMINI_API_KEY)


class UserMatcher:
    """Handle manual user matching and persistent storage of pairings."""

    def __init__(self, storage_file: str = "user_pairings.json"):
        self.storage_file = storage_file
        self.model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-09-2025')

    def load_pairings(self, chat_id: int) -> Dict[str, Dict]:
        """
        Load saved user pairings for a specific chat.

        Returns:
            Dict mapping person_description to pairing data:
            {
                'person_key': {
                    'telegram_user_id': int,
                    'headshot': str (optional path)
                }
            }
        """
        if not os.path.exists(self.storage_file):
            return {}

        try:
            with open(self.storage_file, 'r') as f:
                all_pairings = json.load(f)
                chat_pairings = all_pairings.get(str(chat_id), {})

                # Handle old format (just user_id) and new format (dict with user_id and headshot)
                normalized_pairings = {}
                for key, value in chat_pairings.items():
                    if isinstance(value, int):
                        # Old format: convert to new format
                        normalized_pairings[key] = {'telegram_user_id': value}
                    else:
                        # New format
                        normalized_pairings[key] = value

                return normalized_pairings
        except Exception as e:
            print(f"Error loading pairings: {e}")
            return {}

    def save_pairing(
        self, chat_id: int, person_description: str, telegram_user_id: int, headshot_path: Optional[str] = None
    ):
        """
        Save a person-to-telegram pairing with optional reference headshot.

        Args:
            chat_id: The chat ID
            person_description: The person key/description
            telegram_user_id: The Telegram user ID
            headshot_path: Optional path to the headshot image to save as reference
        """
        all_pairings = {}

        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    all_pairings = json.load(f)
            except Exception:
                pass

        chat_key = str(chat_id)
        if chat_key not in all_pairings:
            all_pairings[chat_key] = {}

        # Save the pairing
        pairing_data = {
            'telegram_user_id': telegram_user_id
        }

        # If headshot provided, save it permanently
        if headshot_path and os.path.exists(headshot_path):
            # Create saved_headshots directory
            saved_dir = os.path.join(TEMP_DIR, 'saved_headshots')
            os.makedirs(saved_dir, exist_ok=True)

            # Generate permanent filename
            saved_headshot_path = os.path.join(
                saved_dir, f"{chat_id}_{person_description.replace(' ', '_')}.jpg"
            )

            # Copy the headshot to permanent location
            try:
                import shutil
                shutil.copy2(headshot_path, saved_headshot_path)
                pairing_data['headshot'] = saved_headshot_path
                print(f"Saved reference headshot: {saved_headshot_path}")
            except Exception as e:
                print(f"Error saving headshot: {e}")

        all_pairings[chat_key][person_description] = pairing_data

        with open(self.storage_file, 'w') as f:
            json.dump(all_pairings, f, indent=2)

    def get_all_pairings_for_chat(self, chat_id: int) -> Dict[str, int]:
        """Get all saved pairings for a chat."""
        return self.load_pairings(chat_id)

    async def extract_person_headshots(
        self, group_photo_path: str, people_data: Dict
    ) -> Dict[int, str]:
        """
        Extract headshot crops for each person detected in the group photo.
        Uses Gemini Vision to identify crop coordinates for each person.

        Returns:
            Dict mapping person_id to cropped headshot image path
        """
        try:
            image = Image.open(group_photo_path)
            width, height = image.size

            people_list = '\n'.join([
                f"Person {p['person_id']}: {p['position']}"
                for p in people_data['people']
            ])

            prompt = f"""
            Analyze this group photo and identify the bounding box coordinates for each person's head/face.

            People in the photo:
            {people_list}

            For each person, provide the crop coordinates as percentages (0-100) of the image dimensions.
            Return ONLY a valid JSON object with this structure:
            {{
                "crops": [
                    {{
                        "person_id": 1,
                        "left": 10.5,
                        "top": 15.2,
                        "right": 35.8,
                        "bottom": 55.3
                    }},
                    ...
                ]
            }}

            Important:
            - Coordinates are percentages of image width/height
            - left, top, right, bottom define the bounding box
            - Include some shoulder area, not just the face
            - Only return the JSON, no additional text
            """

            response = self.model.generate_content([prompt, image])
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]

            data = json.loads(response_text.strip())

            # Crop and save headshots
            headshots = {}
            for crop_info in data['crops']:
                person_id = crop_info['person_id']

                # Convert percentages to pixels
                left = int(crop_info['left'] * width / 100)
                top = int(crop_info['top'] * height / 100)
                right = int(crop_info['right'] * width / 100)
                bottom = int(crop_info['bottom'] * height / 100)

                # Crop the image
                headshot = image.crop((left, top, right, bottom))

                # Save headshot
                headshot_path = os.path.join(
                    TEMP_DIR, f"headshot_person_{person_id}.jpg"
                )
                headshot.save(headshot_path)

                headshots[person_id] = headshot_path

            return headshots

        except Exception as e:
            print(f"Error extracting headshots: {e}")
            # Fallback: return empty dict, will use full group photo
            return {}

    def generate_person_key(self, person: Dict) -> str:
        """
        Generate a stable key for a person based on their characteristics.
        This key is used to match people across different bill splits.
        """
        # Use position as the primary identifier
        # In future, could add more sophisticated matching
        return f"person_{person['position'].lower().replace(' ', '_')}"

    def find_matching_person(
        self, person: Dict, saved_pairings: Dict[str, Dict]
    ) -> Optional[int]:
        """
        Try to find a saved pairing for this person.

        Returns:
            telegram_user_id if found, None otherwise
        """
        person_key = self.generate_person_key(person)
        pairing_data = saved_pairings.get(person_key)
        if pairing_data:
            return pairing_data.get('telegram_user_id')
        return None

    def get_saved_headshot(
        self, person: Dict, saved_pairings: Dict[str, Dict]
    ) -> Optional[str]:
        """
        Get the saved headshot path for a person if available.

        Returns:
            Path to saved headshot image, or None
        """
        person_key = self.generate_person_key(person)
        pairing_data = saved_pairings.get(person_key)
        if pairing_data:
            headshot_path = pairing_data.get('headshot')
            if headshot_path and os.path.exists(headshot_path):
                return headshot_path
        return None
