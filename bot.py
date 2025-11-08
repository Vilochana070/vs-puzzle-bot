import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Your bot token from BotFather
BOT_TOKEN = "8530850320:AAEu7WsHMMKrfTlHuapB-87Sz2IVBh9LBcA"

# Google Sheets Setup
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "credentials.json"
SPREADSHEET_ID = "154DG6M8zXbRyQljVOyYWujVaIZeW1kQQxkVo7LlNhcY"

def get_google_sheets():
    creds = Credentials.from_service_account_file(CREDS_FILE, scopes=SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    return spreadsheet

# TEST: Check if credentials file exists and can be read
try:
    with open("credentials.json", "r") as f:
        print("✅ credentials.json file exists and can be read!")
except Exception as e:
    print(f"❌ Cannot read credentials.json: {e}")

# 🆕 INDIVIDUAL PIECE MANAGEMENT FUNCTIONS
def get_available_piece(event_name, piece_number):
    """Find available fresh piece with auto-expiry check"""
    try:
        spreadsheet = get_google_sheets()
        pieces_sheet = spreadsheet.worksheet("pieces")  # 🆕 NEW SHEET
        
        records = pieces_sheet.get_all_records()
        current_time = datetime.now()
        
        for i, piece in enumerate(records):
            if (piece["Event"] == event_name and 
                str(piece["Piece"]) == piece_number and
                piece["Status"] == "available"):
                
                # 🆕 CHECK EXPIRY
                created_at = datetime.strptime(piece["Created At"], "%Y-%m-%d %H:%M:%S")
                expires_at = created_at + timedelta(hours=24)
                
                if current_time < expires_at:
                    # ✅ FRESH PIECE FOUND
                    hours_left = (expires_at - current_time).total_seconds() / 3600
                    print(f"✅ Found fresh piece: {piece['Piece ID']} ({hours_left:.1f}h left)")
                    return piece, hours_left
                else:
                    # ❌ EXPIRED - AUTO MARK
                    pieces_sheet.update_cell(i + 2, 11, "expired")  # Status column
                    print(f"🔄 Auto-expired {piece['Piece ID']}")
        
        return None, 0  # No available fresh pieces
        
    except Exception as e:
        print(f"Error finding available piece: {e}")
        return None, 0

def mark_piece_sold(piece_id, user_id):
    """Mark piece as sold to specific user"""
    try:
        spreadsheet = get_google_sheets()
        pieces_sheet = spreadsheet.worksheet("pieces")
        
        records = pieces_sheet.get_all_records()
        for i, piece in enumerate(records):
            if piece["Piece ID"] == piece_id:
                pieces_sheet.update_cell(i + 2, 11, "sold")      # Status
                pieces_sheet.update_cell(i + 2, 12, user_id)     # Sold To
                print(f"✅ Marked {piece_id} as sold to {user_id}")
                return True
        return False
    except Exception as e:
        print(f"Error marking piece sold: {e}")
        return False

def format_time_left(hours):
    """Format hours into readable time"""
    if hours >= 1:
        return f"{int(hours)} hours {int((hours % 1) * 60)} minutes"
    else:
        return f"{int(hours * 60)} minutes"

# 🆕 ADMIN NOTIFICATION FUNCTION
async def send_expiry_notifications(app):
    """Send notifications for pieces expiring in 1 hour"""
    try:
        spreadsheet = get_google_sheets()
        pieces_sheet = spreadsheet.worksheet("pieces")
        
        records = pieces_sheet.get_all_records()
        current_time = datetime.now()
        expiring_pieces = []
        
        for piece in records:
            if piece["Status"] == "available":
                created_at = datetime.strptime(piece["Created At"], "%Y-%m-%d %H:%M:%S")
                expires_at = created_at + timedelta(hours=24)
                time_left = (expires_at - current_time).total_seconds() / 3600
                
                if 0 < time_left <= 1:  # Expiring in 1 hour
                    expiring_pieces.append(f"{piece['Piece ID']} ({format_time_left(time_left)})")
        
        if expiring_pieces:
            notification = "🔔 PUZZLES EXPIRING IN 1 HOUR:\n" + "\n".join(expiring_pieces)
            print(notification)
            # 🆕 You can add code here to send to your Telegram
            # await app.bot.send_message(YOUR_CHAT_ID, notification)
            
    except Exception as e:
        print(f"Notification error: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "No username"
    first_name = update.message.from_user.first_name or "User"
    
    try:
        spreadsheet = get_google_sheets()
        users_sheet = spreadsheet.worksheet("users")
        
        # Check if user already exists and get subscription status
        users_data = users_sheet.get_all_records()
        user_exists = False
        is_subscribed = False
        
        for user in users_data:
            if user["User ID"] == user_id:
                user_exists = True
                is_subscribed = user["Subscription"] == "subscribed"
                break
        
        if not user_exists:
            # 🆕 NEW USER - ADD WITH WELCOME GIFT
            users_sheet.append_row([
                user_id,
                username,
                0.3,  # 🎁 $0.30 WELCOME GIFT
                "not subscribed",
                first_name,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
            print(f"✅ New user registered: {user_id} ({username}) with $0.30 gift")
            welcome_gift_msg = "🎁 Welcome Gift: $0.30 has been added to your balance!"
            is_subscribed = False
        else:
            welcome_gift_msg = "👋 Welcome !!!"
        
        # 🆕 DYNAMIC BUTTONS BASED ON SUBSCRIPTION STATUS
        if is_subscribed:
            # User is subscribed - show Unsubscribe button
            keyboard = [
                ["🛒 Buy", "💳 Topup"],
                ["💰 Balance", "🔕 Unsubscribe"]
            ]
        else:
            # User is not subscribed - show Subscribe button
            keyboard = [
                ["🛒 Buy", "💳 Topup"],
                ["💰 Balance", "🔔 Subscribe To Updates"]
            ]
            
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        welcome_text = f"""
{welcome_gift_msg}

🧩 Welcome to "VS PUZZLE STORE" 🧩

📌Telegram Chanel : https://t.me/+5AXKwulSKHsxYzdl

🖇Available Commands:
• Buy - Purchase puzzle pieces
• Topup - Add balance to your account  
• Balance - Check your current balance
• Subscribe to updates - Get notified about new pieces

What would you like to do?
        """
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
        
    except Exception as e:
        print(f"Start command error: {e}")
        # Fallback to basic buttons if error
        keyboard = [
            ["🛒 Buy", "💳 Topup"],
            ["💰 Balance", "🔔 Subscribe To Updates"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        fallback_text = "👋 Welcome! Use the buttons below to get started!"
        await update.message.reply_text(fallback_text, reply_markup=reply_markup)

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Get Google Sheets
        spreadsheet = get_google_sheets()
        events_sheet = spreadsheet.worksheet("events")
        
        # Get active events
        events_data = events_sheet.get_all_records()
        active_events = [event["Event Name"] for event in events_data if event["Status"] == "active"]
        
        # If no active events, use default
        if not active_events:
            active_events = ["MNT", "XPL", "ABC", "DEF"]
            print("⚠ No active events found, using defaults")
        
        # Create keyboard with active events
        keyboard = []
        for i in range(0, len(active_events), 2):
            row = active_events[i:i+2]
            keyboard.append(row)
        keyboard.append(["Back to Main Menu"])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "🎯 Select which event you want to buy from:",
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"❌ Error loading events: {e}")
        await update.message.reply_text("❌ Error loading events. Please try again.")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    try:
        spreadsheet = get_google_sheets()
        users_sheet = spreadsheet.worksheet("users")
        
        # Find user in sheet
        users_data = users_sheet.get_all_records()
        user_balance = 0
        user_found = False
        
        for user in users_data:
            if user["User ID"] == user_id:
                user_balance = user["Balance"]
                user_found = True
                break
        
        if not user_found:
            # 🆕 AUTO-REGISTER IF USER NOT FOUND
            username = update.message.from_user.username or "No username"
            first_name = update.message.from_user.first_name or "User"
            
            users_sheet.append_row([
                user_id,
                username,
                0.3,  # 🎁 WELCOME GIFT
                "not subscribed",
                first_name,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
            user_balance = 0.3
            print(f"✅ Auto-registered user in balance check: {user_id}")
        
        await update.message.reply_text(f"💰 Your current balance: ${user_balance}")
        
    except Exception as e:
        print(f"Balance error: {e}")
        await update.message.reply_text("❌ Error checking balance. Please try again.")

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    try:
        spreadsheet = get_google_sheets()
        users_sheet = spreadsheet.worksheet("users")
        
        # Get user's subscription status
        users_data = users_sheet.get_all_records()
        is_subscribed = False
        
        for user in users_data:
            if user["User ID"] == user_id:
                is_subscribed = user["Subscription"] == "subscribed"
                break
        
        # 🆕 DYNAMIC BUTTONS BASED ON SUBSCRIPTION STATUS
        if is_subscribed:
            keyboard = [
                ["🛒 Buy", "💳 Topup"],
                ["💰 Balance", "🔕 Unsubscribe"]
            ]
        else:
            keyboard = [
                ["🛒 Buy", "💳 Topup"],
                ["💰 Balance", "🔔 Subscribe To Updates"]
            ]
            
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        return_text = """
👋 Welcome !!!

🧩 Welcome to "VS PUZZLE STORE" 🧩

📌Telegram Chanel : https://t.me/+5AXKwulSKHsxYzdl

🖇Available Commands:
• Buy - Purchase puzzle pieces
• Topup - Add balance to your account  
• Balance - Check your current balance
• Subscribe to updates - Get notified about new pieces

What would you like to do?
    """
    
        await update.message.reply_text(return_text, reply_markup=reply_markup)
        
    except Exception as e:
        print(f"Back to main error: {e}")
        # Fallback buttons
        keyboard = [
            ["🛒 Buy", "💳 Topup"],
            ["💰 Balance", "🔔 Subscribe To Updates"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("🔄 Returned to main menu!", reply_markup=reply_markup)

async def topup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    instructions = """
💳 How to Top Up Your Balance:

1. Contact @Indrajith00 directly
 
2. Send your payment.( You can pay via Bybit ID, Giveaway, Binance ID Or USDT Aptos.)

3. Wait for confirmation

4. Your balance will be updated manually

📞 Contact: @Indrajith00
💵 Minimum Deposit : $1

Once payment is confirmed, your balance will be updated within 3 hours!
    """
    
    await update.message.reply_text(instructions)

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "No username"
    
    try:
        spreadsheet = get_google_sheets()
        users_sheet = spreadsheet.worksheet("users")
        
        # Find user in sheet
        users_data = users_sheet.get_all_records()
        user_found = False
        
        for user in users_data:
            if user["User ID"] == user_id:
                # Update subscription status
                users_sheet.update_cell(users_data.index(user) + 2, 4, "subscribed")
                user_found = True
                break
        
        if not user_found:
            # Add new user as subscribed
            users_sheet.append_row([user_id, username, 0, "subscribed"])
        
        # 🆕 SHOW UNSUBSCRIBE BUTTON AFTER SUBSCRIBING
        keyboard = [
            ["🛒 Buy", "💳 Topup"],
            ["💰 Balance", "🔕 Unsubscribe"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "✅ Subscribed!\n\n"
            "You will now receive notifications when new puzzles are added.\n\n"
            "You can unsubscribe anytime from the menu.",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        print(f"Subscribe error: {e}")
        await update.message.reply_text("❌ Error subscribing. Please try again.")

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    try:
        spreadsheet = get_google_sheets()
        users_sheet = spreadsheet.worksheet("users")
        
        # Find user in sheet and update subscription status
        users_data = users_sheet.get_all_records()
        user_found = False
        
        for i, user in enumerate(users_data):
            if user["User ID"] == user_id:
                users_sheet.update_cell(i + 2, 4, "not subscribed")
                user_found = True
                break
        
        if user_found:
            # 🆕 SHOW SUBSCRIBE BUTTON AFTER UNSUBSCRIBING
            keyboard = [
                ["🛒 Buy", "💳 Topup"],
                ["💰 Balance", "🔔 Subscribe To Updates"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                "🔕 Unsubscribed\n\n"
                "You will no longer receive puzzle notifications.\n\n"
                "You can re-subscribe anytime from the menu.",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ You were not subscribed to updates.")
        
    except Exception as e:
        print(f"Unsubscribe error: {e}")
        await update.message.reply_text("❌ Error unsubscribing. Please try again.")

async def send_broadcast_to_subscribers(app, message):
    """Send message to all subscribed users"""
    try:
        spreadsheet = get_google_sheets()
        users_sheet = spreadsheet.worksheet("users")
        
        users_data = users_sheet.get_all_records()
        subscribed_users = [user for user in users_data if user["Subscription"] == "subscribed"]
        
        success_count = 0
        fail_count = 0
        
        for user in subscribed_users:
            try:
                await app.bot.send_message(
                    chat_id=user["User ID"],
                    text=message
                )
                success_count += 1
                # Small delay to avoid hitting rate limits
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Failed to send to user {user['User ID']}: {e}")
                fail_count += 1
        
        print(f"📢 Broadcast sent: {success_count} successful, {fail_count} failed")
        return success_count, fail_count
        
    except Exception as e:
        print(f"Broadcast error: {e}")
        return 0, 0

async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to send broadcast messages"""
    
    ADMIN_USER_ID = 1557321125 
    
    if update.message.from_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ This command is for administrators only.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast <message>\n\n"
            "Example: /broadcast 🎉 New puzzles added! Check them out now!"
        )
        return
    
    message = " ".join(context.args)
    
    await update.message.reply_text("🔄 Sending broadcast to subscribers...")
    
    success_count, fail_count = await send_broadcast_to_subscribers(context.application, message)
    
    await update.message.reply_text(
        f"✅ Broadcast completed!\n"
        f"• Successful: {success_count}\n"
        f"• Failed: {fail_count}"
    )

async def handle_event_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_event = update.message.text
    context.user_data['selected_event'] = selected_event
    
    try:
        spreadsheet = get_google_sheets()
        pieces_sheet = spreadsheet.worksheet("pieces")  # 🆕 USING PIECES SHEET
        
        # 🆕 GET AVAILABLE PIECES (NOT SOLD OUT)
        pieces_data = pieces_sheet.get_all_records()
        available_pieces = set()
        
        for piece in pieces_data:
            if (piece["Event"] == selected_event and 
                piece["Status"] == "available" and
                datetime.now() < datetime.strptime(piece["Created At"], "%Y-%m-%d %H:%M:%S") + timedelta(hours=24)):
                available_pieces.add(str(piece["Piece"]))
        
        available_pieces = sorted(list(available_pieces))
        
        if available_pieces:
            # Create number buttons
            keyboard = []
            row = []
            for i, piece in enumerate(available_pieces):
                row.append(piece)
                if (i + 1) % 3 == 0:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
            
            keyboard.append(["Back to Main Menu"])
            
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                f"🧩 Available pieces for {selected_event}:\n\n"
                f"Select a puzzle number:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"❌ No pieces available for {selected_event} right now.",
                reply_markup=ReplyKeyboardMarkup([["Back to Main Menu"]], resize_keyboard=True)
            )
            
    except Exception as e:
        print(f"Event selection error: {e}")
        await update.message.reply_text("❌ Error loading pieces. Please try again.")

async def handle_puzzle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    puzzle_number = update.message.text
    event_name = context.user_data.get('selected_event')
    
    print(f"🔄 User {user_id} selected: {event_name} - Piece #{puzzle_number}")
    
    try:
        # 🆕 FIND AVAILABLE FRESH PIECE
        available_piece, hours_left = get_available_piece(event_name, puzzle_number)
        
        if not available_piece:
            await update.message.reply_text(
                f"❌ Piece {puzzle_number} not available or expired for {event_name}.",
                reply_markup=ReplyKeyboardMarkup([["Back to Main Menu"]], resize_keyboard=True)
            )
            return
        
        price = available_piece["Price"]
        
        # Check user balance
        spreadsheet = get_google_sheets()
        users_sheet = spreadsheet.worksheet("users")
        users_data = users_sheet.get_all_records()
        
        user_balance = 0
        user_row = None
        
        for i, user in enumerate(users_data):
            if user["User ID"] == user_id:
                user_balance = user["Balance"]
                user_row = i + 2
                break
        
        if user_balance >= price:
            # 🆕 STORE PIECE INFO FOR CONFIRMATION
            context.user_data['pending_purchase'] = {
                'event': event_name,
                'piece': puzzle_number,
                'price': price,
                'user_row': user_row,
                'piece_id': available_piece["Piece ID"],
                'puzzle_link': available_piece["Puzzle Link"],
                'puzzle_code': available_piece["Puzzle Code"],
                'qr_path': available_piece.get("QR Path", ""),
                'hours_left': hours_left
            }
            
            # Show confirmation
            keyboard = [
                [f"✅ Confirm Purchase - ${price}"],
                ["❌ Cancel"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(
                f"🛒 Purchase Details:\n\n"
                f"• Event: {event_name}\n"
                f"• Piece: #{puzzle_number}\n"
                f"• Price: ${price}\n"
                f"• Your Balance: ${user_balance}\n"
                f"• Expires In: {format_time_left(hours_left)}\n\n"
                f"Confirm purchase?",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"❌ Insufficient balance!\n"
                f"Price: ${price} | Your Balance: ${user_balance}\n\n"
                f"Please top up your balance first.",
                reply_markup=ReplyKeyboardMarkup([["Back to Main Menu"]], resize_keyboard=True)
            )
            
    except Exception as e:
        print(f"❌ Puzzle selection error: {e}")
        await update.message.reply_text("❌ Error processing selection. Please try again.")

async def handle_purchase_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_choice = update.message.text
    
    # 🆕 ANTI-DUPLICATE CHECK
    if 'processing_purchase' in context.user_data and context.user_data['processing_purchase']:
        print(f"🔄 Purchase already processing for user {user_id}, ignoring duplicate click")
        return
    
    if "Confirm" in user_choice:
        try:
            # 🆕 MARK AS PROCESSING TO PREVENT DUPLICATES
            context.user_data['processing_purchase'] = True
            
            purchase_data = context.user_data.get('pending_purchase')
            if not purchase_data:
                await update.message.reply_text("❌ Purchase session expired. Please start over.")
                context.user_data.pop('processing_purchase', None)
                return
            
            # 🆕 DOUBLE-CHECK PIECE IS STILL AVAILABLE
            available_piece, hours_left = get_available_piece(purchase_data['event'], purchase_data['piece'])
            if not available_piece or available_piece["Piece ID"] != purchase_data['piece_id']:
                await update.message.reply_text(
                    "❌ Piece no longer available. Please try another piece.",
                    reply_markup=ReplyKeyboardMarkup([["Back to Main Menu"]], resize_keyboard=True)
                )
                context.user_data.pop('processing_purchase', None)
                context.user_data.pop('pending_purchase', None)
                return
            
            spreadsheet = get_google_sheets()
            users_sheet = spreadsheet.worksheet("users")
            transactions_sheet = spreadsheet.worksheet("transactions")
            
            # Update user balance
            users_data = users_sheet.get_all_records()
            current_balance = 0
            
            for user in users_data:
                if user["User ID"] == user_id:
                    current_balance = user["Balance"]
                    break
            
            new_balance = current_balance - purchase_data['price']
            users_sheet.update_cell(purchase_data['user_row'], 3, new_balance)
            
            # 🆕 MARK PIECE AS SOLD
            mark_piece_sold(purchase_data['piece_id'], user_id)
            
            # Record transaction
            transactions_sheet.append_row([
                user_id,
                "purchase",
                purchase_data['price'],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                f"{purchase_data['event']} - Piece #{purchase_data['piece']} - {purchase_data['piece_id']}"
            ])
            
            # 🆕 ENHANCED DELIVERY MESSAGE WITH INSTRUCTIONS
            delivery_message = f"""
🎉 Purchase Successful!

📦 Puzzle Delivery:
🔗 {purchase_data['puzzle_link']}
🔢 Puzzle code: {purchase_data['puzzle_code']}
⏰ Expires In: {format_time_left(purchase_data['hours_left'])}

📖 How to claim puzzle with link:
https://t.me/puzzlesellsl/927

⚠ Claim before expiration!
📞 Contact @Indrajith00 with your Puzzle Code if any issues.
            """
            
            keyboard = [["Back to Main Menu"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            await update.message.reply_text(delivery_message, reply_markup=reply_markup)
            
            # 🆕 SEND QR CODE IF AVAILABLE
            if purchase_data.get('qr_path'):
                try:
                    with open(purchase_data['qr_path'], 'rb') as qr_file:
                        await update.message.reply_photo(
                            photo=qr_file,
                            caption="📱 Scan QR code to access your puzzle!",
                            reply_markup=reply_markup
                        )
                except FileNotFoundError:
                    await update.message.reply_text(
                        "📱 Use the link above to access your puzzle",
                        reply_markup=reply_markup
                    )
            
            # 🆕 CLEAR ALL PURCHASE DATA
            context.user_data.pop('pending_purchase', None)
            context.user_data.pop('processing_purchase', None)
            
            print(f"✅ Purchase completed for user {user_id}")
            
        except Exception as e:
            print(f"Purchase confirmation error: {e}")
            # 🆕 CLEAN UP ON ERROR TOO
            context.user_data.pop('processing_purchase', None)
            context.user_data.pop('pending_purchase', None)
            await update.message.reply_text("❌ Error processing purchase. Please try again.")
    else:
        # User clicked Cancel
        await update.message.reply_text(
            "❌ Purchase cancelled.",
            reply_markup=ReplyKeyboardMarkup([["Back to Main Menu"]], resize_keyboard=True)
        )
        # 🆕 CLEAR DATA ON CANCEL TOO
        context.user_data.pop('pending_purchase', None)
        context.user_data.pop('processing_purchase', None)

def main():
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("broadcast", admin_broadcast_command))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.Text("🛒 Buy"), buy_command))
    app.add_handler(MessageHandler(filters.Text("💰 Balance"), balance_command))
    app.add_handler(MessageHandler(filters.Text("Back to Main Menu"), back_to_main))
    app.add_handler(MessageHandler(filters.Text("💳 Topup"), topup_command))
    app.add_handler(MessageHandler(filters.Text("🔔 Subscribe To Updates"), subscribe_command))
    app.add_handler(MessageHandler(filters.Text("🔕 Unsubscribe"), unsubscribe_command))  # ✅ ADD THIS LINE
    app.add_handler(MessageHandler(filters.Regex("^(MNT|XPL|ABC|DEF)$"), handle_event_selection))
    app.add_handler(MessageHandler(filters.Regex("^[1-9]$"), handle_puzzle_selection))
    app.add_handler(MessageHandler(filters.Regex(r"^(✅ Confirm Purchase - \$\d+(\.\d+)?|❌ Cancel)$"), handle_purchase_confirmation))
    
    # Start the bot
    print("Bot is starting...")
    app.run_polling()
if __name__ == "__main__":
    main()