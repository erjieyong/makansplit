import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
    COLLECTING_RECIPIENT_INFO,
    CHOOSING_SPLIT_MODE,
    TAGGING_USERS,
    MANUAL_ASSIGNMENT,
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
from paynow_storage import PayNowStorage

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
        self.user_matcher = UserMatcher()
        self.paynow_storage = PayNowStorage()

    async def makansplit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the bill splitting conversation."""
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

            # Check if user has saved PayNow info
            user_id = update.effective_user.id
            saved_paynow = self.paynow_storage.get_user_paynow(user_id)

            if saved_paynow:
                # User has saved info, ask for confirmation
                keyboard = [
                    [InlineKeyboardButton("✅ Use This Info", callback_data="paynow_confirm")],
                    [InlineKeyboardButton("✏️ Use Different Info", callback_data="paynow_new")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    "💳 *PayNow Recipient Information*\n\n"
                    "I found your saved PayNow details:\n\n"
                    f"📱 {saved_paynow['phone']}\n"
                    f"👤 {saved_paynow['name']}\n\n"
                    "Use this information?",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                # No saved info, ask for it
                chat_type = update.effective_chat.type

                if chat_type == 'private':
                    # In private chats, we can use contact sharing
                    contact_button = KeyboardButton("📱 Share My Contact", request_contact=True)
                    reply_keyboard = ReplyKeyboardMarkup(
                        [[contact_button]],
                        one_time_keyboard=True,
                        resize_keyboard=True
                    )

                    await update.message.reply_text(
                        "💳 *PayNow Recipient Information*\n\n"
                        "Please share your contact so others can pay you via PayNow.\n\n"
                        "Tap the button below to share your phone number 👇\n\n"
                        "_This is where others will send payment to._",
                        reply_markup=reply_keyboard,
                        parse_mode='Markdown'
                    )
                else:
                    # In group chats, ask for manual input
                    await update.message.reply_text(
                        "💳 *PayNow Recipient Information*\n\n"
                        "Please send your PayNow details in this format:\n\n"
                        "`+6512345678 | John Doe`\n\n"
                        "Format: `phone_number | recipient_name`\n\n"
                        "_This is where others will send payment to._",
                        parse_mode='Markdown'
                    )

            return COLLECTING_RECIPIENT_INFO

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

    async def handle_paynow_confirmation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle PayNow info confirmation."""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id

        if query.data == "paynow_confirm":
            # Use saved info
            saved_paynow = self.paynow_storage.get_user_paynow(user_id)
            if saved_paynow:
                context.user_data['paynow_phone'] = saved_paynow['phone']
                context.user_data['paynow_name'] = saved_paynow['name']

                await query.edit_message_text(
                    f"✅ Using saved PayNow info:\n"
                    f"📱 {saved_paynow['phone']}\n"
                    f"👤 {saved_paynow['name']}\n\n"
                    f"Now let's split the bill!"
                )

                # Show splitting mode options
                keyboard = [
                    [InlineKeyboardButton("➗ Split Evenly", callback_data="mode_even")],
                    [InlineKeyboardButton("✏️ Split Manually", callback_data="mode_manual")],
                    [InlineKeyboardButton("📸 Split by Photo (AI)", callback_data="mode_photo")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="\n💡 *How would you like to split the bill?*\n\n"
                         "• *Split Evenly* - Divide equally among everyone\n"
                         "• *Split Manually* - Manually assign who ate what\n"
                         "• *Split by Photo (AI)* - Auto-detect from group photo",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

                return CHOOSING_SPLIT_MODE
        else:  # paynow_new
            # Ask for new info
            await query.edit_message_text(
                "💳 *Enter New PayNow Information*\n\n"
                "Please send your PayNow details in this format:\n\n"
                "`+6512345678 | John Doe`\n\n"
                "Format: `phone_number | recipient_name`",
                parse_mode='Markdown'
            )
            return COLLECTING_RECIPIENT_INFO

    async def collect_recipient_info(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Collect PayNow recipient information from user contact."""
        # Check if contact was shared
        if update.message.contact:
            contact = update.message.contact
            phone = contact.phone_number

            # Ensure phone number has country code
            if not phone.startswith('+'):
                phone = '+' + phone

            # Get name from contact (or fallback to Telegram name)
            name = f"{contact.first_name or ''} {contact.last_name or ''}".strip()
            if not name:
                name = update.effective_user.first_name or "User"

            # Store recipient info in session and persistent storage
            context.user_data['paynow_phone'] = phone
            context.user_data['paynow_name'] = name

            user_id = update.effective_user.id
            self.paynow_storage.save_user_paynow(user_id, phone, name)

            await update.message.reply_text(
                f"✅ PayNow recipient set and saved for future use:\n"
                f"📱 {phone}\n"
                f"👤 {name}\n\n"
                f"Now let's split the bill!",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            # Handle text input (fallback for manual entry)
            message_text = update.message.text.strip()

            # Parse format: +6512345678 | John Doe
            if '|' not in message_text:
                contact_button = KeyboardButton("📱 Share My Contact", request_contact=True)
                reply_keyboard = ReplyKeyboardMarkup(
                    [[contact_button]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
                await update.message.reply_text(
                    "❌ Please share your contact using the button, or type in this format:\n\n"
                    "`+6512345678 | John Doe`",
                    reply_markup=reply_keyboard,
                    parse_mode='Markdown'
                )
                return COLLECTING_RECIPIENT_INFO

            parts = message_text.split('|')
            if len(parts) != 2:
                contact_button = KeyboardButton("📱 Share My Contact", request_contact=True)
                reply_keyboard = ReplyKeyboardMarkup(
                    [[contact_button]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
                await update.message.reply_text(
                    "❌ Invalid format. Please use: `+6512345678 | John Doe`",
                    reply_markup=reply_keyboard,
                    parse_mode='Markdown'
                )
                return COLLECTING_RECIPIENT_INFO

            phone = parts[0].strip()
            name = parts[1].strip()

            # Basic validation
            if not phone.startswith('+'):
                await update.message.reply_text(
                    "❌ Phone number must start with country code (e.g., +65)",
                    parse_mode='Markdown'
                )
                return COLLECTING_RECIPIENT_INFO

            if not name:
                await update.message.reply_text(
                    "❌ Recipient name cannot be empty",
                    parse_mode='Markdown'
                )
                return COLLECTING_RECIPIENT_INFO

            # Store recipient info in session and persistent storage
            context.user_data['paynow_phone'] = phone
            context.user_data['paynow_name'] = name

            user_id = update.effective_user.id
            self.paynow_storage.save_user_paynow(user_id, phone, name)

            await update.message.reply_text(
                f"✅ PayNow recipient set and saved for future use:\n"
                f"📱 {phone}\n"
                f"👤 {name}\n\n"
                f"Now let's split the bill!",
                reply_markup=ReplyKeyboardRemove()
            )

        # Show splitting mode options
        keyboard = [
            [InlineKeyboardButton("➗ Split Evenly", callback_data="mode_even")],
            [InlineKeyboardButton("✏️ Split Manually", callback_data="mode_manual")],
            [InlineKeyboardButton("📸 Split by Photo (AI)", callback_data="mode_photo")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "\n💡 *How would you like to split the bill?*\n\n"
            "• *Split Evenly* - Divide equally among everyone\n"
            "• *Split Manually* - Manually assign who ate what\n"
            "• *Split by Photo (AI)* - Auto-detect from group photo",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return CHOOSING_SPLIT_MODE

    async def handle_split_mode_choice(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle the user's choice of splitting mode."""
        query = update.callback_query
        await query.answer()

        if query.data == "mode_even":
            # Even split mode
            await query.edit_message_text(
                "➗ *Even Split Mode*\n\n"
                "The bill will be split equally among all participants.\n"
                "Please tag everyone who's eating using the buttons below.",
                parse_mode='Markdown'
            )
            context.user_data['split_mode'] = 'even'
            return await self.start_user_tagging(update, context)

        elif query.data == "mode_manual":
            # Manual split mode
            await query.edit_message_text(
                "✏️ *Manual Split Mode*\n\n"
                "You'll assign who ate what item by item.\n"
                "Let's start!",
                parse_mode='Markdown'
            )
            context.user_data['split_mode'] = 'manual'
            context.user_data['manual_assignments'] = {}  # {item_index: [person_ids]}
            context.user_data['current_item_index'] = 0
            return await self.start_manual_assignment(update, context)

        elif query.data == "mode_photo":
            # Photo AI mode (existing flow)
            await query.edit_message_text(
                "📸 *Photo AI Mode*\n\n"
                "Great! Now please send me a *photo of everyone at the table with their food* 📸\n\n"
                "Make sure:\n"
                "✓ Everyone's face is visible\n"
                "✓ Food items are clearly visible\n"
                "✓ Good lighting",
                parse_mode='Markdown'
            )
            context.user_data['split_mode'] = 'photo'
            return WAITING_GROUP_PHOTO

    async def start_user_tagging(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Start the user tagging process for even split."""
        # Initialize tagged users list if not exists
        if 'tagged_users' not in context.user_data:
            context.user_data['tagged_users'] = []

        # Get chat members for tagging
        chat_members = []

        # First, try to get from stored members (users who have interacted)
        if 'known_members' not in context.bot_data:
            context.bot_data['known_members'] = {}

        chat_id = update.effective_chat.id
        if chat_id not in context.bot_data['known_members']:
            context.bot_data['known_members'][chat_id] = {}

        # Add current user to known members
        current_user = update.effective_user
        context.bot_data['known_members'][chat_id][current_user.id] = {
            'id': current_user.id,
            'first_name': current_user.first_name,
            'last_name': current_user.last_name,
            'username': current_user.username,
            'mention': current_user.mention_html()
        }

        try:
            # Get chat administrators
            chat_admins = await context.bot.get_chat_administrators(chat_id)
            for admin in chat_admins:
                user = admin.user
                if not user.is_bot:
                    context.bot_data['known_members'][chat_id][user.id] = {
                        'id': user.id,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'username': user.username,
                        'mention': user.mention_html()
                    }
        except Exception as e:
            logger.warning(f"Could not get chat administrators: {e}")

        # Convert known members to list
        chat_members = list(context.bot_data['known_members'][chat_id].values())
        context.user_data['chat_members'] = chat_members

        # Build keyboard with chat members
        keyboard = []
        tagged_user_ids = context.user_data['tagged_users']

        for member in chat_members:
            display_name = member['first_name']
            if member['username']:
                display_name += f" (@{member['username']})"

            # Add checkmark if already tagged
            if member['id'] in tagged_user_ids:
                display_name = "✅ " + display_name
                callback_data = f"untag_{member['id']}"
            else:
                callback_data = f"tag_{member['id']}"

            keyboard.append([
                InlineKeyboardButton(display_name, callback_data=callback_data)
            ])

        # Add done button
        keyboard.append([
            InlineKeyboardButton("✅ Done", callback_data="tagging_done")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"👥 *Select everyone who's eating*\n\n"
        message_text += f"Currently selected: {len(tagged_user_ids)} people\n\n"
        message_text += "Tap a name to add/remove them from the split.\n\n"
        message_text += "💡 _Tip: If someone isn't in the list, ask them to send any message in this chat first!_"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return TAGGING_USERS

    async def handle_user_tagging(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle user tagging for even split."""
        query = update.callback_query
        await query.answer()

        if query.data.startswith('tag_'):
            # Add user to tagged list
            user_id = int(query.data.split('_')[1])
            if user_id not in context.user_data['tagged_users']:
                context.user_data['tagged_users'].append(user_id)
            # Refresh the keyboard
            return await self.refresh_user_tagging(update, context)

        elif query.data.startswith('untag_'):
            # Remove user from tagged list
            user_id = int(query.data.split('_')[1])
            if user_id in context.user_data['tagged_users']:
                context.user_data['tagged_users'].remove(user_id)
            # Refresh the keyboard
            return await self.refresh_user_tagging(update, context)

        elif query.data == 'tagging_done':
            # Finish tagging and calculate even split
            tagged_users = context.user_data['tagged_users']

            if len(tagged_users) == 0:
                await query.answer("Please select at least one person!", show_alert=True)
                return TAGGING_USERS

            await query.edit_message_text(
                f"✅ Selected {len(tagged_users)} people for even split!"
            )

            # Calculate even split
            bill_data = context.user_data['bill_data']
            total = bill_data['total']
            per_person = round(total / len(tagged_users), 2)

            # Create totals dict
            totals = {user_id: per_person for user_id in tagged_users}
            context.user_data['totals'] = totals
            context.user_data['matches'] = {i+1: user_id for i, user_id in enumerate(tagged_users)}

            # Store user info for later
            chat_members = context.user_data.get('chat_members', [])
            user_info = {member['id']: member for member in chat_members}
            context.user_data['user_info'] = user_info

            # Show summary with recipient info
            paynow_phone = context.user_data.get('paynow_phone', 'N/A')
            paynow_name = context.user_data.get('paynow_name', 'N/A')

            summary = f"📊 *Even Split Summary*\n\n"
            summary += f"Total: ${total:.2f}\n"
            summary += f"Split {len(tagged_users)} ways: ${per_person:.2f} per person\n\n"
            summary += "*People:*\n"
            for user_id in tagged_users:
                if user_id in user_info:
                    summary += f"• {user_info[user_id]['first_name']} - ${per_person:.2f}\n"

            summary += f"\n*PayNow Recipient:*\n"
            summary += f"📱 {paynow_phone}\n"
            summary += f"👤 {paynow_name}"

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=summary,
                parse_mode='Markdown'
            )

            # Ask for confirmation
            keyboard = [
                [
                    InlineKeyboardButton("✅ Looks good!", callback_data="confirm_yes"),
                    InlineKeyboardButton("❌ Cancel", callback_data="confirm_cancel"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="\n*Does this look correct?*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

            return CONFIRMING

    async def refresh_user_tagging(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Refresh the user tagging keyboard."""
        query = update.callback_query

        # Get chat members
        chat_members = context.user_data.get('chat_members', [])
        tagged_user_ids = context.user_data['tagged_users']

        # Build keyboard
        keyboard = []
        for member in chat_members:
            display_name = member['first_name']
            if member['username']:
                display_name += f" (@{member['username']})"

            # Add checkmark if already tagged
            if member['id'] in tagged_user_ids:
                display_name = "✅ " + display_name
                callback_data = f"untag_{member['id']}"
            else:
                callback_data = f"tag_{member['id']}"

            keyboard.append([
                InlineKeyboardButton(display_name, callback_data=callback_data)
            ])

        # Add done button
        keyboard.append([
            InlineKeyboardButton("✅ Done", callback_data="tagging_done")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"👥 *Select everyone who's eating*\n\n"
        message_text += f"Currently selected: {len(tagged_user_ids)} people\n\n"
        message_text += "Tap a name to add/remove them from the split.\n\n"
        message_text += "💡 _Tip: If someone isn't in the list, ask them to send any message in this chat first!_"

        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return TAGGING_USERS

    async def start_manual_assignment(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Start the manual item assignment process."""
        bill_data = context.user_data['bill_data']
        items = bill_data['items']
        current_index = context.user_data['current_item_index']

        if current_index >= len(items):
            # All items assigned, show summary
            return await self.show_manual_split_summary(update, context)

        item = items[current_index]

        # Get chat members
        if 'chat_members' not in context.user_data:
            chat_members = []

            # First, try to get from stored members (users who have interacted)
            if 'known_members' not in context.bot_data:
                context.bot_data['known_members'] = {}

            chat_id = update.effective_chat.id
            if chat_id not in context.bot_data['known_members']:
                context.bot_data['known_members'][chat_id] = {}

            # Add current user to known members
            current_user = update.effective_user
            context.bot_data['known_members'][chat_id][current_user.id] = {
                'id': current_user.id,
                'first_name': current_user.first_name,
                'last_name': current_user.last_name,
                'username': current_user.username,
                'mention': current_user.mention_html()
            }

            try:
                # Get chat administrators
                chat_admins = await context.bot.get_chat_administrators(chat_id)
                for admin in chat_admins:
                    user = admin.user
                    if not user.is_bot:
                        context.bot_data['known_members'][chat_id][user.id] = {
                            'id': user.id,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'username': user.username,
                            'mention': user.mention_html()
                        }
            except Exception as e:
                logger.warning(f"Could not get chat administrators: {e}")

            # Convert known members to list
            chat_members = list(context.bot_data['known_members'][chat_id].values())
            context.user_data['chat_members'] = chat_members

        # Initialize assignment for this item if not exists
        if current_index not in context.user_data['manual_assignments']:
            context.user_data['manual_assignments'][current_index] = []

        # Build keyboard
        keyboard = []
        assigned_users = context.user_data['manual_assignments'][current_index]
        chat_members = context.user_data['chat_members']

        for member in chat_members:
            display_name = member['first_name']
            if member['username']:
                display_name += f" (@{member['username']})"

            # Add checkmark if already assigned
            if member['id'] in assigned_users:
                display_name = "✅ " + display_name
                callback_data = f"unassign_{current_index}_{member['id']}"
            else:
                callback_data = f"assign_{current_index}_{member['id']}"

            keyboard.append([
                InlineKeyboardButton(display_name, callback_data=callback_data)
            ])

        # Add select all / deselect all button
        if len(assigned_users) == len(chat_members):
            keyboard.append([
                InlineKeyboardButton("❌ Deselect All", callback_data=f"deselect_all_{current_index}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("✅ Select All", callback_data=f"select_all_{current_index}")
            ])

        # Add skip and next buttons
        keyboard.append([
            InlineKeyboardButton("⏭ Skip item", callback_data=f"skip_item_{current_index}")
        ])
        if len(assigned_users) > 0:
            keyboard.append([
                InlineKeyboardButton("➡️ Next item", callback_data=f"next_item_{current_index}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"📝 *Item {current_index + 1}/{len(items)}*\n\n"
        message_text += f"*{item['name']}* - ${item['price']:.2f}\n\n"
        message_text += f"Currently assigned to: {len(assigned_users)} people\n\n"
        message_text += "Select who ate this item (can select multiple):"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return MANUAL_ASSIGNMENT

    async def handle_manual_assignment(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Handle manual item assignment."""
        query = update.callback_query
        await query.answer()

        if query.data.startswith('assign_'):
            # Add user to item assignment
            parts = query.data.split('_')
            item_index = int(parts[1])
            user_id = int(parts[2])

            if user_id not in context.user_data['manual_assignments'][item_index]:
                context.user_data['manual_assignments'][item_index].append(user_id)

            # Refresh the keyboard
            return await self.refresh_manual_assignment(update, context)

        elif query.data.startswith('unassign_'):
            # Remove user from item assignment
            parts = query.data.split('_')
            item_index = int(parts[1])
            user_id = int(parts[2])

            if user_id in context.user_data['manual_assignments'][item_index]:
                context.user_data['manual_assignments'][item_index].remove(user_id)

            # Refresh the keyboard
            return await self.refresh_manual_assignment(update, context)

        elif query.data.startswith('select_all_'):
            # Select all users for this item
            item_index = int(query.data.split('_')[2])
            chat_members = context.user_data['chat_members']
            context.user_data['manual_assignments'][item_index] = [member['id'] for member in chat_members]

            # Refresh the keyboard
            return await self.refresh_manual_assignment(update, context)

        elif query.data.startswith('deselect_all_'):
            # Deselect all users for this item
            item_index = int(query.data.split('_')[2])
            context.user_data['manual_assignments'][item_index] = []

            # Refresh the keyboard
            return await self.refresh_manual_assignment(update, context)

        elif query.data.startswith('skip_item_'):
            # Skip this item
            await query.edit_message_text(
                f"⏭ Skipped item {context.user_data['current_item_index'] + 1}"
            )
            context.user_data['current_item_index'] += 1
            return await self.start_manual_assignment(update, context)

        elif query.data.startswith('next_item_'):
            # Move to next item
            item_index = context.user_data['current_item_index']
            assigned_count = len(context.user_data['manual_assignments'][item_index])

            await query.edit_message_text(
                f"✅ Item {item_index + 1} assigned to {assigned_count} people"
            )

            context.user_data['current_item_index'] += 1
            return await self.start_manual_assignment(update, context)

    async def refresh_manual_assignment(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Refresh the manual assignment keyboard."""
        query = update.callback_query

        bill_data = context.user_data['bill_data']
        items = bill_data['items']
        current_index = context.user_data['current_item_index']
        item = items[current_index]

        # Build keyboard
        keyboard = []
        assigned_users = context.user_data['manual_assignments'][current_index]
        chat_members = context.user_data['chat_members']

        for member in chat_members:
            display_name = member['first_name']
            if member['username']:
                display_name += f" (@{member['username']})"

            # Add checkmark if already assigned
            if member['id'] in assigned_users:
                display_name = "✅ " + display_name
                callback_data = f"unassign_{current_index}_{member['id']}"
            else:
                callback_data = f"assign_{current_index}_{member['id']}"

            keyboard.append([
                InlineKeyboardButton(display_name, callback_data=callback_data)
            ])

        # Add select all / deselect all button
        if len(assigned_users) == len(chat_members):
            keyboard.append([
                InlineKeyboardButton("❌ Deselect All", callback_data=f"deselect_all_{current_index}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton("✅ Select All", callback_data=f"select_all_{current_index}")
            ])

        # Add skip and next buttons
        keyboard.append([
            InlineKeyboardButton("⏭ Skip item", callback_data=f"skip_item_{current_index}")
        ])
        if len(assigned_users) > 0:
            keyboard.append([
                InlineKeyboardButton("➡️ Next item", callback_data=f"next_item_{current_index}")
            ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        message_text = f"📝 *Item {current_index + 1}/{len(items)}*\n\n"
        message_text += f"*{item['name']}* - ${item['price']:.2f}\n\n"
        message_text += f"Currently assigned to: {len(assigned_users)} people\n\n"
        message_text += "Select who ate this item (can select multiple):"

        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return MANUAL_ASSIGNMENT

    async def show_manual_split_summary(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Show summary of manual split assignments."""
        bill_data = context.user_data['bill_data']
        items = bill_data['items']
        assignments = context.user_data['manual_assignments']
        chat_members = context.user_data.get('chat_members', [])
        user_info = {member['id']: member for member in chat_members}

        # Calculate totals per user
        totals = {}
        for item_index, user_ids in assignments.items():
            if len(user_ids) > 0:
                item = items[item_index]
                # Split item equally among assigned users
                share_per_person = item['total_price'] / len(user_ids)

                for user_id in user_ids:
                    if user_id not in totals:
                        totals[user_id] = 0
                    totals[user_id] += share_per_person

        # Round totals
        for user_id in totals:
            totals[user_id] = round(totals[user_id], 2)

        context.user_data['totals'] = totals
        context.user_data['user_info'] = user_info
        context.user_data['matches'] = {i+1: user_id for i, user_id in enumerate(totals.keys())}

        # Build summary message
        summary = "📊 *Manual Split Summary*\n\n"

        for user_id, total in totals.items():
            if user_id in user_info:
                user_name = user_info[user_id]['first_name']
                summary += f"*{user_name}* - ${total:.2f}\n"

                # Show items for this user
                user_items = []
                for item_index, assigned_users in assignments.items():
                    if user_id in assigned_users:
                        item = items[item_index]
                        share = f"({len(assigned_users)} way split)" if len(assigned_users) > 1 else ""
                        user_items.append(f"  • {item['name']} {share}")

                if user_items:
                    summary += '\n'.join(user_items)
                    summary += "\n\n"

        # Show unassigned items
        unassigned = []
        for i, item in enumerate(items):
            if i not in assignments or len(assignments[i]) == 0:
                unassigned.append(f"• {item['name']} - ${item['price']:.2f}")

        if unassigned:
            summary += "\n⚠️ *Unassigned items:*\n"
            summary += '\n'.join(unassigned)
            summary += "\n\n"

        # Add PayNow recipient info
        paynow_phone = context.user_data.get('paynow_phone', 'N/A')
        paynow_name = context.user_data.get('paynow_name', 'N/A')
        summary += f"\n*PayNow Recipient:*\n"
        summary += f"📱 {paynow_phone}\n"
        summary += f"👤 {paynow_name}"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=summary,
            parse_mode='Markdown'
        )

        # Ask for confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Looks good!", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Cancel", callback_data="confirm_cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="\n*Does this look correct?*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return CONFIRMING

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

        # Show PayNow recipient info
        paynow_phone = context.user_data.get('paynow_phone', 'N/A')
        paynow_name = context.user_data.get('paynow_name', 'N/A')
        recipient_text = f"\n*PayNow Recipient:*\n📱 {paynow_phone}\n👤 {paynow_name}\n"

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=recipient_text,
            parse_mode='Markdown'
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
            totals = context.user_data['totals']
            user_info = context.user_data.get('user_info', {})
            split_mode = context.user_data.get('split_mode', 'photo')

            # Create PayNowGenerator with dynamic recipient info
            paynow_phone = context.user_data.get('paynow_phone')
            paynow_name = context.user_data.get('paynow_name')

            if not paynow_phone or not paynow_name:
                await context.bot.send_message(
                    chat_id=context.user_data['chat_id'],
                    text="❌ PayNow recipient information missing. Please restart with /makansplit"
                )
                return ConversationHandler.END

            paynow_generator = PayNowGenerator(paynow_phone, paynow_name)

            restaurant = bill_data.get('restaurant', 'Restaurant')

            # Handle different split modes
            if split_mode == 'even':
                # Even split: send to each tagged user
                for user_id, amount in totals.items():
                    user_name = user_info.get(user_id, {}).get('first_name', 'there')

                    message = f"💰 *Bill Split Request*\n\n"
                    message += f"📍 {restaurant}\n"
                    message += f"Your share (even split): *${amount:.2f}*\n\n"
                    message += f"*Pay to:*\n"
                    message += f"📱 {paynow_phone}\n"
                    message += f"👤 {paynow_name}\n\n"
                    message += "Please scan the QR code below to pay via PayNow."

                    # Generate QR code
                    reference = f"{restaurant[:15]} split"
                    qr_code = paynow_generator.generate_qr_code(
                        amount, reference, user_name
                    )

                    # Send direct message
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"Hi {user_name}! 👋\n\n" + message,
                            parse_mode='Markdown'
                        )

                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=qr_code,
                            caption=f"PayNow QR Code - ${amount:.2f}"
                        )

                        # Notify group
                        await context.bot.send_message(
                            chat_id=context.user_data['chat_id'],
                            text=f"✅ Payment request sent to {user_name} via DM"
                        )
                        logger.info(f"Sent payment request to user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send DM to user {user_id}: {e}")
                        await context.bot.send_message(
                            chat_id=context.user_data['chat_id'],
                            text=f"⚠️ Could not send DM to {user_name}. Please share the QR manually."
                        )

            elif split_mode == 'manual':
                # Manual split: send to each user with their items
                assignments = context.user_data['manual_assignments']
                items = bill_data['items']

                for user_id, amount in totals.items():
                    user_name = user_info.get(user_id, {}).get('first_name', 'there')

                    # Get items for this user
                    user_items = []
                    for item_index, assigned_users in assignments.items():
                        if user_id in assigned_users:
                            item = items[item_index].copy()
                            item['share_ratio'] = 1.0 / len(assigned_users)
                            user_items.append(item)

                    # Generate message
                    message = paynow_generator.format_payment_message(
                        amount, user_items, restaurant
                    )

                    # Generate QR code
                    reference = f"{restaurant[:15]} split"
                    qr_code = paynow_generator.generate_qr_code(
                        amount, reference, user_name
                    )

                    # Send direct message
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"Hi {user_name}! 👋\n\n" + message,
                            parse_mode='Markdown'
                        )

                        await context.bot.send_photo(
                            chat_id=user_id,
                            photo=qr_code,
                            caption=f"PayNow QR Code - ${amount:.2f}"
                        )

                        # Notify group
                        await context.bot.send_message(
                            chat_id=context.user_data['chat_id'],
                            text=f"✅ Payment request sent to {user_name} via DM"
                        )
                        logger.info(f"Sent payment request to user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send DM to user {user_id}: {e}")
                        await context.bot.send_message(
                            chat_id=context.user_data['chat_id'],
                            text=f"⚠️ Could not send DM to {user_name}. Please share the QR manually."
                        )

            else:  # split_mode == 'photo'
                # Photo AI mode: existing logic
                people_data = context.user_data['people_data']
                matches = context.user_data.get('matches', {})

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
                    message = paynow_generator.format_payment_message(
                        amount, person_items, restaurant
                    )

                    # Generate QR code
                    reference = f"{restaurant[:15]} split"
                    qr_code = paynow_generator.generate_qr_code(
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
                     "Use /makansplit to split another bill.",
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

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Welcome message for new users."""
        await update.message.reply_text(
            "👋 *Welcome to MakanSplit!*\n\n"
            "I help you split restaurant bills fairly in Singapore using PayNow!\n\n"
            "*Quick Start:*\n"
            "Use /makansplit to begin splitting a bill\n\n"
            "*Commands:*\n"
            "• /makansplit - Start bill splitting\n"
            "• /help - Show detailed help\n"
            "• /cancel - Cancel current operation",
            parse_mode='Markdown'
        )

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        await update.message.reply_text(
            "❌ Cancelled. Send /makansplit to begin again."
        )
        return ConversationHandler.END

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        await update.message.reply_text(
            "*MakanSplit Bot* 💰\n\n"
            "I help you split restaurant bills with three different modes!\n\n"
            "*Commands:*\n"
            "/makansplit - Start splitting a bill\n"
            "/cancel - Cancel current operation\n"
            "/help - Show this help message\n\n"
            "*How it works:*\n"
            "1. Send me a photo of your bill\n"
            "2. Choose a splitting mode:\n"
            "   • *Even Split* - Divide equally among everyone\n"
            "   • *Manual Split* - Assign who ate what item by item\n"
            "   • *Photo AI Split* - Auto-detect from group photo\n"
            "3. Confirm and receive PayNow QR codes\n\n"
            "*Tips for best results:*\n"
            "• Use clear, well-lit photos\n"
            "• Make sure all text on bill is readable\n"
            "• For Photo AI mode: ensure faces and food are visible",
            parse_mode='Markdown'
        )

    async def track_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Track users who send messages in the group."""
        if update.effective_chat.type in ['group', 'supergroup']:
            user = update.effective_user

            # Initialize known_members if not exists
            if 'known_members' not in context.bot_data:
                context.bot_data['known_members'] = {}

            chat_id = update.effective_chat.id
            if chat_id not in context.bot_data['known_members']:
                context.bot_data['known_members'][chat_id] = {}

            # Add user to known members
            if not user.is_bot:
                context.bot_data['known_members'][chat_id][user.id] = {
                    'id': user.id,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'username': user.username,
                    'mention': user.mention_html()
                }


def main():
    """Start the bot."""
    # Create bot instance
    bot = BillSplitterBot()

    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('makansplit', bot.makansplit)],
        states={
            WAITING_BILL_PHOTO: [
                CommandHandler('makansplit', bot.makansplit),
                MessageHandler(filters.PHOTO, bot.receive_bill_photo)
            ],
            COLLECTING_RECIPIENT_INFO: [
                CommandHandler('makansplit', bot.makansplit),
                CallbackQueryHandler(bot.handle_paynow_confirmation, pattern="^paynow_"),
                MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), bot.collect_recipient_info)
            ],
            CHOOSING_SPLIT_MODE: [
                CommandHandler('makansplit', bot.makansplit),
                CallbackQueryHandler(bot.handle_split_mode_choice)
            ],
            TAGGING_USERS: [
                CommandHandler('makansplit', bot.makansplit),
                CallbackQueryHandler(bot.handle_user_tagging)
            ],
            MANUAL_ASSIGNMENT: [
                CommandHandler('makansplit', bot.makansplit),
                CallbackQueryHandler(bot.handle_manual_assignment)
            ],
            WAITING_GROUP_PHOTO: [
                CommandHandler('makansplit', bot.makansplit),
                MessageHandler(filters.PHOTO, bot.receive_group_photo)
            ],
            MATCHING_USERS: [
                CommandHandler('makansplit', bot.makansplit),
                CallbackQueryHandler(bot.handle_person_match),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_manual_input)
            ],
            CONFIRMING: [
                CommandHandler('makansplit', bot.makansplit),
                CallbackQueryHandler(bot.handle_confirmation)
            ],
            CORRECTING: [
                CommandHandler('makansplit', bot.makansplit),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_corrections),
                CallbackQueryHandler(bot.handle_confirmation)
            ],
        },
        fallbacks=[
            CommandHandler('cancel', bot.cancel),
            CommandHandler('makansplit', bot.makansplit)
        ],
        per_message=False,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', bot.start))
    application.add_handler(CommandHandler('help', bot.help_command))

    # Add message handler to track users in groups (runs for all messages)
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, bot.track_user),
        group=1  # Lower priority so it doesn't interfere with conversation handler
    )

    # Start the bot
    logger.info("Bot started!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
