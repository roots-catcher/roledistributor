import os
import logging
import sqlite3
import re
from telegram import (
    Update,
    Bot,
    ParseMode,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)
from telegram.utils.helpers import mention_html

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получение токена бота из переменной окружения
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Определение состояний для ConversationHandler
(
    SETROLE_CHOOSE_OPTION,
    SETROLE_ENTER_ROLE_NAME,
    SETROLE_SELECT_USER,
    DELETEROLE_SELECT_USER,
    DELETEROLE_SELECT_ROLE,
    TAGROLE_CHOOSE_ROLE,
    GETROLE_ENTER_USERNAME,
    REMOVEROLE_CHOOSE_ROLE,
    ASSIGNROLE_CHOOSE_ROLE,
    ASSIGNROLE_CONFIRM,
) = range(10)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('db/roles.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS roles
                 (username TEXT, role TEXT)''')
    c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_username_role
                 ON roles (username, LOWER(role))''')  # Индекс теперь на LOWER(role)
    conn.commit()
    conn.close()

# Команда /start
def start_command(update: Update, context: CallbackContext):
    user = update.message.from_user
    welcome_text = f"Привет, {user.first_name}! Я бот для управления ролями в группе."

    keyboard = [
        ['/help', '/roles'],
        ['/setrole', '/getrole'],
        ['/deleterole', '/tagrole'],
        ['/removerole', '/assignrole'] 
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    sent_message = update.message.reply_text(welcome_text, reply_markup=reply_markup)

    # Удаляем сообщение пользователя с командой
    try:
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
    except:
        pass

# Команда /help
def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Я бот для управления ролями в группе.\n\n"
        "Доступные команды:\n"
        "/setrole - Назначить роль пользователю.\n"
        "/getrole - Получить роли пользователя.\n"
        "/deleterole - Удалить роль у пользователя.\n"
        "/removerole - Удалить роль из системы.\n"
        "/assignrole - Самостоятельно добавить себе роль.\n"
        "/roles - Показать все роли и участников.\n"
        "/tagrole - Упомянуть участников роли.\n"
        "/help - Показать это сообщение.\n\n"
        "Вы также можете использовать `@<роль>` в вашем сообщении, чтобы упомянуть всех участников этой роли.\n"
        "Например: `@dev Привет, команда!`"
    )

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    update.message.reply_text(help_text)

    # Удаляем сообщение пользователя с командой
    try:
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
    except:
        pass

# Команда /roles
def list_roles(update: Update, context: CallbackContext):
    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    try:
        conn = sqlite3.connect('db/roles.db')
        c = conn.cursor()
        c.execute("SELECT role FROM roles GROUP BY role")
        roles = c.fetchall()

        if roles:
            message = 'Список ролей и участников:\n'
            for role_tuple in roles:
                role = role_tuple[0]
                c.execute("SELECT username FROM roles WHERE role = ?", (role,))
                users = c.fetchall()
                user_mentions = [f'@{username[0]}' for username in users]
                user_list = ', '.join(user_mentions)
                message += f'- {role} ({len(user_mentions)}): {user_list}\n'
            conn.close()
            update.message.reply_text(message)
        else:
            update.message.reply_text('Пока нет назначенных ролей.')
    except Exception as e:
        logging.error(f"Exception in list_roles: {e}", exc_info=True)
        update.message.reply_text('Произошла ошибка при получении списка ролей.')

    # Удаляем сообщение пользователя с командой
    try:
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
    except:
        pass

