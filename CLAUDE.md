# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MakanSplit is a Telegram bot that intelligently splits restaurant bills by analyzing photos. It offers three splitting modes:
1. **Even Split** - Equal division among selected participants
2. **Manual Split** - Item-by-item assignment with multi-person sharing
3. **Photo AI Split** - Automatic detection via group photo analysis

## Common Commands

### Development
```bash
# Setup environment
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -r requirements.txt

# Run bot locally
python bot.py

# Run with Docker
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### Deployment
```bash
# Build Docker image
docker build -t bill-splitter-bot .

# Push to AWS ECR
aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com
docker tag bill-splitter-bot:latest ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/bill-splitter-bot:latest
docker push ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/bill-splitter-bot:latest
```

## Architecture

### Conversation Flow State Machine

The bot uses python-telegram-bot's ConversationHandler with these states (defined in `config.py`):

```
WAITING_BILL_PHOTO → [Bill uploaded]
    ↓
CHOOSING_SPLIT_MODE → [User selects mode]
    ↓
    ├─→ TAGGING_USERS (Even split: tag participants)
    ├─→ MANUAL_ASSIGNMENT (Manual: assign items one by one)
    └─→ WAITING_GROUP_PHOTO (Photo AI: upload group photo)
         ↓
         ANALYZING → MATCHING_USERS
    ↓
CONFIRMING → [User confirms]
    ↓
FINALIZING (Send PayNow QR codes)
```

### Component Interactions

**bot.py** - Main conversation orchestrator
- Manages state transitions via ConversationHandler
- Coordinates between analyzer, matcher, and payment components
- Tracks users via `context.bot_data['known_members']` (persists users who interact in group)

**bill_analyzer.py** - Bill OCR and parsing
- Supports dual AI providers (Gemini or OpenRouter)
- Provider selection: If `OPENROUTER_API_KEY` is set → uses OpenRouter, else → Gemini
- Returns structured JSON: items, subtotal, tax, service_charge, total
- Calculates proportional tax/service per item

**person_matcher.py** - Group photo analysis
- Also supports dual AI providers (same logic as bill_analyzer)
- Matches people to food items in group photos
- Returns person_id, position, items[], share_ratio{} for split items

**paynow_generator.py** - PayNow QR code generation
- Uses official PayNowQR library from https://github.com/ekqiutech/PayNowQR
- Requires `paynow-logo.png` in project root
- Generates EMVCo-compliant QR codes for Singapore PayNow

**user_matcher.py** - Telegram user identification
- Matches AI-detected people to Telegram users
- Stores pairings persistently in `user_pairings.json`

## Key Design Patterns

### User Tracking System
The bot tracks all group members who send messages via a message handler in `bot.py`:
- Stored in `context.bot_data['known_members'][chat_id][user_id]`
- Automatically includes admins + anyone who sends a message
- Used for user selection in Even and Manual split modes
- Tip shown to users: "Ask people to send any message in chat to be added"

### AI Provider Abstraction
Both `bill_analyzer.py` and `person_matcher.py` implement dual provider support:
- `self.use_openrouter = bool(OPENROUTER_API_KEY)`
- `_analyze_with_openrouter()` - Base64 encodes image, calls OpenRouter API
- `_analyze_with_gemini()` - Uses google.generativeai SDK
- Both return text response, JSON parsing is shared

### Split Mode Implementation
Three independent flows that converge at CONFIRMING state:

**Even Split:**
- `start_user_tagging()` - Display user selection with checkmarks
- `handle_user_tagging()` - Toggle users, show "Done" when ready
- Calculate: `total / len(tagged_users)`
- Store in `context.user_data['totals']` as {user_id: amount}

**Manual Split:**
- `start_manual_assignment()` - Show item with user selection
- "Select All" button added for convenience
- `handle_manual_assignment()` - Assign users per item, track in `manual_assignments[item_index] = [user_ids]`
- Calculate shares: If item has N assignees, each pays `item_price / N`

**Photo AI Split:**
- Original flow: group photo → AI analysis → person matching → user confirmation
- Most complex flow due to people-to-telegram-user mapping

## Environment Variables

Required:
- `TELEGRAM_BOT_TOKEN` - From @BotFather
- `PAYNOW_RECIPIENT_PHONE` - Format: +6512345678
- `PAYNOW_RECIPIENT_NAME` - Recipient name for PayNow

AI Provider (choose one):
- `GEMINI_API_KEY` - Google Gemini API
- `OPENROUTER_API_KEY` + `OPENROUTER_MODEL` - OpenRouter API
  - If both set, OpenRouter is preferred
  - Example model: `google/gemini-2.5-flash-lite-preview-09-2025`

## Important Files Not in Git

- `.env` - Contains sensitive credentials (see .env.example)
- `temp_photos/` - Temporary storage for bill/group photos
- `user_pairings.json` - Persistent person-to-telegram-user mappings
- `.venv/` - Python virtual environment

## Docker Deployment Notes

- Uses `uv` for fast Python package installation
- Requires `paynow-logo.png` to be COPY'd into container
- Creates `temp_photos/` directory at runtime
- Environment variables passed via docker-compose `.env` file
- No load balancer needed (bot uses long polling)
- Recommended: 512 CPU, 1GB RAM (AWS Fargate or ECS)

## Bot Behavior Notes

1. **User Selection**: Only shows admins + users who have sent messages in the group (Telegram API limitation)
2. **PayNow QR Codes**: Must scan with Singapore banking app (DBS, OCBC, UOB, etc.)
3. **State Persistence**: Uses `context.user_data` (per-user) and `context.bot_data` (global)
4. **Error Handling**: Bill/photo analysis failures return to start with error message
5. **Restart**: `/start` command clears user_data and restarts from beginning
