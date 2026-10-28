import os
import sys
import logging
import subprocess
import json
import datetime
import uuid
import psutil
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, 
    MessageHandler, CallbackQueryHandler, filters
)

# Logging Setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ================= CONFIGURATION =================
ADMIN_ID = 6661429894  # ⚠️ Apnar Admin Telegram Numeric ID
BOT_TOKEN = "9119463959:AAFGhC4kIBb4fn6GDXz1oDoizT-sFMmNIhY"  # ⚠️ Apnar Main Bot Token

USER_DATA_FILE = "users_data.json"
TOKENS_DATA_FILE = "tokens_data.json"
CONFIG_DATA_FILE = "config_data.json"
SCRIPTS_DIR = "./user_scripts"

os.makedirs(SCRIPTS_DIR, exist_ok=True)

# Memory Management
running_processes = {}     # { user_id: subprocess.Popen }
user_upload_state = {}     # { user_id: {'step': '...', ...} }

# ================= DATA MANAGEMENT =================
def load_data(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def is_admin(user_id):
    return user_id == ADMIN_ID

def check_validity(user_id):
    if is_admin(user_id):
        return True, "Unlimited (Admin)"
    data = load_data(USER_DATA_FILE)
    uid = str(user_id)
    if uid not in data or "expiry" not in data[uid]:
        return False, "No active plan"
    
    try:
        expiry_dt = datetime.datetime.fromisoformat(data[uid]["expiry"])
        if datetime.datetime.now() > expiry_dt:
            return False, "Expired"
        return True, expiry_dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return False, "Invalid Date"

# ================= KEYBOARDS =================
def main_menu_keyboard(user_id):
    keyboard = [
        [KeyboardButton("📁 File Upload"), KeyboardButton("🚀 Start Host")],
        [KeyboardButton("📊 View Hosting"), KeyboardButton("🎧 Support")]
    ]
    if is_admin(user_id):
        keyboard.append([KeyboardButton("⚙️ Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def package_pricing_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📅 1 Day - 20 Tk", callback_data="pkg_select_1")],
        [InlineKeyboardButton("📅 7 Days - 50 Tk", callback_data="pkg_select_7")],
        [InlineKeyboardButton("📅 15 Days - 90 Tk", callback_data="pkg_select_15")],
        [InlineKeyboardButton("📅 30 Days - 150 Tk", callback_data="pkg_select_30")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_gen_token_days_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎟️ 1 Day Token", callback_data="gen_tok_1"),
         InlineKeyboardButton("🎟️ 7 Days Token", callback_data="gen_tok_7")],
        [InlineKeyboardButton("🎟️ 15 Days Token", callback_data="gen_tok_15"),
         InlineKeyboardButton("🎟️ 30 Days Token", callback_data="gen_tok_30")],
        [InlineKeyboardButton("🔙 Back to Admin", callback_data="btn_admin_panel_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ================= HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    text = (
        f"👋 Hello {user_name}!\n\n"
        "Welcome to the **Bot Hosting Panel**.\n"
        "Nicher button gulo bebohar kore apnar bot manage O host korun:"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard(user_id), parse_mode="Markdown")

async def handle_bottom_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # --- 1. FILE UPLOAD ---
    if text == "📁 File Upload":
        if is_admin(user_id):
            user_upload_state[user_id] = {"step": "awaiting_name", "days": 365}
            await update.message.reply_text(
                "👑 **Admin Access Granted!** (No Token/Payment Required)\n\n"
                "📝 **Step 1:** Prothome Bot-er ekta **Nickname / Name** likhe send korun:",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "💳 **Choose Hosting Package**\n\n"
                "Koto diner jonno bot host nite chan paket select korun:\n\n"
                "• 1 Day = **20 Tk**\n"
                "• 7 Days = **50 Tk**\n"
                "• 15 Days = **90 Tk**\n"
                "• 30 Days = **150 Tk**",
                reply_markup=package_pricing_inline_keyboard(),
                parse_mode="Markdown"
            )

    # --- 2. START HOST ---
    elif text == "🚀 Start Host":
        valid, status = check_validity(user_id)
        if not valid:
            await update.message.reply_text(f"⚠️ Permission nei ba plan expired! Status: `{status}`", parse_mode="Markdown")
            return

        user_folder = os.path.join(SCRIPTS_DIR, str(user_id))
        bot_file = os.path.join(user_folder, "bot.py")
        req_file = os.path.join(user_folder, "requirements.txt")
        log_file_path = os.path.join(user_folder, "bot.log")

        if not os.path.exists(bot_file):
            await update.message.reply_text("❌ `bot.py` file paowa jayni! Prothome `📁 File Upload`-e click kore file upload korun.")
            return

        # Stop existing process cleanly if running
        if user_id in running_processes:
            proc = running_processes[user_id]
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

        if os.path.exists(req_file):
            await update.message.reply_text("⚙️ Requirements install kora hocche, ektu somoy din...")
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req_file], check=True)
            except Exception as e:
                await update.message.reply_text(f"⚠️ Requirements install-e somossa: {e}")

        # High-Speed & Log Enabled Execution
        try:
            with open(log_file_path, "w") as log_file:
                process = subprocess.Popen(
                    [sys.executable, "-u", "bot.py"],
                    cwd=user_folder,
                    stdout=log_file,
                    stderr=log_file,
                    stdin=subprocess.DEVNULL
                )
            running_processes[user_id] = process

            await update.message.reply_text(
                f"🚀 **Bot Host Successfully Started!**\n\n"
                f"⚡ **Performance Status:** 100% High Speed (Smooth & Lag-Free)\n"
                f"● **Process ID (PID):** `{process.pid}`\n"
                f"● **Status:** 🟢 Running Smoothly\n"
                f"● **Expiry Date:** `{status}`",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Bot start hote somossa hoyeche: {e}")

    # --- 3. VIEW HOSTING ---
    elif text == "📊 View Hosting":
        data_store = load_data(USER_DATA_FILE)
        u_info = data_store.get(str(user_id), {})
        
        bot_name = u_info.get("bot_name", "Not Set")
        start_date = u_info.get("start_date", "N/A")
        expiry = u_info.get("expiry", "N/A")
        plan_days = u_info.get("plan_days", "N/A")

        remaining_days = "Expired"
        if is_admin(user_id):
            remaining_days = "Unlimited (Admin)"
        elif expiry != "N/A":
            try:
                exp_dt = datetime.datetime.fromisoformat(expiry)
                delta = exp_dt - datetime.datetime.now()
                if delta.days >= 0:
                    remaining_days = f"{delta.days} Days, {delta.seconds // 3600} Hours"
                else:
                    remaining_days = "Expired"
            except Exception:
                remaining_days = "N/A"

        valid, expiry_formatted = check_validity(user_id)

        msg = (
            f"📊 **Hosting Info**\n\n"
            f"🤖 **Bot Name:** `{bot_name}`\n"
            f"⏳ **Package:** `{plan_days} Days`\n"
            f"📅 **Start Date:** `{start_date}`\n"
            f"⌛ **Expiry Date:** `{expiry_formatted}`\n"
            f"🕒 **Remaining Time:** `{remaining_days}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    # --- 4. SUPPORT ---
    elif text == "🎧 Support":
        config = load_data(CONFIG_DATA_FILE)
        supp_username = config.get("support_username", "admin")
        clean_username = supp_username.replace("@", "")

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{clean_username}")
        ]])

        msg = (
            "📞 **Customer Support**\n\n"
            "Token kinar jonno (1, 7, 15, 30 Days) ba kono somossa hole niche button-e tap kore Admin-er inbox-e jogajog korun:"
        )
        await update.message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")

    # --- 5. ADMIN PANEL ---
    elif text == "⚙️ Admin Panel":
        if not is_admin(user_id): return

        admin_kb = [
            [InlineKeyboardButton("🔑 Generate Token", callback_data="admin_gen_token_menu")],
            [InlineKeyboardButton("🎟️ Active Tokens List", callback_data="admin_view_tokens")],
            [InlineKeyboardButton("🎛️ Manage User Bots", callback_data="admin_manage_bots")],
            [InlineKeyboardButton("💬 Set Support Username", callback_data="admin_set_support")]
        ]
        await update.message.reply_text("⚙️ **Welcome to Admin Control Panel**", reply_markup=InlineKeyboardMarkup(admin_kb), parse_mode="Markdown")

    else:
        await handle_text_inputs(update, context)