# Команда /setrole
def setrole_start(update: Update, context: CallbackContext):
    # Автоматическая отмена предыдущего диалога
    context.user_data.clear()

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    user = update.message.from_user
    chat = update.effective_chat

    # Проверяем, является ли пользователь администратором
    try:
        member = context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator']:
            update.message.reply_text('Только администратор может назначать роли.')
            # Удаляем сообщение пользователя с командой
            try:
                context.bot.delete_message(chat_id=chat.id, message_id=context.user_data['user_command_message_id'])
            except:
                pass
            return ConversationHandler.END
    except:
        update.message.reply_text('Не удалось проверить ваши права. Попробуйте позже.')
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

    # Предлагаем выбрать существующую роль или создать новую
    keyboard = [
        [InlineKeyboardButton('Выбрать существующую роль', callback_data='setrole_existing')],
        [InlineKeyboardButton('Создать новую роль', callback_data='setrole_new')],
        [InlineKeyboardButton('Отмена', callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent_message = update.message.reply_text('Выберите опцию:', reply_markup=reply_markup)
    context.user_data['message_to_delete'] = sent_message.message_id

    return SETROLE_CHOOSE_OPTION

def setrole_option_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'cancel':
        try:
            query.message.delete()
        except:
            pass
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=query.message.chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

    context.user_data['setrole'] = {}

    if data == 'setrole_existing':
        # Предлагаем выбрать существующую роль
        conn = sqlite3.connect('db/roles.db')
        c = conn.cursor()
        c.execute("SELECT DISTINCT role FROM roles")
        results = c.fetchall()
        conn.close()

        if results:
            keyboard = []
            for role_tuple in results:
                role = role_tuple[0]
                keyboard.append([InlineKeyboardButton(role, callback_data=f'setrole_role:{role}')])
            keyboard.append([InlineKeyboardButton('Назад', callback_data='back')])

            reply_markup = InlineKeyboardMarkup(keyboard)
            query.edit_message_text('Выберите роль:', reply_markup=reply_markup)
            return SETROLE_CHOOSE_OPTION
        else:
            query.edit_message_text('Пока нет доступных ролей.')
            return ConversationHandler.END
    elif data == 'setrole_new':
        # Запрашиваем название новой роли
        query.edit_message_text('Пожалуйста, введите название новой роли:')
        return SETROLE_ENTER_ROLE_NAME
    elif data.startswith('setrole_role:'):
        role = data.split(':', 1)[1]
        context.user_data['setrole']['role'] = role
        query.edit_message_text(f'Вы выбрали роль "{role}". Теперь введите @username пользователей через пробел для назначения роли:')
        return SETROLE_SELECT_USER
    elif data == 'back':
        # Возвращаемся к выбору опции
        try:
            query.message.delete()
        except:
            pass
        return setrole_start(update, context)
    else:
        query.message.reply_text('Неизвестная команда.')
        return ConversationHandler.END

def setrole_new_role_name(update: Update, context: CallbackContext):
    role_name = update.message.text.strip()
    if not role_name:
        update.message.reply_text('Название роли не может быть пустым. Попробуйте снова или нажмите /cancel для отмены.')
        return SETROLE_ENTER_ROLE_NAME

    context.user_data['setrole']['role'] = role_name
    sent_message = update.message.reply_text(f'Роль "{role_name}" создана. Теперь введите @username пользователей через пробел для назначения роли:')
    context.user_data['message_to_delete'] = sent_message.message_id
    return SETROLE_SELECT_USER

def setrole_select_user(update: Update, context: CallbackContext):
    role = context.user_data['setrole'].get('role')
    if not role:
        update.message.reply_text('Произошла ошибка. Роль не найдена.')
        return ConversationHandler.END

    usernames = update.message.text.strip().split()
    if not usernames:
        update.message.reply_text('Пожалуйста, укажите @username пользователей через пробел или нажмите /cancel для отмены.')
        return SETROLE_SELECT_USER

    success_users = []
    failed_users = []

    for username in usernames:
        if username.startswith('@'):
            username = username[1:]
        if username:
            conn = sqlite3.connect('db/roles.db')
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO roles (username, role) VALUES (?, ?)", (username.lower(), role))
            conn.commit()
            conn.close()
            success_users.append(f'@{username}')
        else:
            failed_users.append(username)

    message = ''
    if success_users:
        message += f'Роль "{role}" назначена пользователям: {" ".join(success_users)}.\n'
    if failed_users:
        message += f'Не удалось назначить роль пользователям: {" ".join(failed_users)}.\n'

    update.message.reply_text(message)

    # Удаляем системные сообщения бота
    try:
        if 'message_to_delete' in context.user_data:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['message_to_delete'])
    except:
        pass

    # Удаляем сообщения пользователя с командой и вводом
    try:
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except:
        pass

    return ConversationHandler.END

# Команда /getrole
def getrole_start(update: Update, context: CallbackContext):
    # Автоматическая отмена предыдущего диалога
    context.user_data.clear()

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    sent_message = update.message.reply_text('Пожалуйста, введите @username пользователя для получения его ролей:')
    context.user_data['message_to_delete'] = sent_message.message_id
    return GETROLE_ENTER_USERNAME

def getrole_enter_username(update: Update, context: CallbackContext):
    username = update.message.text.strip()
    if username.startswith('@'):
        username = username[1:]

    conn = sqlite3.connect('db/roles.db')
    c = conn.cursor()
    c.execute("SELECT role FROM roles WHERE username = ?", (username.lower(),))
    results = c.fetchall()
    conn.close()

    if results:
        roles = ', '.join([row[0] for row in results])
        update.message.reply_text(f'Роли пользователя @{username}: {roles}')
    else:
        update.message.reply_text(f'У пользователя @{username} нет назначенных ролей.')

    # Удаляем сообщения пользователя с командой и вводом
    try:
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
    except:
        pass

    # Удаляем системные сообщения бота
    try:
        if 'message_to_delete' in context.user_data:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['message_to_delete'])
    except:
        pass

    return ConversationHandler.END

# Команда /deleterole
def deleterole_start(update: Update, context: CallbackContext):
    # Автоматическая отмена предыдущего диалога
    context.user_data.clear()

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    user = update.message.from_user
    chat = update.effective_chat

    # Проверяем, является ли пользователь администратором
    try:
        member = context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator']:
            update.message.reply_text('Только администратор может удалять роли.')
            # Удаляем сообщение пользователя с командой
            try:
                context.bot.delete_message(chat_id=chat.id, message_id=context.user_data['user_command_message_id'])
            except:
                pass
            return ConversationHandler.END
    except:
        update.message.reply_text('Не удалось проверить ваши права. Попробуйте позже.')
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

    sent_message = update.message.reply_text('Пожалуйста, введите @username пользователей через пробел, у которых вы хотите удалить роль:')
    context.user_data['message_to_delete'] = sent_message.message_id
    return DELETEROLE_SELECT_USER

def deleterole_select_user(update: Update, context: CallbackContext):
    usernames = update.message.text.strip().split()
    if not usernames:
        update.message.reply_text('Пожалуйста, укажите @username пользователей через пробел или нажмите /cancel для отмены.')
        return DELETEROLE_SELECT_USER

    context.user_data['deleterole'] = {'usernames': usernames}

    # Предлагаем выбрать роль для удаления
    conn = sqlite3.connect('db/roles.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT role FROM roles")
    results = c.fetchall()
    conn.close()

    if results:
        keyboard = []
        for role_tuple in results:
            role = role_tuple[0]
            keyboard.append([InlineKeyboardButton(role, callback_data=f'deleterole_role:{role}')])
        keyboard.append([InlineKeyboardButton('Назад', callback_data='back')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_message = update.message.reply_text('Выберите роль для удаления у указанных пользователей:', reply_markup=reply_markup)
        context.user_data['message_to_delete'] = sent_message.message_id
        return DELETEROLE_SELECT_ROLE
    else:
        update.message.reply_text('Пока нет доступных ролей.')
        return ConversationHandler.END

def deleterole_role_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'back':
        try:
            query.message.delete()
        except:
            pass
        return deleterole_start(update, context)

    if data.startswith('deleterole_role:'):
        role = data.split(':', 1)[1]

        usernames = context.user_data['deleterole'].get('usernames')
        if not usernames:
            query.edit_message_text('Произошла ошибка. Пользователи не найдены.')
            return ConversationHandler.END

        success_users = []
        failed_users = []

        for username in usernames:
            if username.startswith('@'):
                username = username[1:]
            if username:
                conn = sqlite3.connect('db/roles.db')
                c = conn.cursor()
                c.execute("DELETE FROM roles WHERE username = ? AND role = ?", (username.lower(), role))
                conn.commit()
                conn.close()
                success_users.append(f'@{username}')
            else:
                failed_users.append(username)

        message = ''
        if success_users:
            message += f'Роль "{role}" удалена у пользователей: {" ".join(success_users)}.\n'
        if failed_users:
            message += f'Не удалось удалить роль у пользователей: {" ".join(failed_users)}.\n'

        query.edit_message_text(message)

        # Удаляем системные сообщения бота
        try:
            if 'message_to_delete' in context.user_data:
                context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['message_to_delete'])
        except:
            pass

        # Удаляем сообщения пользователя с командой и вводом
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.callback_query.message.message_id)
        except:
            pass

        return ConversationHandler.END
    else:
        query.message.reply_text('Неизвестная команда.')
        return ConversationHandler.END

# Команда /tagrole
def tagrole_start(update: Update, context: CallbackContext):
    # Автоматическая отмена предыдущего диалога
    context.user_data.clear()

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    conn = sqlite3.connect('db/roles.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT role FROM roles")
    results = c.fetchall()
    conn.close()

    if results:
        keyboard = []
        for role_tuple in results:
            role = role_tuple[0]
            keyboard.append([InlineKeyboardButton(role, callback_data=f'tagrole_role:{role}')])
        keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_message = update.message.reply_text('Выберите роль для тегирования:', reply_markup=reply_markup)
        context.user_data['message_to_delete'] = sent_message.message_id
        return TAGROLE_CHOOSE_ROLE
    else:
        update.message.reply_text('Пока нет доступных ролей.')
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

def tagrole_choose_role(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'cancel':
        try:
            query.message.delete()
        except:
            pass
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

    if data.startswith('tagrole_role:'):
        role = data.split(':', 1)[1]
        context.user_data['tagrole'] = {'role': role}

        # Удаляем сообщение с выбором роли
        try:
            query.message.delete()
            if 'message_to_delete' in context.user_data:
                context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['message_to_delete'])
        except:
            pass

        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass

        # Получаем список пользователей с данной ролью
        conn = sqlite3.connect('db/roles.db')
        c = conn.cursor()
        c.execute("SELECT DISTINCT username FROM roles WHERE role = ?", (role,))
        users = c.fetchall()
        conn.close()

        if users:
            mentions = [f'@{username_tuple[0]}' for username_tuple in users]
            # Убираем дубликаты
            unique_mentions = list(set(mentions))
            mentions_text = ' '.join(unique_mentions)

            # Отправляем сообщение с упоминаниями
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f'Участники роли "{role}":\n{mentions_text}',
                parse_mode=ParseMode.HTML
            )
        else:
            context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f'Нет участников с ролью "{role}".'
            )

        return ConversationHandler.END
    else:
        query.message.reply_text('Неизвестная команда.')
        return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text('Операция отменена.')

    # Удаляем системные сообщения бота
    try:
        if 'message_to_delete' in context.user_data:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['message_to_delete'])
    except:
        pass

    # Удаляем сообщение пользователя с командой
    try:
        if 'user_command_message_id' in context.user_data:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
    except:
        pass

    # Очищаем данные пользователя
    context.user_data.clear()

    return ConversationHandler.END

