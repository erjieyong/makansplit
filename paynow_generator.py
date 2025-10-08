from paynow import PayNowQR
from io import BytesIO
from typing import Optional
import os
import tempfile


class PayNowGenerator:
    """Generate PayNow QR codes for Singapore payments using PayNowQR library."""

    def __init__(
        self, recipient_phone: str, recipient_name: str
    ):
        self.recipient_phone = recipient_phone
        self.recipient_name = recipient_name

    def generate_qr_code(
        self, amount: float, reference: str = "", person_name: str = ""
    ) -> BytesIO:
        """
        Generate a PayNow QR code image using the PayNowQR library.

        Args:
            amount: Amount to request
            reference: Reference text for the transaction
            person_name: Name of the person (for reference text)

        Returns:
            BytesIO object containing the QR code image
        """
        # Build reference string
        if person_name and reference:
            full_reference = f"{reference} - {person_name}"
        elif person_name:
            full_reference = person_name
        else:
            full_reference = reference

        # Limit reference to 25 characters
        full_reference = full_reference[:25] if full_reference else "Bill Split"

        # Create PayNowQR object
        # PayNowQR(recipient_type, recipient_id, recipient_name, amount, reference, expiry_date, brand_colour)
        qr = PayNowQR(
            "MOBILE",  # Type must be uppercase
            self.recipient_phone,
            self.recipient_name,
            amount,
            full_reference
        )

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_path = tmp_file.name

        try:
            # Generate and save QR code
            qr.save(tmp_path)

            # Read the file into BytesIO
            with open(tmp_path, 'rb') as f:
                bio = BytesIO(f.read())
            bio.seek(0)

            return bio
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def format_payment_message(
        self, amount: float, items: list, restaurant: str = ""
    ) -> str:
        """Format a payment request message."""
        lines = []
        lines.append("💰 *Your Bill Split*\n")

        if restaurant:
            lines.append(f"📍 {restaurant}\n")

        lines.append("*Your items:*")
        for item in items:
            if 'share_ratio' in item and item['share_ratio'] < 1.0:
                lines.append(
                    f"• {item['name']} ({item['share_ratio']:.0%} share) - ${item['total_price'] * item['share_ratio']:.2f}"
                )
            else:
                lines.append(f"• {item['name']} - ${item['total_price']:.2f}")

        lines.append(f"\n*Total Amount: ${amount:.2f}*")
        lines.append(f"\n*Pay to:*")
        lines.append(f"📱 {self.recipient_phone}")
        lines.append(f"👤 {self.recipient_name}")
        lines.append(f"\nPlease scan the QR code below to pay via PayNow:")

        return '\n'.join(lines)
