import os
import telegram
import logging
import threading # Para ejecutar la sincronización en un hilo separado

# Importar las clases necesarias de telegram.ext
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Configurar logging para ver errores del bot y mensajes informativos
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Variables Globales para el Bot ---
# Obtener TOKEN y CHAT_ID del entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Instancia del bot de Telegram (se inicializa una vez)
bot = None
if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        logger.info("Bot de Telegram inicializado correctamente.")
    except Exception as e:
        logger.error(f"Error al inicializar el bot de Telegram con el token proporcionado: {e}")
        bot = None # Asegurarse de que bot es None si falla la inicialización
else:
    logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados. Las notificaciones y comandos del bot no funcionarán.")

# Variable global para almacenar la función de sincronización (callback)
sync_function_callback = None

# --- Funciones de Utilidad para enviar mensajes ---
def send_telegram(message: str) -> None:
    """
    Envía un mensaje a un chat de Telegram.
    Utiliza la instancia global 'bot' para la comunicación.
    """
    if bot and TELEGRAM_CHAT_ID:
        try:
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')
            logger.info(f"Mensaje de Telegram enviado: {message[:50]}...") # Loguea los primeros 50 caracteres
        except telegram.error.Unauthorized:
            logger.error("Error de Telegram: Token del bot inválido o no autorizado. Verifica TELEGRAM_BOT_TOKEN.")
        except telegram.error.BadRequest as e:
            logger.error(f"Error de Telegram (BadRequest): {e}. Posiblemente CHAT_ID incorrecto o formato de mensaje inválido.")
        except Exception as e:
            logger.error(f"Error desconocido al enviar mensaje a Telegram: {e}")
    else:
        logger.warning("Bot de Telegram no inicializado o CHAT_ID no configurado. No se pudo enviar el mensaje.")

# --- Funciones Handler para Comandos del Bot ---

def start_command(update, context):
    """
    Maneja el comando /start o /help en Telegram.
    Envía un mensaje de bienvenida y ayuda al usuario.
    """
    chat_id = update.message.chat_id
    user = update.message.from_user

    # Solo responde si el chat_id coincide con el configurado para mayor seguridad
    if str(chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para usar este bot.")
        logger.warning(f"Intento de comando /start no autorizado desde chat_id: {chat_id}, usuario: {user.username}")
        return

    welcome_message = (
        "Hello there! 👋 I'm your Raspberry Pi Data Sync Bot. 🤖\n\n"
        "Here are the commands you can use:\n"
        "  `/sync` - Triggers a *manual data synchronization* from your Raspberry Pi. 🚀\n\n"
        "Please ensure your Raspberry Pi is powered on and accessible. 📡\n"
        "You'll receive notifications for every sync! ✨"
    )
    
    update.message.reply_text(welcome_message, parse_mode='Markdown')
    logger.info(f"Comando /start o /help recibido de {user.username} (ID: {chat_id}). Mensaje de ayuda enviado.")


def start_sync_command(update, context):
    """
    Maneja el comando /sync para iniciar la sincronización de datos.
    """
    chat_id = update.message.chat_id
    user = update.message.from_user

    # Solo permite la ejecución si el chat_id coincide con el configurado
    if str(chat_id) != TELEGRAM_CHAT_ID:
        update.message.reply_text("Lo siento, no estás autorizado para ejecutar este comando.")
        logger.warning(f"Intento de comando /sync no autorizado desde chat_id: {chat_id}, usuario: {user.username}")
        return

    update.message.reply_text("¡Comando `/sync` recibido! Iniciando la sincronización de datos ahora... 🚀")
    logger.info(f"Comando /sync recibido de {user.username} (ID: {chat_id}). Disparando sincronización.")

    # Llama a la función de sincronización (perform_sync de main.py)
    # Ejecuta en un hilo separado para no bloquear el bot de Telegram
    if sync_function_callback:
        sync_thread = threading.Thread(target=sync_function_callback, args=("from",))
        sync_thread.start()
    else:
        update.message.reply_text("Error interno: La función de sincronización no está configurada.")
        logger.error("sync_function_callback no configurada en telegram_utils. Esto es un error de programación.")

def error_handler(update, context):
    """
    Registra los errores causados por Updates.
    """
    logger.warning(f'Update "{update}" causó error "{context.error}"')

# --- Función para iniciar el Listener del Bot ---
def start_telegram_bot_listener(sync_func):
    """
    Inicializa y arranca el bot de Telegram para escuchar comandos.
    Recibe la función de sincronización como callback.
    """
    global sync_function_callback
    sync_function_callback = sync_func # Asigna la función de sincronización pasada desde main.py

    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN no está configurado. No se puede iniciar el listener del bot.")
        return

    if not bot: # Si el bot no se inicializó correctamente antes, no podemos continuar.
        logger.error("La instancia del bot de Telegram no está disponible. No se puede iniciar el listener.")
        return

    try:
        # Updater gestiona las actualizaciones del bot
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
        # Dispatcher es el que distribuye las actualizaciones a los handlers
        dispatcher = updater.dispatcher

        # Añadir manejadores para los comandos
        dispatcher.add_handler(CommandHandler("start", start_command))
        dispatcher.add_handler(CommandHandler("help", start_command))
        dispatcher.add_handler(CommandHandler("sync", start_sync_command))

        # Añadir manejador de errores
        dispatcher.add_error_handler(error_handler)

        # Iniciar el bot. start_polling() ejecuta la escucha en un hilo separado,
        # lo que permite que el proceso principal de Python (main.py) continúe.
        updater.start_polling()
        logger.info("Bot de Telegram: Listener iniciado y en modo polling.")
        # Nota: No llamar a updater.idle() aquí, ya que bloquearía el main.py.
        # main.py ya tiene su propio mecanismo para mantenerse vivo (time.sleep).

    except Exception as e:
        logger.error(f"Fallo crítico al iniciar el listener del bot de Telegram: {e}")