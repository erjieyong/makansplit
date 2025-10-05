import google.generativeai as genai
from PIL import Image
import json
from typing import Dict, List, Optional
import aiohttp
import os
from config import GEMINI_API_KEY, TEMP_DIR

genai.configure(api_key=GEMINI_API_KEY)


class PersonMatcher:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-09-2025')

    async def analyze_group_photo(
        self, group_photo_path: str, bill_items: List[Dict]
    ) -> Dict:
        """
        Analyze group photo and match people to food items.

        Returns:
            Dict with structure:
            {
                'people': [
                    {
                        'person_id': int,
                        'position': str,
                        'items': [item_index, ...],
                        'share_ratio': {item_index: float}  # For shared items
                    }
                ],
                'confidence': float
            }
        """
        try:
            image = Image.open(group_photo_path)

            items_list = '\n'.join(
                [f"{i+1}. {item['name']} - ${item['price']:.2f}" for i, item in enumerate(bill_items)]
            )

            prompt = f"""
            Analyze this photo of people dining together. Your task is to:

            1. Identify and count all people in the photo
            2. Describe their seating positions (e.g., "person on left", "person in center", etc.)
            3. Identify the food items in front of or near each person
            4. Match each person to the items from this bill:

            {items_list}

            Return ONLY a valid JSON object with this structure:
            {{
                "people": [
                    {{
                        "person_id": 1,
                        "position": "description of position",
                        "items": [1, 3],
                        "share_ratio": {{"1": 1.0, "3": 0.5}},
                        "confidence": 0.85
                    }},
                    ...
                ],
                "overall_confidence": 0.80,
                "notes": "Any observations or uncertainties"
            }}

            Important:
            - person_id starts from 1
            - items array contains 1-based indices from the bill
            - share_ratio indicates how much of each item this person consumed (1.0 = whole item, 0.5 = half, etc.)
            - If an item is shared, multiple people can have the same item with different share ratios
            - The sum of share_ratios for each item across all people should equal 1.0
            - confidence is a number between 0 and 1 indicating how certain you are about this person's matches
            - If you cannot clearly identify food for someone, set confidence low and add notes
            - Only return the JSON, no additional text
            """

            response = self.model.generate_content([prompt, image])

            # Extract JSON from response
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]

            data = json.loads(response_text.strip())

            return data

        except Exception as e:
            raise Exception(f"Error analyzing group photo: {str(e)}")

    async def match_faces_to_telegram(
        self, group_photo_path: str, user_photos: Dict[int, str], people_data: Dict
    ) -> Dict[int, int]:
        """
        Match detected people in group photo to Telegram users via facial recognition.

        Args:
            group_photo_path: Path to group photo
            user_photos: Dict mapping user_id to profile photo path
            people_data: Output from analyze_group_photo

        Returns:
            Dict mapping person_id to telegram_user_id
        """
        if not user_photos:
            return {}

        try:
            group_image = Image.open(group_photo_path)

            # Build description of profile photos
            profile_descriptions = []
            for user_id, photo_path in user_photos.items():
                profile_descriptions.append(f"Telegram User {user_id}: Profile photo at {photo_path}")

            people_descriptions = []
            for person in people_data['people']:
                people_descriptions.append(
                    f"Person {person['person_id']}: {person['position']}"
                )

            # Load all profile photos
            profile_images = []
            for user_id, photo_path in user_photos.items():
                try:
                    profile_images.append((user_id, Image.open(photo_path)))
                except Exception as e:
                    print(f"Error loading profile photo for user {user_id}: {e}")

            prompt = f"""
            You are analyzing a group dining photo. Here are the people identified:
            {chr(10).join(people_descriptions)}

            I will show you profile pictures of Telegram users. Match each person in the group photo to their Telegram profile picture using facial recognition.

            Return ONLY a valid JSON object with this structure:
            {{
                "matches": {{
                    "1": telegram_user_id or null,
                    "2": telegram_user_id or null,
                    ...
                }},
                "confidence": {{
                    "1": 0.85,
                    "2": 0.60,
                    ...
                }},
                "notes": "Any observations about difficult matches"
            }}

            Important:
            - Keys in matches are person_id (as strings), values are telegram user IDs (as integers) or null
            - Only make matches you are confident about (confidence > 0.6)
            - If you cannot match a person confidently, set their value to null
            - Only return the JSON, no additional text
            """

            # Create content list with group photo and all profile photos
            content = [prompt, group_image]
            for user_id, img in profile_images:
                content.append(f"Telegram User {user_id} profile:")
                content.append(img)

            response = self.model.generate_content(content)

            # Extract JSON from response
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]

            data = json.loads(response_text.strip())

            # Convert string keys to int
            matches = {}
            for person_id_str, user_id in data['matches'].items():
                if user_id is not None:
                    matches[int(person_id_str)] = user_id

            return matches

        except Exception as e:
            print(f"Error matching faces: {str(e)}")
            return {}

    def calculate_person_totals(
        self, people_data: Dict, bill_items: List[Dict]
    ) -> Dict[int, float]:
        """
        Calculate total amount owed by each person.

        Returns:
            Dict mapping person_id to total amount owed
        """
        totals = {}

        for person in people_data['people']:
            person_id = person['person_id']
            total = 0.0

            for item_index in person['items']:
                # Convert to 0-based index
                item = bill_items[item_index - 1]

                # Get share ratio (default to 1.0 if not specified)
                share_ratio = person.get('share_ratio', {}).get(str(item_index), 1.0)

                # Add proportional cost (including tax and service charge)
                total += item['total_price'] * share_ratio

            totals[person_id] = round(total, 2)

        return totals

    def format_analysis_summary(
        self, people_data: Dict, bill_items: List[Dict], totals: Dict[int, float], matches: Optional[Dict[int, int]] = None
    ) -> str:
        """Format the person-food matching analysis into readable text."""
        lines = []
        lines.append("👥 *Person-Food Matching Analysis*\n")

        for person in people_data['people']:
            person_id = person['person_id']
            lines.append(f"*Person {person_id}* ({person['position']})")

            if matches and person_id in matches:
                lines.append(f"✓ Matched to Telegram user")

            lines.append(f"Confidence: {person.get('confidence', 0):.0%}")
            lines.append(f"Items:")

            for item_index in person['items']:
                item = bill_items[item_index - 1]
                share_ratio = person.get('share_ratio', {}).get(str(item_index), 1.0)

                if share_ratio == 1.0:
                    lines.append(f"  • {item['name']} - ${item['total_price']:.2f}")
                else:
                    lines.append(
                        f"  • {item['name']} ({share_ratio:.0%} share) - ${item['total_price'] * share_ratio:.2f}"
                    )

            lines.append(f"*Total: ${totals[person_id]:.2f}*\n")

        lines.append(f"\nOverall confidence: {people_data.get('overall_confidence', 0):.0%}")

        if people_data.get('notes'):
            lines.append(f"\nNotes: {people_data['notes']}")

        return '\n'.join(lines)

    async def download_telegram_photo(
        self, file_path: str, user_id: int
    ) -> str:
        """Download a Telegram photo and save it locally."""
        local_path = os.path.join(TEMP_DIR, f"profile_{user_id}.jpg")

        async with aiohttp.ClientSession() as session:
            async with session.get(file_path) as response:
                if response.status == 200:
                    with open(local_path, 'wb') as f:
                        f.write(await response.read())
                    return local_path

        raise Exception(f"Failed to download photo for user {user_id}")