# Обработчик сообщений для замены @<роль> на упоминания участников роли
def role_mention_handler(update: Update, context: CallbackContext):
    message = update.message
    text = message.text

    # Ищем шаблон @<роль>, регистронезависимо
    pattern = r'@(\w+)'
    matches = re.findall(pattern, text)

    if matches:
        all_mentions = []
        roles_processed = set()

        for role in matches:
            role_lower = role.lower()
            if role_lower in roles_processed:
                continue  # Избегаем повторной обработки той же роли
            roles_processed.add(role_lower)

            # Проверяем, существует ли такая роль
            conn = sqlite3.connect('db/roles.db')
            c = conn.cursor()
            c.execute("SELECT DISTINCT username FROM roles WHERE LOWER(role) = ?", (role_lower,))
            users = c.fetchall()
            conn.close()

            if users:
                mentions = [f'@{username_tuple[0]}' for username_tuple in users]
                all_mentions.extend(mentions)

        if all_mentions:
            # Убираем дубликаты
            unique_mentions = list(set(all_mentions))
            mentions_text = ' '.join(unique_mentions)

            # Отправляем новое сообщение с упоминаниями
            update.message.reply_text(mentions_text, parse_mode=ParseMode.HTML)
            # context.bot.send_message(
            #     chat_id=message.chat.id,
            #     text=mentions_text,
            #     parse_mode=ParseMode.HTML
            # )

