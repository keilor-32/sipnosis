import os
import logging
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --- Configuración ---
TOKEN = os.getenv("TOKEN")
APP_URL = os.getenv("APP_URL")
PORT = int(os.getenv("PORT", "8080"))

if not TOKEN or not APP_URL:
    raise ValueError("❌ ERROR: Faltan variables de entorno (TOKEN o APP_URL).")

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Variables en memoria ---
known_chats = set()

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mensaje de bienvenida y explicación de uso."""
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot de sinopsis.\n\n"
        "Envíame una imagen y escribe la sinopsis en la 'descripción' (caption). "
        "Yo me encargaré de formatearla y enviarla a todos los canales y grupos registrados."
    )

async def detectar_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta y registra automáticamente grupos y canales nuevos."""
    chat = update.effective_chat
    
    # Detección de grupos
    if chat.type in ["group", "supergroup"]:
        if chat.id not in known_chats:
            known_chats.add(chat.id)
            logger.info(f"Grupo registrado: {chat.id}")
            await update.message.reply_text(f"✅ ¡Grupo registrado para envíos! ID: `{chat.id}`", parse_mode="Markdown")
            
    # Detección de canales (cuando el bot es admin y se publica algo)
    elif update.channel_post:
        channel_id = update.channel_post.chat.id
        if channel_id not in known_chats:
            known_chats.add(channel_id)
            logger.info(f"Canal registrado: {channel_id}")
            await context.bot.send_message(
                chat_id=channel_id,
                text=f"✅ ¡Canal registrado exitosamente! ID: `{channel_id}`",
                parse_mode="Markdown"
            )

async def recibir_foto_y_sinopsis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la foto con texto del administrador y la distribuye."""
    msg = update.message
    
    if msg.photo and msg.caption:
        photo_id = msg.photo[-1].file_id
        caption = msg.caption
        
        if not known_chats:
            await msg.reply_text("⚠️ Aún no hay grupos o canales registrados. Agrega el bot a un canal/grupo primero.")
            return

        enviados = 0
        for chat_id in known_chats:
            try:
                # Envía la foto con la sinopsis tal cual se recibió
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=caption,
                    parse_mode="Markdown"
                )
                enviados += 1
            except Exception as e:
                logger.warning(f"No se pudo enviar al chat {chat_id}: {e}")

        await msg.reply_text(f"✅ Sinopsis enviada exitosamente a {enviados} canal(es)/grupo(s).")
    else:
        await msg.reply_text("❌ Por favor, asegúrate de enviar una **imagen** y de incluir la **sinopsis** en la descripción de la foto.")

# --- WEBHOOK aiohttp ---
async def webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, app_telegram.bot)
    await app_telegram.update_queue.put(update)
    return web.Response(text="OK")

async def on_startup(app):
    webhook_url = f"{APP_URL}/webhook"
    await app_telegram.bot.set_webhook(webhook_url)
    logger.info(f"Webhook configurado en {webhook_url}")

async def on_shutdown(app):
    await app_telegram.bot.delete_webhook()
    logger.info("Webhook eliminado")

# --- App Telegram e Inicialización ---
app_telegram = Application.builder().token(TOKEN).build()

# Agregar los manejadores de comandos y mensajes
app_telegram.add_handler(CommandHandler("start", start))
app_telegram.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, recibir_foto_y_sinopsis))
app_telegram.add_handler(MessageHandler(filters.ALL & (filters.ChatType.GROUPS | filters.ChatType.CHANNEL), detectar_chat))

# Configuración del servidor web
web_app = web.Application()
web_app.router.add_post("/webhook", webhook_handler)
web_app.router.add_get("/ping", lambda request: web.Response(text="✅ Bot de sinopsis activo."))
web_app.on_startup.append(on_startup)
web_app.on_shutdown.append(on_shutdown)

async def main():
    logger.info("🤖 Bot de sinopsis iniciado...")
    
    await app_telegram.initialize()
    await app_telegram.start()

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Webhook corriendo en el puerto {PORT}")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Deteniendo bot...")
    finally:
        await app_telegram.stop()
        await app_telegram.shutdown()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
