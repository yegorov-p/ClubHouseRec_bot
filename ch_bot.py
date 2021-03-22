from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import urllib.parse
import logging.config
from clubhouse import Clubhouse
from datetime import datetime, timezone
import pytz
from pymongo import MongoClient
import configparser
import psutil

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s] %(lineno)-5s %(levelname)-8s  %(message)s',
            'datefmt': "%Y-%m-%d %H:%M:%S",
        }
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'formatter': 'standard',
            'class': 'logging.StreamHandler',
        },
        'rotate_file': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'ch_bot.log',
            'encoding': 'utf8',
            'maxBytes': 1000000,
            'backupCount': 10,
        }
    },
    'loggers': {
        '': {
            'handlers': [
                'console',
                'rotate_file'
            ],
            'level': 'DEBUG',
        },
    }
}
logging.config.dictConfig(LOGGING)

CLIENT = MongoClient(host='localhost:27017',
                     tz_aware=True,
                     )
TASKS = CLIENT['clubhouse']['tasks']
QUEUE = CLIENT['clubhouse']['queue']

logger = logging.getLogger(__name__)


def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    logger.debug(f'START from {update.message.chat_id}')
    if str(update.message.chat_id) not in WHITE_LIST:
        update.message.reply_html(
            f"We are under ban from Clubhouse. Check https://www.reddit.com/r/ClubhouseApp/comments/lqi79i/recording_clubhouse_crash_course/")
    else:
        update.message.reply_html('Just send me a link to a room or an event')


def status(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) not in WHITE_LIST:
        logger.warning(f'Unknown user {update.message.chat_id}')
        update.message.reply_html(
            f"We are under ban from Clubhouse. Check https://www.reddit.com/r/ClubhouseApp/comments/lqi79i/recording_clubhouse_crash_course/")
        return
    logger.debug(f'STATUS from {update.message.chat_id}')
    act_rec = TASKS.count_documents({'status': 'DOWNLOADING'})
    in_queue = QUEUE.count_documents({})

    act_tasks = '\n'.join(
        ['{}: {} /kill_{}'.format(task['topic'], datetime.now(timezone.utc) - task['dt'], task['pid']) for task in
         TASKS.find({'status': 'DOWNLOADING'})])
    future_tasks = '\n'.join([str(task['time_start'] - datetime.now(timezone.utc)) for task in QUEUE.find()])

    update.message.reply_html(f'<b>Recording:</b> {act_rec}\n'
                              f'{act_tasks}\n'
                              f'<b>Waiting in queue:</b> {in_queue}\n'
                              f'{future_tasks}'
                              )


def room_msg(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) not in WHITE_LIST:
        logger.warning(f'Unknown user {update.message.chat_id}')
        update.message.reply_html(
            f"We are under ban from Clubhouse. Check https://www.reddit.com/r/ClubhouseApp/comments/lqi79i/recording_clubhouse_crash_course/")
        return

    room_id = urllib.parse.urlparse(update.message.text).path.split('/')[-1]
    logger.info(f'ROOM from {update.message.chat_id}: {room_id}')

    cur_task = TASKS.find_one({'_id': room_id})

    if cur_task:
        logger.debug('We already know about that room')
        TASKS.update_one({
            '_id': room_id
        }, {
            '$addToSet': {'users': update.message.chat_id}
        })
        logger.info(f'Added {update.message.chat_id} to ROOM {room_id}')
        update.message.reply_html(f"Recording {cur_task['topic']}. We'll notify you as soon as it's over.")
    else:
        logger.info(f'{room_id}: New room ')

        active_downloads = TASKS.count_documents({'status': 'DOWNLOADING',
                                                  'users': [update.message.chat_id],
                                                  })

        all_downloads = TASKS.count_documents({'status': 'DOWNLOADING',
                                               })

        if active_downloads > 10:
            logger.warning(f'Greedy user {update.message.chat_id}: {active_downloads}')
            update.message.reply_html(f"You are too greedy! You have standalone {active_downloads} active downloads.")
        elif all_downloads > 80:
            logger.error(f'Out of quota')
            update.message.reply_html(f"Out of quota. Please try again later")
        else:
            logger.error(f'{room_id}: New')
            TASKS.insert_one({'_id': room_id,
                              'status': 'WAITING_FOR_TOKEN',
                              'dt': datetime.utcnow(),
                              'users': [update.message.chat_id]
                              })
            update.message.reply_html(
                f"Preparing to record that room. Because of some new limits from Clubhouse that can take some time.")


