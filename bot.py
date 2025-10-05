import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from config import (
    TELEGRAM_BOT_TOKEN,
    WAITING_BILL_PHOTO,
    WAITING_GROUP_PHOTO,
    ANALYZING,
    MATCHING_USERS,
    CONFIRMING,
    CORRECTING,
    FINALIZING,
    TEMP_DIR,
)
from bill_analyzer import BillAnalyzer
from person_matcher import PersonMatcher
from paynow_generator import PayNowGenerator
from user_matcher import UserMatcher

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class BillSplitterBot:
    def __init__(self):
        self.bill_analyzer = BillAnalyzer()
        self.person_matcher = PersonMatcher()
        self.paynow_generator = PayNowGenerator()
        self.user_matcher = UserMatcher()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the conversation and ask for bill photo."""
        user = update.effective_user

        # Check if user is restarting mid-flow
        if context.user_data:
            await update.message.reply_text(
                "🔄 Restarting from the beginning...\n"
                "Previous session data cleared."
            )

        await update.message.reply_text(
            f"Hi {user.mention_html()}! 👋\n\n"
            "I'll help you split the bill fairly among your group.\n\n"
            "*Here's how it works:*\n"
            "1️⃣ Send me a photo of the bill\n"
            "2️⃣ Send me a group photo of everyone with their food\n"
            "3️⃣ I'll analyze and match people to their items\n"
            "4️⃣ Confirm the split and I'll send PayNow QR codes\n\n"
            "Let's start! Please send me a *clear photo of the bill* 📄",
            parse_mode='Markdown'
        )

        # Initialize session data (clear any existing data)
        context.user_data.clear()
        context.user_data['chat_id'] = update.effective_chat.id

        return WAITING_BILL_PHOTO

    async def receive_bill_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive and process the bill photo."""
        await update.message.reply_text("📸 Got the bill! Analyzing... ⏳")

        # Download photo
        photo = update.message.photo[-1]  # Get highest resolution
        file = await context.bot.get_file(photo.file_id)

        bill_photo_path = os.path.join(TEMP_DIR, f"bill_{update.effective_chat.id}.jpg")
        await file.download_to_drive(bill_photo_path)

        try:
            # Analyze bill
            bill_data = self.bill_analyzer.analyze_bill(bill_photo_path)
            context.user_data['bill_data'] = bill_data
            context.user_data['bill_photo_path'] = bill_photo_path

            # Send summary
            summary = self.bill_analyzer.format_bill_summary(bill_data)
            await update.message.reply_text(summary, parse_mode='Markdown')

            await update.message.reply_text(
                "\nGreat! Now please send me a *photo of everyone at the table with their food* 📸\n\n"
                "Make sure:\n"
                "✓ Everyone's face is visible\n"
                "✓ Food items are clearly visible\n"
                "✓ Good lighting",
                parse_mode='Markdown'
            )

            return WAITING_GROUP_PHOTO

        except Exception as e:
            logger.error(f"Error analyzing bill: {e}")
            await update.message.reply_text(
                "❌ Sorry, I couldn't analyze the bill properly. "
                "Please send a clearer photo of the bill.\n\n"
                "Make sure:\n"
                "✓ All items and prices are visible\n"
                "✓ Good lighting and focus\n"
                "✓ No glare or shadows"
            )
            return WAITING_BILL_PHOTO

    async def receive_group_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receive and process the group photo."""
        await update.message.reply_text(
            "📸 Got the group photo! Analyzing who ate what... 🔍\n"
            "This may take a moment..."
        )

        # Download photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        group_photo_path = os.path.join(TEMP_DIR, f"group_{update.effective_chat.id}.jpg")
        await file.download_to_drive(group_photo_path)

        try:
            bill_data = context.user_data['bill_data']

            # Analyze group photo
            people_data = await self.person_matcher.analyze_group_photo(
                group_photo_path, bill_data['items']
            )
            context.user_data['people_data'] = people_data
            context.user_data['group_photo_path'] = group_photo_path

            # Extract headshots for each person
            await update.message.reply_text(
                "📸 Extracting individual photos... This may take a moment..."
            )

            headshots = await self.user_matcher.extract_person_headshots(
                group_photo_path, people_data
            )
            context.user_data['headshots'] = headshots

            # Get chat members for matching
            chat_members = []
            try:
                # Get all chat administrators and members
                chat_admins = await context.bot.get_chat_administrators(update.effective_chat.id)

                for admin in chat_admins:
                    user = admin.user
                    if not user.is_bot:
                        chat_members.append({
                            'id': user.id,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'username': user.username,
                            'mention': user.mention_html()
                        })
                        logger.info(f"Found chat member: {user.first_name} (ID: {user.id})")

            except Exception as e:
                logger.warning(f"Could not get chat members: {e}")
                # If we can't get chat members, we'll still proceed with manual input

            context.user_data['chat_members'] = chat_members

            # Load saved pairings for this chat
            saved_pairings = self.user_matcher.load_pairings(update.effective_chat.id)
            logger.info(f"Loaded {len(saved_pairings)} saved pairings for chat {update.effective_chat.id}")

            # Try to auto-match based on saved pairings
            matches = {}
            unmatched_people = []

            for person in people_data['people']:
                person_id = person['person_id']
                person_key = self.user_matcher.generate_person_key(person)

                if person_key in saved_pairings:
                    telegram_user_id = saved_pairings[person_key].get('telegram_user_id')
                    matches[person_id] = telegram_user_id
                    logger.info(f"Auto-matched Person {person_id} to user {telegram_user_id} using saved pairing")

                    # Show saved headshot if available for confirmation
                    saved_headshot = self.user_matcher.get_saved_headshot(person, saved_pairings)
                    if saved_headshot:
                        logger.info(f"Found saved headshot for Person {person_id}: {saved_headshot}")
                else:
                    unmatched_people.append(person)

            context.user_data['matches'] = matches
            context.user_data['unmatched_people'] = unmatched_people
            context.user_data['current_matching_index'] = 0

            if unmatched_people:
                # Start manual matching for unmatched people
                logger.info(f"{len(unmatched_people)} people need manual matching")
                return await self.start_person_matching(update, context)
            else:
                # All people were auto-matched
                await update.message.reply_text(
                    f"✅ Auto-matched all {len(people_data['people'])} people based on saved pairings!"
                )
                # Continue to confirmation
                return await self.show_confirmation(update, context)


        except Exception as e:
            logger.error(f"Error analyzing group photo: {e}")
            await update.message.reply_text(
                "❌ Sorry, I couldn't analyze the group photo properly. "
                "Please send a clearer photo.\n\n"
                "Make sure:\n"
                "✓ Everyone's face is visible\n"
                "✓ Food items are clearly visible\n"
                "✓ Good lighting and no blur"
            )
            return WAITING_GROUP_PHOTO

    async def start_person_matching(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Start the manual person matching process."""
        unmatched_people = context.user_data['unmatched_people']
        current_index = context.user_data['current_matching_index']

        if current_index >= len(unmatched_people):
            # All people matched, move to confirmation
            return await self.show_confirmation(update, context)

        person = unmatched_people[current_index]
        person_id = person['person_id']

        # Send headshot if available
        headshots = context.user_data.get('headshots', {})
        if person_id in headshots:
            with open(headshots[person_id], 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo,
                    caption=f"*Person {person_id}*\nPosition: {person['position']}"
                )

        # Build keyboard with chat members
        chat_members = context.user_data.get('chat_members', [])
        keyboard = []

        for member in chat_members:
            display_name = member['first_name']
            if member['username']:
                display_name += f" (@{member['username']})"

            keyboard.append([
                InlineKeyboardButton(
                    display_name,
                    callback_data=f"match_{person_id}_{member['id']}"
                )
            ])

        # Add manual input and skip buttons
        keyboard.append([
            InlineKeyboardButton("✍️ Enter username/phone", callback_data=f"manual_{person_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("⏭ Skip this person", callback_data=f"skip_{person_id}")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"👤 *Who is Person {person_id}?*\n\n"
        message_text += f"Position: {person['position']}\n\n"

        if chat_members:
            message_text += "Select from the list below, or choose 'Enter username/phone' to input manually:"
        else:
            message_text += "Choose 'Enter username/phone' to enter their Telegram username or phone number:"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return MATCHING_USERS

    async def handle_person_match(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle the user's selection for person matching."""
        query = update.callback_query
        await query.answer()

        data = query.data

        if data.startswith('match_'):
            # Parse: match_personId_telegramUserId
            parts = data.split('_')
            person_id = int(parts[1])
            telegram_user_id = int(parts[2])

            # Find the person
            unmatched_people = context.user_data['unmatched_people']
            current_index = context.user_data['current_matching_index']
            person = unmatched_people[current_index]

            # Save the match
            context.user_data['matches'][person_id] = telegram_user_id

            # Save to persistent storage with headshot
            person_key = self.user_matcher.generate_person_key(person)
            headshots = context.user_data.get('headshots', {})
            headshot_path = headshots.get(person_id)

            self.user_matcher.save_pairing(
                update.effective_chat.id, person_key, telegram_user_id, headshot_path
            )

            # Get user name for confirmation
            chat_members = context.user_data.get('chat_members', [])
            user_name = "Unknown"
            for member in chat_members:
                if member['id'] == telegram_user_id:
                    user_name = member['first_name']
                    break

            await query.edit_message_text(
                f"✅ Person {person_id} matched to {user_name}!"
            )

            logger.info(f"Matched Person {person_id} to Telegram user {telegram_user_id}")

            # Move to next person
            context.user_data['current_matching_index'] += 1
            return await self.start_person_matching(update, context)

        elif data.startswith('manual_'):
            # Parse: manual_personId
            person_id = int(data.split('_')[1])
            context.user_data['awaiting_manual_input'] = person_id

            await query.edit_message_text(
                f"✍️ *Manual Input for Person {person_id}*\n\n"
                "Please type their Telegram username (with or without @) or phone number with country code:\n\n"
                "Examples:\n"
                "• @johndoe\n"
                "• johndoe\n"
                "• +6591234567",
                parse_mode='Markdown'
            )

            return MATCHING_USERS

        elif data.startswith('skip_'):
            # Parse: skip_personId
            person_id = int(data.split('_')[1])
            await query.edit_message_text(
                f"⏭ Skipped Person {person_id}"
            )
            logger.info(f"Skipped matching for Person {person_id}")

            # Move to next person
            context.user_data['current_matching_index'] += 1
            return await self.start_person_matching(update, context)

    async def handle_manual_input(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle manual username/phone input for person matching."""
        if 'awaiting_manual_input' not in context.user_data:
            return MATCHING_USERS

        person_id = context.user_data['awaiting_manual_input']
        user_input = update.message.text.strip()

        # Remove @ if present
        if user_input.startswith('@'):
            user_input = user_input[1:]

        # Find the person
        unmatched_people = context.user_data['unmatched_people']
        current_index = context.user_data['current_matching_index']
        person = unmatched_people[current_index]

        # Try to find the user
        telegram_user_id = None
        user_name = user_input

        # First, try to match with known chat members by username
        chat_members = context.user_data.get('chat_members', [])
        for member in chat_members:
            if member['username'] and member['username'].lower() == user_input.lower():
                telegram_user_id = member['id']
                user_name = member['first_name']
                break

        if not telegram_user_id:
            # Ask user to tag the person or provide more info
            await update.message.reply_text(
                f"⚠️ I couldn't find a user with username/phone '{user_input}' in this chat.\n\n"
                f"Please ask **Person {person_id}** to:\n"
                f"1. Send any message in this chat, OR\n"
                f"2. Start a private chat with me by clicking @{(await context.bot.get_me()).username}\n\n"
                "Then send /start again to restart the matching process.\n\n"
                "For now, I'll skip this person."
            )

            # Skip this person
            logger.warning(f"Could not match Person {person_id} to username/phone: {user_input}")
            context.user_data['current_matching_index'] += 1
            del context.user_data['awaiting_manual_input']
            return await self.start_person_matching(update, context)

        # Save the match
        context.user_data['matches'][person_id] = telegram_user_id

        # Save to persistent storage with headshot
        person_key = self.user_matcher.generate_person_key(person)
        headshots = context.user_data.get('headshots', {})
        headshot_path = headshots.get(person_id)

        self.user_matcher.save_pairing(
            update.effective_chat.id, person_key, telegram_user_id, headshot_path
        )

        await update.message.reply_text(
            f"✅ Person {person_id} matched to {user_name}!"
        )

        logger.info(f"Manually matched Person {person_id} to Telegram user {telegram_user_id}")

        # Move to next person
        context.user_data['current_matching_index'] += 1
        del context.user_data['awaiting_manual_input']

        return await self.start_person_matching(update, context)

    async def show_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Show the final analysis summary and ask for confirmation."""
        bill_data = context.user_data['bill_data']
        people_data = context.user_data['people_data']
        matches = context.user_data['matches']

        # Calculate totals
        totals = self.person_matcher.calculate_person_totals(
            people_data, bill_data['items']
        )
        context.user_data['totals'] = totals

        # Format summary with matches
        summary = self.person_matcher.format_analysis_summary(
            people_data, bill_data['items'], totals, matches
        )

        # Add user names to summary
        chat_members = context.user_data.get('chat_members', [])
        user_info = {}
        for member in chat_members:
            user_info[member['id']] = member

        context.user_data['user_info'] = user_info

        # Send summary
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=summary,
            parse_mode='Markdown'
        )

        # If we have matches, show them
        if matches:
            match_text = "\n👥 *Matched Users:*\n"
            for person_id, telegram_user_id in matches.items():
                if telegram_user_id in user_info:
                    user_name = user_info[telegram_user_id]['first_name']
                    match_text += f"Person {person_id} → {user_name}\n"

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=match_text,
                parse_mode='Markdown'
            )

        # Check confidence
        if people_data.get('overall_confidence', 0) < 0.7:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ Note: I'm not very confident about some food matches. "
                     "Please review carefully!"
            )

        # Ask for confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Looks good!", callback_data="confirm_yes"),
                InlineKeyboardButton("✏️ Make changes", callback_data="confirm_edit"),
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="confirm_cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="\n*Does this look correct?*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return CONFIRMING

    async def handle_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle user confirmation of the analysis."""
        query = update.callback_query
        await query.answer()

        if query.data == "confirm_yes":
            await query.edit_message_text(
                "✅ Great! Preparing PayNow QR codes...\n\n"
                "I'll now send payment requests to each person."
            )
            return await self.send_payment_requests(update, context)

        elif query.data == "confirm_edit":
            await query.edit_message_text(
                "✏️ *Editing mode*\n\n"
                "Please describe what changes need to be made.\n"
                "For example:\n"
                "• 'Person 1 should not have item 3'\n"
                "• 'Person 2 and Person 3 should split item 5'\n"
                "• 'Add item 2 to Person 1'",
                parse_mode='Markdown'
            )
            return CORRECTING

        elif query.data == "confirm_cancel":
            await query.edit_message_text(
                "❌ Cancelled. Send /start to begin again."
            )
            return ConversationHandler.END

    async def handle_corrections(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle user corrections to the analysis."""
        correction_text = update.message.text

        await update.message.reply_text(
            "🤔 I understand you want to make changes. "
            "However, manual correction is complex.\n\n"
            "For now, please send /start to restart with new photos, "
            "or use the buttons below to proceed:",
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Proceed anyway", callback_data="confirm_yes"),
                InlineKeyboardButton("🔄 Restart", callback_data="restart"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "What would you like to do?",
            reply_markup=reply_markup
        )

        return CONFIRMING

    async def send_payment_requests(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Send PayNow QR codes to each person."""
        try:
            bill_data = context.user_data['bill_data']
            people_data = context.user_data['people_data']
            totals = context.user_data['totals']
            matches = context.user_data.get('matches', {})
            user_info = context.user_data.get('user_info', {})

            restaurant = bill_data.get('restaurant', 'Restaurant')

            # For each person, prepare their items
            for person in people_data['people']:
                person_id = person['person_id']
                amount = totals[person_id]

                # Get their items
                person_items = []
                for item_index in person['items']:
                    item = bill_data['items'][item_index - 1].copy()
                    share_ratio = person.get('share_ratio', {}).get(str(item_index), 1.0)
                    item['share_ratio'] = share_ratio
                    person_items.append(item)

                # Generate message
                message = self.paynow_generator.format_payment_message(
                    amount, person_items, restaurant
                )

                # Generate QR code
                reference = f"{restaurant[:15]} split"
                qr_code = self.paynow_generator.generate_qr_code(
                    amount, reference, f"Person {person_id}"
                )

                # Check if this person was matched to a Telegram user
                telegram_user_id = matches.get(person_id)

                if telegram_user_id:
                    # Send direct message to the matched user
                    try:
                        user_name = user_info.get(telegram_user_id, {}).get('first_name', 'there')
                        await context.bot.send_message(
                            chat_id=telegram_user_id,
                            text=f"Hi {user_name}! 👋\n\n" + message,
                            parse_mode='Markdown'
                        )

                        await context.bot.send_photo(
                            chat_id=telegram_user_id,
                            photo=qr_code,
                            caption=f"PayNow QR Code - ${amount:.2f}"
                        )

                        # Notify group that DM was sent
                        await context.bot.send_message(
                            chat_id=context.user_data['chat_id'],
                            text=f"✅ Payment request sent to {user_name} (Person {person_id}) via DM"
                        )
                        logger.info(f"Sent payment request to user {telegram_user_id} (Person {person_id})")
                    except Exception as e:
                        logger.error(f"Failed to send DM to user {telegram_user_id}: {e}")
                        # Fallback to group message
                        await context.bot.send_message(
                            chat_id=context.user_data['chat_id'],
                            text=f"*Person {person_id}* ({person['position']})\n" + message,
                            parse_mode='Markdown'
                        )

                        await context.bot.send_photo(
                            chat_id=context.user_data['chat_id'],
                            photo=qr_code,
                            caption=f"PayNow QR Code for Person {person_id} - ${amount:.2f}"
                        )
                else:
                    # No match, send to group
                    await context.bot.send_message(
                        chat_id=context.user_data['chat_id'],
                        text=f"*Person {person_id}* ({person['position']})\n" + message,
                        parse_mode='Markdown'
                    )

                    await context.bot.send_photo(
                        chat_id=context.user_data['chat_id'],
                        photo=qr_code,
                        caption=f"PayNow QR Code for Person {person_id} - ${amount:.2f}"
                    )

            await context.bot.send_message(
                chat_id=context.user_data['chat_id'],
                text="✅ *All done!*\n\n"
                     "Payment requests sent to everyone. "
                     "Please scan your respective QR codes to pay.\n\n"
                     "Use /start to split another bill.",
                parse_mode='Markdown'
            )

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Error sending payment requests: {e}")
            await update.callback_query.message.reply_text(
                "❌ Sorry, there was an error generating payment requests. "
                "Please try again with /start"
            )
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text(
            "❌ Cancelled. Send /start to begin again."
        )
        return ConversationHandler.END

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        await update.message.reply_text(
            "*Bill Splitter Bot* 💰\n\n"
            "I help you split restaurant bills fairly based on who ate what!\n\n"
            "*Commands:*\n"
            "/start - Start splitting a bill\n"
            "/cancel - Cancel current operation\n"
            "/help - Show this help message\n\n"
            "*How it works:*\n"
            "1. Send me a photo of your bill\n"
            "2. Send me a photo of everyone with their food\n"
            "3. I'll analyze and match people to items\n"
            "4. Confirm and receive PayNow QR codes\n\n"
            "*Tips for best results:*\n"
            "• Use clear, well-lit photos\n"
            "• Make sure all text on bill is readable\n"
            "• Ensure everyone's face is visible in group photo\n"
            "• Show food items clearly",
            parse_mode='Markdown'
        )


def main():
    """Start the bot."""
    # Create bot instance
    bot = BillSplitterBot()

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start)],
        states={
            WAITING_BILL_PHOTO: [
                CommandHandler('start', bot.start),
                MessageHandler(filters.PHOTO, bot.receive_bill_photo)
            ],
            WAITING_GROUP_PHOTO: [
                CommandHandler('start', bot.start),
                MessageHandler(filters.PHOTO, bot.receive_group_photo)
            ],
            MATCHING_USERS: [
                CommandHandler('start', bot.start),
                CallbackQueryHandler(bot.handle_person_match),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_manual_input)
            ],
            CONFIRMING: [
                CommandHandler('start', bot.start),
                CallbackQueryHandler(bot.handle_confirmation)
            ],
            CORRECTING: [
                CommandHandler('start', bot.start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_corrections),
                CallbackQueryHandler(bot.handle_confirmation)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', bot.cancel),
            CommandHandler('start', bot.start)
        ],
        per_message=False,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', bot.help_command))

    # Start the bot
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
