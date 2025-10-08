# Changelog

All notable changes to MakanSplit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-05

### Added
- Initial release of MakanSplit bot
- Three bill splitting modes:
  - Even split: Divide bill equally among tagged users
  - Manual split: Manually assign items to users
  - Photo AI split: Automatically detect who ate what from group photo
- PayNow QR code generation for Singapore payments
- Dynamic PayNow recipient collection (from bill uploader)
- Persistent storage of user PayNow information
- User tracking in group chats
- Bill analysis using Gemini/OpenRouter AI
- Person-to-food matching using computer vision
- Telegram user pairing with detected people
- Confirmation flow before sending payment requests
- Docker support for containerized deployment
- AWS App Runner deployment script with versioning
- Comprehensive deployment documentation

### Features
- `/makansplit` - Start bill splitting
- `/start` - Welcome message
- `/help` - Show help information
- `/cancel` - Cancel current operation
- Contact sharing for easy PayNow setup
- Manual entry fallback for PayNow info
- Item-by-item assignment with "Select All" option
- Real-time user tracking in groups
- Saved PayNow info with confirmation
- Recipient verification before payment

### Technical
- Python 3.11+ with python-telegram-bot
- Gemini AI and OpenRouter API support
- PayNowQR library for EMVCo-compliant QR codes
- Docker with uv package manager
- AWS ECR and App Runner deployment
- Automated deployment with version tagging
- JSON-based persistent storage

## [Unreleased]

### Planned
- Multiple currency support
- Receipt OCR improvements
- Group expense tracking
- Split bill history
- Export to CSV/PDF
- Multi-language support
