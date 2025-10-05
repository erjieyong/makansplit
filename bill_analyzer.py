import google.generativeai as genai
from PIL import Image
import json
import base64
import requests
from io import BytesIO
from typing import Dict, List
from config import GEMINI_API_KEY, OPENROUTER_API_KEY, OPENROUTER_MODEL


class BillAnalyzer:
    def __init__(self):
        # Determine which AI provider to use
        self.use_openrouter = bool(OPENROUTER_API_KEY)

        if self.use_openrouter:
            self.openrouter_api_key = OPENROUTER_API_KEY
            self.openrouter_model = OPENROUTER_MODEL
            print(f"Using OpenRouter with model: {self.openrouter_model}")
        else:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-09-2025')
            print("Using Gemini API")

    def _analyze_with_openrouter(self, image_path: str, prompt: str) -> str:
        """Analyze image using OpenRouter API."""
        # Read and encode image
        with open(image_path, 'rb') as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')

        # Determine image MIME type
        if image_path.lower().endswith('.png'):
            mime_type = 'image/png'
        elif image_path.lower().endswith('.jpg') or image_path.lower().endswith('.jpeg'):
            mime_type = 'image/jpeg'
        else:
            mime_type = 'image/jpeg'  # default

        headers = {
            'Authorization': f'Bearer {self.openrouter_api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.openrouter_model,
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': prompt
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': f'data:{mime_type};base64,{image_data}'
                            }
                        }
                    ]
                }
            ]
        }

        response = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers=headers,
            json=data
        )

        if response.status_code != 200:
            raise Exception(f"OpenRouter API error: {response.status_code} - {response.text}")

        result = response.json()
        return result['choices'][0]['message']['content']

    def _analyze_with_gemini(self, image_path: str, prompt: str) -> str:
        """Analyze image using Gemini API."""
        image = Image.open(image_path)
        response = self.model.generate_content([prompt, image])
        return response.text

    def analyze_bill(self, image_path: str) -> Dict:
        """
        Analyze a bill image and extract itemized information.

        Returns:
            Dict with structure:
            {
                'items': [{'name': str, 'price': float}],
                'subtotal': float,
                'tax': float,
                'service_charge': float,
                'total': float,
                'restaurant': str (optional)
            }
        """
        try:
            prompt = """
            Analyze this restaurant bill and extract the following information in JSON format:

            1. All itemized food and drink items with their individual prices
            2. Subtotal (before tax and service charge)
            3. Tax amount (GST or other taxes)
            4. Service charge amount
            5. Total amount
            6. Restaurant name (if visible)

            Return ONLY a valid JSON object with this structure:
            {
                "items": [
                    {"name": "Item name", "price": 12.50},
                    ...
                ],
                "subtotal": 100.00,
                "tax": 8.00,
                "service_charge": 10.00,
                "total": 118.00,
                "restaurant": "Restaurant Name"
            }

            Important:
            - Extract ALL items from the bill
            - Prices should be numbers (float), not strings
            - If tax or service charge is not shown separately, set to 0
            - Be precise with the numbers
            - Only return the JSON, no additional text
            """

            # Choose provider
            if self.use_openrouter:
                response_text = self._analyze_with_openrouter(image_path, prompt)
            else:
                response_text = self._analyze_with_gemini(image_path, prompt)

            # Extract JSON from response
            response_text = response_text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]

            data = json.loads(response_text.strip())

            # Calculate proportional charges per item
            if data['subtotal'] > 0:
                tax_rate = data['tax'] / data['subtotal']
                service_rate = data['service_charge'] / data['subtotal']

                for item in data['items']:
                    item['tax'] = round(item['price'] * tax_rate, 2)
                    item['service_charge'] = round(item['price'] * service_rate, 2)
                    item['total_price'] = round(
                        item['price'] + item['tax'] + item['service_charge'], 2
                    )

            return data

        except Exception as e:
            raise Exception(f"Error analyzing bill: {str(e)}")

    def format_bill_summary(self, bill_data: Dict) -> str:
        """Format bill data into a readable summary."""
        lines = []
        lines.append(f"📄 *Bill Analysis*")

        if bill_data.get('restaurant'):
            lines.append(f"Restaurant: {bill_data['restaurant']}")

        lines.append(f"\n*Items:*")
        for i, item in enumerate(bill_data['items'], 1):
            lines.append(f"{i}. {item['name']} - ${item['price']:.2f}")

        lines.append(f"\n*Summary:*")
        lines.append(f"Subtotal: ${bill_data['subtotal']:.2f}")
        lines.append(f"Tax (GST): ${bill_data['tax']:.2f}")
        lines.append(f"Service Charge: ${bill_data['service_charge']:.2f}")
        lines.append(f"*Total: ${bill_data['total']:.2f}*")

        return '\n'.join(lines)
