# Bill Splitter Telegram Bot

A Telegram bot that intelligently splits restaurant bills by analyzing photos of the bill and the dining group, matching people to their food using AI vision.

## Features

- 📸 **Bill OCR**: Extract itemized prices from bill photos
- 👥 **Person-Food Matching**: Analyze group photos to determine who ate what
- 🤖 **Facial Recognition**: Match people in photos to Telegram profiles
- 💰 **Smart Splitting**: Handle shared items and proportional tax/service charges
- 📱 **PayNow Integration**: Generate Singapore PayNow QR codes for easy payment

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) - Fast Python package installer
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Google Gemini API Key (from [Google AI Studio](https://makersuite.google.com/app/apikey))
- PayNow-enabled phone number (Singapore)

### Local Installation

1. **Install uv** (if not already installed)
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # or on macOS: brew install uv
   ```

2. **Clone the repository**
   ```bash
   cd /path/to/makansplit
   ```

3. **Create virtual environment and install dependencies**
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your credentials:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   GEMINI_API_KEY=your_gemini_key
   PAYNOW_RECIPIENT_PHONE=+6512345678
   PAYNOW_RECIPIENT_NAME=Your Name
   ```

5. **Run the bot**
   ```bash
   uv run bot.py
   # or: python bot.py
   ```

### Docker Installation

1. **Build and run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

2. **View logs**
   ```bash
   docker-compose logs -f
   ```

3. **Stop the bot**
   ```bash
   docker-compose down
   ```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to begin
3. Send a clear photo of the bill
4. Send a group photo showing everyone with their food
5. Review the AI's analysis and confirm
6. Everyone receives a PayNow QR code with their amount

### Tips for Best Results

**Bill Photo:**
- Ensure good lighting
- All items and prices should be readable
- Avoid glare and shadows
- Keep the camera steady

**Group Photo:**
- Everyone's face should be visible
- Food items should be clearly shown
- Good lighting is essential
- Avoid blur or motion

## AWS Deployment

### Option 1: AWS ECS/Fargate

1. **Build and push Docker image to ECR**
   ```bash
   aws ecr create-repository --repository-name bill-splitter-bot

   aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com

   docker build -t bill-splitter-bot .
   docker tag bill-splitter-bot:latest YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/bill-splitter-bot:latest
   docker push YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/bill-splitter-bot:latest
   ```

2. **Create ECS Task Definition**
   - Use the image from ECR
   - Set environment variables (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, etc.)
   - Allocate 512 CPU units and 1GB memory

3. **Create ECS Service**
   - Use Fargate launch type
   - 1 task (can scale if needed)
   - No load balancer needed (bot uses long polling)

### Option 2: AWS EC2

1. **Launch EC2 instance**
   - Ubuntu 22.04 LTS
   - t3.small or larger
   - Security group: Allow outbound HTTPS

2. **Install Docker on EC2**
   ```bash
   sudo apt update
   sudo apt install docker.io docker-compose -y
   sudo systemctl enable docker
   sudo systemctl start docker
   ```

3. **Deploy the bot**
   ```bash
   scp -r . ubuntu@your-ec2-ip:/home/ubuntu/bill-splitter
   ssh ubuntu@your-ec2-ip
   cd bill-splitter
   nano .env  # Add your credentials
   sudo docker-compose up -d
   ```

4. **Set up auto-restart**
   ```bash
   sudo docker update --restart unless-stopped bill-splitter-bot
   ```

### Environment Variables for Production

Make sure to set these in your AWS environment:

```bash
TELEGRAM_BOT_TOKEN=your_production_token
GEMINI_API_KEY=your_production_key
PAYNOW_RECIPIENT_PHONE=+6512345678
PAYNOW_RECIPIENT_NAME=Your Business Name
```

## Architecture

```
┌─────────────┐
│  Telegram   │
│   Users     │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         Telegram Bot API            │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│          bot.py                     │
│  (Conversation Handler & States)    │
└──────┬──────────────┬───────────────┘
       │              │
       ▼              ▼
┌─────────────┐  ┌──────────────────┐
│bill_analyzer│  │ person_matcher   │
│  (Gemini)   │  │   (Gemini)       │
└─────────────┘  └──────────────────┘
       │              │
       └──────┬───────┘
              ▼
       ┌──────────────┐
       │paynow_generator│
       └──────────────┘
```

## Project Structure

```
makansplit/
├── bot.py                 # Main bot logic
├── bill_analyzer.py       # Bill OCR and extraction
├── person_matcher.py      # Person-food matching & facial recognition
├── paynow_generator.py    # PayNow QR code generation
├── config.py              # Configuration and constants
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker container definition
├── docker-compose.yml     # Docker Compose configuration
├── .env.example           # Example environment variables
├── .gitignore            # Git ignore rules
└── temp_photos/          # Temporary photo storage
```

## Troubleshooting

### Bot doesn't respond
- Check if bot is running: `docker-compose ps`
- View logs: `docker-compose logs -f`
- Verify token is correct in `.env`

### Bill analysis fails
- Ensure bill photo is clear and well-lit
- Check Gemini API key is valid
- Try a different angle or better lighting

### Person matching is inaccurate
- Take a clearer group photo
- Ensure food items are visible
- Make sure faces are clear
- Good lighting helps significantly

### PayNow QR codes don't work
- Verify phone number format: +6512345678
- Ensure recipient phone has PayNow enabled
- Check if amount is valid (> 0)

## Limitations

- Currently only supports Singapore PayNow
- Requires good quality photos for accurate analysis
- Facial recognition works best with clear, front-facing photos
- May struggle with very complex bills or unusual layouts

## Future Enhancements

- Support for other payment methods (PayLah, GrabPay, etc.)
- Multi-currency support
- Better manual correction interface
- Split history and analytics
- Support for multiple payers (when someone pays for others)

## License

MIT License - feel free to use and modify for your needs.

## Support

For issues or questions:
1. Check the logs: `docker-compose logs -f`
2. Ensure all environment variables are set correctly
3. Verify API keys are valid and have proper permissions
4. Test with clear, well-lit photos

## Credits

- Built with [python-telegram-bot](https://python-telegram-bot.org/)
- AI vision powered by [Google Gemini](https://deepmind.google/technologies/gemini/)
- PayNow QR codes follow Singapore's EMV QR standard
