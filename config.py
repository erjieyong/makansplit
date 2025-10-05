import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# AI Provider Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'google/gemini-flash-1.5-8b')

# PayNow Configuration
PAYNOW_RECIPIENT_PHONE = os.getenv('PAYNOW_RECIPIENT_PHONE')
PAYNOW_RECIPIENT_NAME = os.getenv('PAYNOW_RECIPIENT_NAME')

# Bot States
(
    WAITING_BILL_PHOTO,
    CHOOSING_SPLIT_MODE,
    TAGGING_USERS,
    MANUAL_ASSIGNMENT,
    WAITING_GROUP_PHOTO,
    ANALYZING,
    MATCHING_USERS,
    CONFIRMING,
    CORRECTING,
    FINALIZING,
) = range(10)

# Temp directory for photos
TEMP_DIR = 'temp_photos'
os.makedirs(TEMP_DIR, exist_ok=True)