# ================= TEXT & TOKEN INPUT HANDLER =================
async def handle_text_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state_info = user_upload_state.get(user_id, {})
    current_step = state_info.get("step")

    if not current_step:
        return

    if current_step == "awaiting_token":
        target_days = state_info.get("selected_days")
        tokens_db = load_data(TOKENS_DATA_FILE)

        if text in tokens_db:
            tok_info = tokens_db[text]
            tok_status = tok_info.get("status")
            tok_days = tok_info.get("days")

            if tok_status != "active":
                await update.message.reply_text("❌ **Ei Token-ti already bebohar kora hoye geche!** Notun bot host korar jonno notun token din.")
                return

            if tok_days != target_days:
                await update.message.reply_text(
                    f"⚠️ **Invalid Plan Token!**\n"
                    f"Apni select korchen **{target_days} Days**, kintu token-ti **{tok_days} Days** er.\n"
                    f"Anugraho kore Sothik **{target_days} Days** er token-ti paste korun:"
                )
                return

            tokens_db[text]["status"] = "used"
            tokens_db[text]["used_by"] = user_id
            save_data(TOKENS_DATA_FILE, tokens_db)

            user_upload_state[user_id]["step"] = "awaiting_name"
            user_upload_state[user_id]["days"] = target_days

            await update.message.reply_text(
                f"✅ **{target_days} Days Token Verified Successfully!**\n\n"
                "📝 **Step 1:** Ebar apnar Bot-er ekta **Nickname / Name** likhe send korun:",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ **Invalid Token!** Admin-er sathe jogajog kore sothik token collect korun.")

    elif current_step == "awaiting_name":
        user_upload_state[user_id]["bot_name"] = text
        user_upload_state[user_id]["step"] = "awaiting_bot_file"

        await update.message.reply_text(
            f"✅ Bot Nickname: **{text}**\n\n"
            "📝 **Step 2:** Ebar apnar `bot.py` file-ti upload/send korun.",
            parse_mode="Markdown"
        )

    elif current_step == "awaiting_support_username":
        if not is_admin(user_id): return
        config = load_data(CONFIG_DATA_FILE)
        config["support_username"] = text.replace("@", "")
        save_data(CONFIG_DATA_FILE, config)

        user_upload_state.pop(user_id, None)
        await update.message.reply_text(f"✅ Support username updated: `@{text.replace('@', '')}`", parse_mode="Markdown")

# ================= INLINE CALLBACK HANDLERS =================
async def inline_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("pkg_select_"):
        days = int(data.split("_")[2])
        user_upload_state[user_id] = {
            "step": "awaiting_token",
            "selected_days": days
        }

        await query.edit_message_text(
            f"🔑 **{days} Days Package Selected!**\n\n"
            f"Anugraho kore Admin-er theke collect kora **{days} Days Token**-ti ekhane paste/send korun:",
            parse_mode="Markdown"
        )

    elif data == "admin_gen_token_menu":
        if not is_admin(user_id): return
        await query.edit_message_text(
            "🎟️ **Token Duration Selection**\n\nKoto diner validity-r token generate korte chan select korun:",
            reply_markup=admin_gen_token_days_keyboard(),
            parse_mode="Markdown"
        )

    elif data.startswith("gen_tok_"):
        if not is_admin(user_id): return
        days = int(data.split("_")[2])
        
        new_token = f"TOK-{days}D-{uuid.uuid4().hex[:6].upper()}"
        tokens_db = load_data(TOKENS_DATA_FILE)
        tokens_db[new_token] = {
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "days": days,
            "status": "active",
            "used_by": None
        }
        save_data(TOKENS_DATA_FILE, tokens_db)

        await query.edit_message_text(
            f"✅ **{days} Days Token Generated!**\n\n"
            f"🔑 Token: `{new_token}`\n\n"
            f"Ei token-ti **{days} Days Package** er jonno work korbe.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Token Menu", callback_data="admin_gen_token_menu")]]),
            parse_mode="Markdown"
        )

    elif data == "admin_view_tokens":
        if not is_admin(user_id): return
        tokens_db = load_data(TOKENS_DATA_FILE)
        
        if not tokens_db:
            msg = "🎟️ Kono token paowa jayni."
        else:
            msg = "🎟️ **Tokens List:**\n\n"
            for tok, info in list(tokens_db.items())[-12:]:
                st = "🟢 Active" if info["status"] == "active" else f"🔴 Used"
                d_str = f"{info.get('days', '?')} Days"
                msg += f"• `{tok}` ({d_str}) | {st}\n"

        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="btn_admin_panel_back")]]),
            parse_mode="Markdown"
        )

    elif data == "admin_set_support":
        if not is_admin(user_id): return
        user_upload_state[user_id] = {"step": "awaiting_support_username"}
        await query.edit_message_text("💬 Admin Support Telegram Username-ti send korun (e.g. `your_username`):")

    elif data == "btn_admin_panel_back":
        if not is_admin(user_id): return
        admin_kb = [
            [InlineKeyboardButton("🔑 Generate Token", callback_data="admin_gen_token_menu")],
            [InlineKeyboardButton("🎟️ Active Tokens List", callback_data="admin_view_tokens")],
            [InlineKeyboardButton("🎛️ Manage User Bots", callback_data="admin_manage_bots")],
            [InlineKeyboardButton("💬 Set Support Username", callback_data="admin_set_support")]
        ]
        await query.edit_message_text("⚙️ **Welcome to Admin Control Panel**", reply_markup=InlineKeyboardMarkup(admin_kb), parse_mode="Markdown")

    elif data == "admin_manage_bots":
        if not is_admin(user_id): return
        data_store = load_data(USER_DATA_FILE)
        
        if not data_store:
            await query.edit_message_text("❌ Kono registered user bot paowa jayni.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_admin_panel_back")]]))
            return

        msg = "🎛️ **User Bots Comprehensive Status:**\n\n"
        kb = []

        for uid, info in data_store.items():
            proc = running_processes.get(int(uid))
            is_running = proc and proc.poll() is None
            status_icon = "🟢 ON" if is_running else "🔴 OFF"

            if is_running:
                try:
                    p = psutil.Process(proc.pid)
                    cpu = f"{p.cpu_percent(interval=0.01)}%"
                    mem = f"{p.memory_info().rss / (1024 * 1024):.1f}MB"
                except Exception:
                    cpu, mem = "N/A", "N/A"
            else:
                cpu, mem = "0%", "0MB"

            uname = info.get("username", "Unknown")
            b_name = info.get("bot_name", "No Name")
            pkg = info.get("plan_days", "N/A")
            s_date = info.get("start_date", "N/A")
            e_date = info.get("expiry", "N/A")

            msg += (
                f"👤 **User:** @{uname} (`{uid}`)\n"
                f"🤖 **Bot Name:** `{b_name}`\n"
                f"📦 **Pkg:** `{pkg} Days` | 🚀 **CPU:** `{cpu}` | 📊 **RAM:** `{mem}`\n"
                f"📅 **Start:** `{s_date}`\n"
                f"⌛ **Expiry:** `{e_date}`\n"
                "-----------------------------------\n"
            )

            kb.append([InlineKeyboardButton(f"{b_name} ({uid}) [{status_icon}]", callback_data=f"toggle_bot_{uid}")])

        kb.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="btn_admin_panel_back")])
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("toggle_bot_"):
        if not is_admin(user_id): return
        target_uid = int(data.split("_")[2])
        proc = running_processes.get(target_uid)

        user_folder = os.path.join(SCRIPTS_DIR, str(target_uid))
        bot_file = os.path.join(user_folder, "bot.py")
        log_file_path = os.path.join(user_folder, "bot.log")

        if proc and proc.poll() is None:
            # Turn OFF
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            if target_uid in running_processes:
                del running_processes[target_uid]
            await query.answer("🔴 Bot Stopped Successfully!", show_alert=False)
        else:
            # Turn ON
            if os.path.exists(bot_file):
                try:
                    with open(log_file_path, "w") as log_file:
                        new_proc = subprocess.Popen(
                            [sys.executable, "-u", "bot.py"], 
                            cwd=user_folder, 
                            stdout=log_file, 
                            stderr=log_file,
                            stdin=subprocess.DEVNULL
                        )
                    running_processes[target_uid] = new_proc
                    await query.answer("🟢 Bot Started Successfully!", show_alert=False)
                except Exception as e:
                    await query.answer(f"❌ Error: {e}", show_alert=True)
            else:
                await query.answer("❌ User file missing!", show_alert=True)
        
        # Refresh the management menu dynamically
        data_store = load_data(USER_DATA_FILE)
        msg = "🎛️ **User Bots Comprehensive Status:**\n\n"
        kb = []

        for uid, info in data_store.items():
            p_check = running_processes.get(int(uid))
            running_status = p_check and p_check.poll() is None
            status_icon = "🟢 ON" if running_status else "🔴 OFF"

            if running_status:
                try:
                    p = psutil.Process(p_check.pid)
                    cpu = f"{p.cpu_percent(interval=0.01)}%"
                    mem = f"{p.memory_info().rss / (1024 * 1024):.1f}MB"
                except Exception:
                    cpu, mem = "N/A", "N/A"
            else:
                cpu, mem = "0%", "0MB"

            uname = info.get("username", "Unknown")
            b_name = info.get("bot_name", "No Name")
            pkg = info.get("plan_days", "N/A")
            s_date = info.get("start_date", "N/A")
            e_date = info.get("expiry", "N/A")

            msg += (
                f"👤 **User:** @{uname} (`{uid}`)\n"
                f"🤖 **Bot Name:** `{b_name}`\n"
                f"📦 **Pkg:** `{pkg} Days` | 🚀 **CPU:** `{cpu}` | 📊 **RAM:** `{mem}`\n"
                f"📅 **Start:** `{s_date}`\n"
                f"⌛ **Expiry:** `{e_date}`\n"
                "-----------------------------------\n"
            )

            kb.append([InlineKeyboardButton(f"{b_name} ({uid}) [{status_icon}]", callback_data=f"toggle_bot_{uid}")])

        kb.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="btn_admin_panel_back")])
        try:
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        except Exception:
            pass