def event_msg(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) not in WHITE_LIST:
        logger.warning(f'Unknown user {update.message.chat_id}')
        update.message.reply_html(
            f"We are under ban from Clubhouse. Check https://www.reddit.com/r/ClubhouseApp/comments/lqi79i/recording_clubhouse_crash_course/")
        return

    event_id = urllib.parse.urlparse(update.message.text).path.split('/')[-1]
    logger.info(f'EVENT from {update.message.chat_id}: {event_id}')

    data = client.get_event(event_hashid=event_id)

    if data.get('success', False):
        logger.debug('Found an event.')
        ev = data['event']
        room_id = ev['channel']
        topic = ev['name']
        time_start = datetime.fromisoformat(ev['time_start']).astimezone(pytz.utc)

        if ev['is_expired']:
            logger.warning(f'This event has expired: {event_id}')
            update.message.reply_text('This event has expired.')
        elif ev['is_member_only']:
            logger.warning(f'This event is private: {event_id}')
            update.message.reply_text('This event is private.')
        elif room_id:
            cur_task = TASKS.find_one({'_id': room_id})

            if cur_task:
                logger.debug('We already know about that room')
                TASKS.update_one({
                    '_id': room_id
                }, {
                    '$addToSet': {'users': update.message.chat_id}
                })
                logger.info(f'Added {update.message.chat_id} to ROOM {room_id}')
                update.message.reply_html(f"Recording <b>{topic}</b>. We'll notify you as soon as it's over.")
            else:
                logger.info(f'{room_id}: New event')
                TASKS.insert_one({'_id': room_id,
                                  'status': 'WAITING_FOR_TOKEN',
                                  'dt': datetime.utcnow(),
                                  'users': [update.message.chat_id]
                                  })
                update.message.reply_html(
                    f"Preparing to record that room. Because of some new limits from Clubhouse that can take some time.")

        else:
            QUEUE.update_one({'_id': event_id},
                             {'$set': {'time_start': time_start},
                              '$addToSet': {'users': update.message.chat_id}},
                             upsert=True)
            logger.info(f'New event {event_id}')
            update.message.reply_html(f"Looking forward for <b>{topic}</b>. We'll notify you as soon as it's over.")

    elif 'detail' in data:
        logger.warning(f'ERROR {event_id} BAN')
        update.message.reply_text('This is BAN')

    else:
        logger.warning(f'ERROR {event_id} ' + data.get('error_message'))
        update.message.reply_text('Clubhouse said: ' + data.get('error_message', 'This event is not active'))


def kill(update: Update, context: CallbackContext) -> None:
    if str(update.message.chat_id) not in WHITE_LIST:
        logger.warning(f'Unknown user {update.message.chat_id}')
        update.message.reply_html(
            f"We are under ban from Clubhouse. Check https://www.reddit.com/r/ClubhouseApp/comments/lqi79i/recording_clubhouse_crash_course/")
        return

    pid = int(update.message.text.replace('/kill_', ''))
    logger.info(f'KILL from {update.message.chat_id}: {pid}')
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):  # or parent.children() for recursive=False
        child.terminate()

    update.message.reply_html(f"Killed")


def error(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def main():
    """Start the bot."""

    updater = Updater(TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("status", status))

    dispatcher.add_handler(MessageHandler(Filters.regex('^(\/kill_.+)$'), kill))

    dispatcher.add_handler(MessageHandler(Filters.regex('joinclubhouse\.com\/room\/.*$') & ~Filters.command, room_msg))
    dispatcher.add_handler(
        MessageHandler(Filters.regex('joinclubhouse\.com\/event\/.*$') & ~Filters.command, event_msg))

    dispatcher.add_error_handler(error)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read('settings.ini')

    WHITE_LIST = config['Telegram']['white_list'].split(',')

    TOKEN = config['Telegram']['token']

    client = Clubhouse(
        user_id=config['Clubhouse']['user_id'],
        user_token=config['Clubhouse']['user_token'],
        user_device=config['Clubhouse']['user_device']
    )
    main()
