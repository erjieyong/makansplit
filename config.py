import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Gemini API Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# PayNow Configuration
PAYNOW_RECIPIENT_PHONE = os.getenv('PAYNOW_RECIPIENT_PHONE')
PAYNOW_RECIPIENT_NAME = os.getenv('PAYNOW_RECIPIENT_NAME')

# Bot States
(
    WAITING_BILL_PHOTO,
    WAITING_GROUP_PHOTO,
    ANALYZING,
    MATCHING_USERS,
    CONFIRMING,
    CORRECTING,
    FINALIZING,
) = range(7)

# Temp directory for photos
TEMP_DIR = 'temp_photos'
os.makedirs(TEMP_DIR, exist_ok=True)
