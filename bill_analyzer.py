import google.generativeai as genai
from PIL import Image
import json
from typing import Dict, List
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)


class BillAnalyzer:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.5-flash-lite-preview-09-2025')

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
            image = Image.open(image_path)

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

            response = self.model.generate_content([prompt, image])

            # Extract JSON from response
            response_text = response.text.strip()

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