# ================= DOCUMENT UPLOAD HANDLING =================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state_info = user_upload_state.get(user_id, {})
    current_step = state_info.get("step")

    if not current_step:
        await update.message.reply_text("⚠️ Prothome bottom keyboard theke `📁 File Upload`-e tap korun.")
        return

    document = update.message.document
    file_name = document.file_name.lower()

    user_folder = os.path.join(SCRIPTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    file = await context.bot.get_file(document.file_id)

    if current_step == "awaiting_bot_file" or file_name.endswith(".py"):
        save_path = os.path.join(user_folder, "bot.py")
        await file.download_to_drive(custom_path=save_path)
        
        user_upload_state[user_id]["step"] = "awaiting_req_file"
        await update.message.reply_text(
            "✅ `bot.py` file successfully uploaded!\n\n"
            "📝 **Step 3:** Ebar apnar `requirements.txt` file-ti send/upload korun.",
            parse_mode="Markdown"
        )

    elif current_step == "awaiting_req_file" or "requirement" in file_name:
        save_path = os.path.join(user_folder, "requirements.txt")
        await file.download_to_drive(custom_path=save_path)

        bot_name = state_info.get("bot_name", "My Bot")
        days = state_info.get("days", 365 if is_admin(user_id) else 30)

        now = datetime.datetime.now()
        expiry_dt = now + datetime.timedelta(days=days)

        data_store = load_data(USER_DATA_FILE)
        uid_str = str(user_id)
        
        if uid_str not in data_store:
            data_store[uid_str] = {}

        data_store[uid_str]["username"] = update.effective_user.username or "No Username"
        data_store[uid_str]["bot_name"] = bot_name
        data_store[uid_str]["plan_days"] = "Unlimited" if is_admin(user_id) else days
        data_store[uid_str]["start_date"] = now.strftime("%Y-%m-%d %H:%M")
        data_store[uid_str]["expiry"] = "Unlimited" if is_admin(user_id) else expiry_dt.isoformat()
        save_data(USER_DATA_FILE, data_store)

        user_upload_state.pop(user_id, None)

        exp_str = "Unlimited (Admin)" if is_admin(user_id) else expiry_dt.strftime('%Y-%m-%d %H:%M')

        await update.message.reply_text(
            f"🎉 **Setup Complete!** 🎉\n\n"
            f"● **Bot Name:** `{bot_name}`\n"
            f"● **Package Duration:** `{'Unlimited' if is_admin(user_id) else f'{days} Days'}`\n"
            f"● **Expiry Date:** `{exp_str}`\n\n"
            f"Ebar '🚀 Start Host' button-e click kore bot host kora shuru korun!",
            reply_markup=main_menu_keyboard(user_id),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("⚠️ Sothik file (`bot.py` / `requirements.txt`) upload korun.")

# ================= MAIN FUNCTION =================
if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(inline_callback_handler))
    
    application.add_handler(MessageHandler(filters.Regex('^(📁 File Upload|🚀 Start Host|📊 View Hosting|🎧 Support|⚙️ Admin Panel)$'), handle_bottom_buttons))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_inputs))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Main Host Bot is Running Smoothly...")
    application.run_polling()
