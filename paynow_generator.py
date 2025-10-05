import qrcode
from io import BytesIO
from typing import Optional
from config import PAYNOW_RECIPIENT_PHONE, PAYNOW_RECIPIENT_NAME


class PayNowGenerator:
    """Generate PayNow QR codes for Singapore payments."""

    def __init__(
        self, recipient_phone: Optional[str] = None, recipient_name: Optional[str] = None
    ):
        self.recipient_phone = recipient_phone or PAYNOW_RECIPIENT_PHONE
        self.recipient_name = recipient_name or PAYNOW_RECIPIENT_NAME

    def generate_paynow_string(
        self, amount: float, reference: str = ""
    ) -> str:
        """
        Generate PayNow QR code string following Singapore's PayNow format.

        PayNow QR format (EMV QR Code):
        - Payload Format Indicator: "00" + "02" + "01"
        - Point of Initiation: "01" + "02" + "12" (static QR)
        - Merchant Account: "26" + length + PayNow data
        - Transaction Currency: "53" + "03" + "702" (SGD)
        - Transaction Amount: "54" + length + amount
        - Country Code: "58" + "02" + "SG"
        - Merchant Name: "59" + length + name
        - Additional Data: "62" + length + reference data
        - CRC: "63" + "04" + checksum
        """

        def format_field(tag: str, value: str) -> str:
            """Format a field with tag-length-value."""
            length = str(len(value)).zfill(2)
            return f"{tag}{length}{value}"

        # Build PayNow merchant data (tag 26)
        paynow_data = ""
        paynow_data += format_field("00", "SG.PAYNOW")  # PayNow identifier
        paynow_data += format_field("01", "2")  # Proxy type: 2 = mobile number
        paynow_data += format_field(
            "02", self.recipient_phone.replace("+", "").replace(" ", "")
        )  # Mobile number
        paynow_data += format_field("03", "1")  # Editable: 1 = amount is editable

        # Build main payload
        payload = ""
        payload += format_field("00", "01")  # Payload format indicator
        payload += format_field("01", "12")  # Point of initiation (static)
        payload += format_field("26", paynow_data)  # Merchant account info
        payload += format_field("52", "0000")  # Merchant category code
        payload += format_field("53", "702")  # Currency: 702 = SGD
        payload += format_field("54", f"{amount:.2f}")  # Transaction amount
        payload += format_field("58", "SG")  # Country code
        payload += format_field("59", self.recipient_name[:25])  # Merchant name (max 25 chars)

        # Additional data (reference)
        if reference:
            additional_data = format_field("01", reference[:25])  # Reference (max 25 chars)
            payload += format_field("62", additional_data)

        # Calculate CRC16-CCITT checksum
        payload += "6304"  # CRC tag and length
        crc = self._calculate_crc16(payload)
        payload += crc

        return payload

    def _calculate_crc16(self, data: str) -> str:
        """Calculate CRC16-CCITT checksum for PayNow QR."""
        crc = 0xFFFF
        polynomial = 0x1021

        for byte in data.encode('utf-8'):
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ polynomial
                else:
                    crc <<= 1
                crc &= 0xFFFF

        return f"{crc:04X}"

    def generate_qr_code(
        self, amount: float, reference: str = "", person_name: str = ""
    ) -> BytesIO:
        """
        Generate a PayNow QR code image.

        Args:
            amount: Amount to request
            reference: Reference text for the transaction
            person_name: Name of the person (for reference text)

        Returns:
            BytesIO object containing the QR code image
        """
        if person_name and reference:
            full_reference = f"{reference} - {person_name}"
        elif person_name:
            full_reference = person_name
        else:
            full_reference = reference

        paynow_string = self.generate_paynow_string(amount, full_reference)

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(paynow_string)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Save to BytesIO
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)

        return bio

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
        lines.append(f"\nPlease scan the QR code below to pay via PayNow:")

        return '\n'.join(lines)