def removerole_start(update: Update, context: CallbackContext):
    # Автоматическая отмена предыдущего диалога
    context.user_data.clear()

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    user = update.message.from_user
    chat = update.effective_chat

    # Проверяем, является ли пользователь администратором
    try:
        member = context.bot.get_chat_member(chat.id, user.id)
        if member.status not in ['administrator', 'creator']:
            update.message.reply_text('Только администратор может удалять роли.')
            # Удаляем сообщение пользователя с командой
            try:
                context.bot.delete_message(chat_id=chat.id, message_id=context.user_data['user_command_message_id'])
            except:
                pass
            return ConversationHandler.END
    except:
        update.message.reply_text('Не удалось проверить ваши права. Попробуйте позже.')
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

    # Получаем список ролей из базы данных
    conn = sqlite3.connect('db/roles.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT role FROM roles")
    results = c.fetchall()
    conn.close()

    if results:
        keyboard = []
        for role_tuple in results:
            role = role_tuple[0]
            keyboard.append([InlineKeyboardButton(role, callback_data=f'removerole_role:{role}')])
        keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_message = update.message.reply_text('Выберите роль для удаления:', reply_markup=reply_markup)
        context.user_data['message_to_delete'] = sent_message.message_id
        return REMOVEROLE_CHOOSE_ROLE
    else:
        update.message.reply_text('Пока нет доступных ролей для удаления.')
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

def removerole_choose_role(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'cancel':
        try:
            query.message.delete()
        except:
            pass
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=query.message.chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

    if data.startswith('removerole_role:'):
        role = data.split(':', 1)[1]

        # Удаляем роль из базы данных
        conn = sqlite3.connect('db/roles.db')
        c = conn.cursor()
        c.execute("DELETE FROM roles WHERE role = ?", (role,))
        conn.commit()
        conn.close()

        query.edit_message_text(f'Роль "{role}" успешно удалена.')

        # Удаляем сообщения пользователя с командой и системные сообщения
        try:
            if 'message_to_delete' in context.user_data:
                context.bot.delete_message(chat_id=query.message.chat.id, message_id=context.user_data['message_to_delete'])
        except:
            pass

        try:
            context.bot.delete_message(chat_id=query.message.chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass

        return ConversationHandler.END
    else:
        query.message.reply_text('Неизвестная команда.')
        return ConversationHandler.END

def assignrole_start(update: Update, context: CallbackContext):
    # Автоматическая отмена предыдущего диалога
    context.user_data.clear()

    # Сохраняем ID сообщения пользователя с командой
    context.user_data['user_command_message_id'] = update.message.message_id

    conn = sqlite3.connect('db/roles.db')
    c = conn.cursor()
    c.execute("SELECT DISTINCT role FROM roles")
    results = c.fetchall()
    conn.close()

    if results:
        keyboard = []
        for role_tuple in results:
            role = role_tuple[0]
            keyboard.append([InlineKeyboardButton(role, callback_data=f'assignrole_role:{role}')])
        keyboard.append([InlineKeyboardButton('Отмена', callback_data='cancel')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        sent_message = update.message.reply_text('Выберите роль, которую хотите назначить себе:', reply_markup=reply_markup)
        context.user_data['message_to_delete'] = sent_message.message_id
        return ASSIGNROLE_CHOOSE_ROLE
    else:
        update.message.reply_text('Пока нет доступных ролей.')
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

def assignrole_choose_role(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'cancel':
        try:
            query.message.delete()
        except:
            pass
        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass
        return ConversationHandler.END

    if data.startswith('assignrole_role:'):
        role = data.split(':', 1)[1].lower()
        context.user_data['assignrole'] = {'role': role}

        # Подтверждение назначения роли
        keyboard = [
            [InlineKeyboardButton('Да', callback_data='assignrole_confirm_yes')],
            [InlineKeyboardButton('Нет', callback_data='assignrole_confirm_no')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(f'Вы уверены, что хотите назначить себе роль "{role}"?', reply_markup=reply_markup)
        return ASSIGNROLE_CONFIRM
    else:
        query.message.reply_text('Неизвестная команда.')
        return ConversationHandler.END

def assignrole_confirm(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'assignrole_confirm_yes':
        role = context.user_data['assignrole'].get('role')
        if not role:
            query.edit_message_text('Произошла ошибка. Роль не найдена.')
            return ConversationHandler.END

        username = update.effective_user.username
        if not username:
            query.edit_message_text('Не удалось получить ваше имя пользователя.')
            return ConversationHandler.END

        conn = sqlite3.connect('db/roles.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO roles (username, role) VALUES (?, ?)", (username.lower(), role))
        conn.commit()
        conn.close()

        query.edit_message_text(f'Вы успешно назначили себе роль "{role}".')

        # Удаляем системные сообщения бота
        try:
            if 'message_to_delete' in context.user_data:
                context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['message_to_delete'])
        except:
            pass

        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass

        return ConversationHandler.END

    elif data == 'assignrole_confirm_no':
        query.edit_message_text('Операция назначение роли отменена.')

        # Удаляем системные сообщения бота
        try:
            if 'message_to_delete' in context.user_data:
                context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['message_to_delete'])
        except:
            pass

        # Удаляем сообщение пользователя с командой
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['user_command_message_id'])
        except:
            pass

        return ConversationHandler.END
    else:
        query.message.reply_text('Неизвестная команда.')
        return ConversationHandler.END


def main():
    # Инициализируем базу данных
    init_db()

    # Создаем объект Updater и передаем ему токен бота
    updater = Updater(TOKEN, use_context=True)

    # Получаем диспетчер для регистрации обработчиков
    dp = updater.dispatcher

    # Обработчики команд
    dp.add_handler(CommandHandler('start', start_command))
    dp.add_handler(CommandHandler('help', help_command))
    dp.add_handler(CommandHandler('roles', list_roles))

    # Обработчики для /setrole
    setrole_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('setrole', setrole_start)],
        states={
            SETROLE_CHOOSE_OPTION: [
                CallbackQueryHandler(setrole_option_callback, pattern='^setrole_.*$'),
                CallbackQueryHandler(setrole_option_callback, pattern='^(back|cancel)$'),
                CommandHandler('cancel', cancel),
            ],
            SETROLE_ENTER_ROLE_NAME: [
                MessageHandler(Filters.text & ~Filters.command, setrole_new_role_name),
                CommandHandler('cancel', cancel),
            ],
            SETROLE_SELECT_USER: [
                MessageHandler(Filters.text & ~Filters.command, setrole_select_user),
                CommandHandler('cancel', cancel),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True,
    )
    dp.add_handler(setrole_conv_handler)

    # Обработчики для /getrole
    getrole_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('getrole', getrole_start)],
        states={
            GETROLE_ENTER_USERNAME: [
                MessageHandler(Filters.text & ~Filters.command, getrole_enter_username),
                CommandHandler('cancel', cancel),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True,
    )
    dp.add_handler(getrole_conv_handler)

    # Обработчики для /deleterole
    deleterole_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('deleterole', deleterole_start)],
        states={
            DELETEROLE_SELECT_USER: [
                MessageHandler(Filters.text & ~Filters.command, deleterole_select_user),
                CommandHandler('cancel', cancel),
            ],
            DELETEROLE_SELECT_ROLE: [
                CallbackQueryHandler(deleterole_role_callback, pattern='^deleterole_role:.*$'),
                CallbackQueryHandler(deleterole_role_callback, pattern='^(back|cancel)$'),
                CommandHandler('cancel', cancel),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True,
    )
    dp.add_handler(deleterole_conv_handler)

    # Обработчики для /tagrole
    tagrole_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('tagrole', tagrole_start)],
        states={
            TAGROLE_CHOOSE_ROLE: [
                CallbackQueryHandler(tagrole_choose_role, pattern='^tagrole_role:.*$'),
                CallbackQueryHandler(tagrole_choose_role, pattern='^cancel$'),
                CommandHandler('cancel', cancel),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True,
    )
    dp.add_handler(tagrole_conv_handler)

    # Обработчик для /assignrole
    assignrole_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('assignrole', assignrole_start)],
        states={
            ASSIGNROLE_CHOOSE_ROLE: [
                CallbackQueryHandler(assignrole_choose_role, pattern='^assignrole_role:.*$'),
                CallbackQueryHandler(assignrole_choose_role, pattern='^cancel$'),
                CommandHandler('cancel', cancel),
            ],
            ASSIGNROLE_CONFIRM: [
                CallbackQueryHandler(assignrole_confirm, pattern='^assignrole_confirm_.*$'),
                CommandHandler('cancel', cancel),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True,
    )
    dp.add_handler(assignrole_conv_handler)

    # Обработчик сообщений для замены @<роль> на упоминания участников роли
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, role_mention_handler), group=1)

    # Обработчики для /removerole
    removerole_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('removerole', removerole_start)],
        states={
            REMOVEROLE_CHOOSE_ROLE: [
                CallbackQueryHandler(removerole_choose_role, pattern='^removerole_role:.*$'),
                CallbackQueryHandler(removerole_choose_role, pattern='^cancel$'),
                CommandHandler('cancel', cancel),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_user=True,
    )
    dp.add_handler(removerole_conv_handler)

    # Запускаем бота
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()