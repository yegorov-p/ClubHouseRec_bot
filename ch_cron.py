#!/usr/bin/python3

import traceback
import threading
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from pathlib import Path
from telegram.ext import Updater
import telegram
import os
from time import sleep
import shutil
import configparser
from clubhouse import Clubhouse

import logging.config

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
            'filename': 'ch_cron.log',
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


def run_cmd(cmd):
    os.system(cmd)


def process_audiofiles():
    while True:
        sleep(20)
        try:
            for task in TASKS.find({'status': 'DOWNLOADING'}):
                room_id = task['_id']

                users = task['users']
                title = task['topic']
                for p in Path('records').glob(f'*/{room_id}_*/recording2-done.txt'):
                    logger.info(f'{room_id} seems to be ready')
                    directory = p.parent
                    file_list = list(Path(directory).glob('*_*.aac'))
                    if file_list:
                        filename = list(Path(directory).glob('*_*.aac'))[0]
                        filesize = Path(filename).stat().st_size
                        logger.info(f'Audio ready!: {filename} {filesize}')

                        if filesize > 40 * 1024 * 1024:
                            logger.info('Large file, chopping...')
                            cmd = f'ffmpeg -i {filename} -f segment -segment_time 3600 -c copy {directory}/out%03d.aac'
                            os.system(cmd)

                            for ch in sorted([str(k) for k in Path(directory).glob('out*.aac')]):
                                cmd = f'ffmpeg -i {ch} -acodec libmp3lame {ch[:-4]}.mp3'
                                os.system(cmd)

                            for user in users:
                                logger.info(f'Sending {room_id} files to user {user} {len(users)}')
                                counter = 1
                                for ch in sorted([str(k) for k in Path(directory).glob('out*.mp3')]):
                                    try:
                                        logger.info(f'Sent {counter}')
                                        sleep(5)
                                        Updater(TOKEN).bot.send_audio(
                                            chat_id=user,
                                            audio=open(ch, 'rb'),
                                            title=f'{title}: part {counter}')
                                    except telegram.error.Unauthorized:
                                        logger.warning(f'{user} banned the bot!')
                                        break

                                    counter += 1
                                logger.info(f'Sent files to user {user}')
                                TASKS.update_one({'_id': room_id},
                                                 {'$pull': {'users': user}})
                        else:
                            cmd = f'ffmpeg -i {filename} -acodec libmp3lame {directory}/{room_id}.mp3'
                            os.system(cmd)

                            for user in users:
                                logger.info(f'Sending {room_id} file to user {user} {len(users)}')
                                try:
                                    sleep(5)
                                    Updater(TOKEN).bot.send_audio(
                                        chat_id=user,
                                        audio=open(f'{directory}/{room_id}.mp3', 'rb'),
                                        title=title)
                                except telegram.error.Unauthorized:
                                    logger.warning(f'{user} banned the bot!')
                                logger.info(f'Sent files to user {user}')
                                TASKS.update_one({'_id': room_id},
                                                 {'$pull': {'users': user}})

                        TASKS.delete_one({'_id': room_id})

                        logger.info(f'Removing dir {directory}')
                        shutil.rmtree(directory)
                        break

                    else:
                        logger.warning('No recording!')

                        for user in users:
                            logger.info(f'Informing {user}')
                            try:
                                Updater(TOKEN).bot.send_message(
                                    chat_id=user,
                                    text=f"Room <b>{title}</b> was not recorded for some reason. Usually that means that there were no active speakers for several minutes.",
                                    parse_mode='html')
                            except telegram.error.Unauthorized:
                                logger.warning(f'{user} banned the bot!')

                        TASKS.delete_one({'_id': room_id})

                        logger.info(f'Removing dir {directory}')
                        shutil.rmtree(directory)
                        break

        except:
            logger.critical(f'process_audiofiles has broken')
            print(traceback.format_exc())


def process_token():
    while True:
        sleep(5)
        try:
            for task in TASKS.find({'status': 'WAITING_FOR_TOKEN'}):
                room_id = task['_id']
                logger.info(f'Need token for {room_id}')
                data = client.join_channel(room_id)
                users = task['users']
                if data.get('success'):
                    token = data['token']
                    topic = data['topic']

                    logger.debug(f'Got token for {room_id}: {token}')

                    TASKS.update_one({'_id': room_id},
                                     {'$set': {
                                         'token': token,
                                         'topic': topic,
                                         'status': 'GOT_TOKEN'
                                     }})
                    for user in users:
                        logger.info(f'Informing {user} about token')
                        try:
                            Updater(TOKEN).bot.send_message(
                                chat_id=user,
                                text=f"Recording <b>{topic}</b>. We'll notify you as soon as it's over.",
                                parse_mode='html')
                        except telegram.error.Unauthorized:
                            logger.warning(f'{user} banned the bot!')
                    sleep(5)
                    client.leave_channel(room_id)
                elif 'This room is no longer available' in data.get('error_message', ''):
                    for user in users:
                        logger.info(f'Informing {user}')
                        try:
                            Updater(TOKEN).bot.send_message(
                                chat_id=user,
                                text=f'Planned event has either expired or we were banned by clubhouse. Sorry :(',
                                parse_mode='html')
                        except telegram.error.Unauthorized:
                            logger.warning(f'{user} banned the bot!')

                    TASKS.delete_one({'_id': room_id})
                else:
                    TASKS.update_one({'_id': room_id},
                                     {'$set': {'status': 'ERROR'}})
                    logger.critical('NO TOKEN! BAN???')
                    print(data)
                    for user in users:
                        logger.info(f'Informing {user}')
                        try:
                            Updater(TOKEN).bot.send_message(
                                chat_id=user,
                                text=f'This is probably ban',
                                parse_mode='html')
                        except telegram.error.Unauthorized:
                            logger.warning(f'{user} banned the bot!')
                sleep(25)
        except:
            logger.critical('process_token has broken')
            print(traceback.format_exc())


def process_queue():
    while True:
        try:
            for task in QUEUE.find().batch_size(5):
                if task['time_start'] - datetime.now(timezone.utc) < timedelta(minutes=10) and not task.get('skip'):
                    event_id = task['_id']
                    logger.debug(f'Tick-tock for {event_id}')
                    users = task['users']
                    data = client.get_event(event_hashid=event_id)

                    if data.get('success'):
                        ev = data['event']
                        room_id = ev['channel']
                        topic = ev['name']

                        if ev['is_expired'] or (
                                datetime.now(timezone.utc) - task['time_start'] > timedelta(minutes=65)):
                            logger.warning('Event expired!')
                            QUEUE.delete_one({'_id': event_id})
                            for user in users:
                                logger.info(f'Informing {user}')
                                try:
                                    Updater(TOKEN).bot.send_message(
                                        chat_id=user,
                                        text=f'Event <b>{topic}</b> has either expired or we were banned by clubhouse',
                                        parse_mode='html')
                                except telegram.error.Unauthorized:
                                    logger.warning(f'{user} banned the bot!')

                        elif ev['is_member_only']:
                            logger.warning('Private!')
                            QUEUE.delete_one({'_id': event_id})
                            for user in users:
                                logger.info(f'Informing {user}')
                                try:
                                    Updater(TOKEN).bot.send_message(
                                        chat_id=user,
                                        text=f'Event <b>{topic}</b> is private, we cannot record it.',
                                        parse_mode='html')
                                except telegram.error.Unauthorized:
                                    logger.warning(f'{user} banned the bot!')

                        elif room_id:
                            logger.info(f'Got room_id {room_id}')
                            cur_task = TASKS.find_one({'_id': room_id})

                            if cur_task:
                                logger.info('We already know about that room')
                                TASKS.update_one({
                                    '_id': room_id
                                }, {
                                    '$addToSet': {'users': users}
                                })
                                QUEUE.delete_one({'_id': event_id})
                                for user in users:
                                    logger.info(f'Informing {user}')
                                    try:
                                        Updater(TOKEN).bot.send_message(
                                            chat_id=user,
                                            text=f'Event <b>{topic}</b> has started. Preparing to record that room. Because of some new limits from Clubhouse that can take some time.',
                                            parse_mode='html')
                                    except telegram.error.Unauthorized:
                                        logger.warning(f'{user} banned the bot!')
                            else:
                                logger.error(f'{room_id}: New')
                                TASKS.insert_one({'_id': room_id,
                                                  'status': 'WAITING_FOR_TOKEN',
                                                  'topic': topic,
                                                  'users': users,
                                                  'dt': datetime.utcnow()
                                                  })
                                QUEUE.delete_one({'_id': event_id})
                                for user in users:
                                    logger.info(f'Informing {user}')
                                    try:
                                        Updater(TOKEN).bot.send_message(
                                            chat_id=user,
                                            text=f'Event <b>{topic}</b> has started. Preparing to record that room. Because of some new limits from Clubhouse that can take some time.',
                                            parse_mode='html')
                                    except telegram.error.Unauthorized:
                                        logger.warning(f'{user} banned the bot!')

                    else:
                        QUEUE.update_one({'_id': event_id},
                                         {'$set': {'skip': True}})
                        logger.critical('NO TOKEN! BAN???')

                        for user in users:
                            logger.info(f'Informing {user}')
                            try:
                                Updater(TOKEN).bot.send_message(
                                    chat_id=user,
                                    text=f'This is probably ban of event {event_id}',
                                    parse_mode='html')
                            except telegram.error.Unauthorized:
                                logger.warning(f'{user} banned the bot!')
                    sleep(15)
        except:
            logger.critical('process_queue has broken')
            print(traceback.format_exc())

        sleep(30)


if __name__ == "__main__":
    logger.info('Started cron!')

    config = configparser.ConfigParser()
    config.read('settings.ini')

    TOKEN = config['Telegram']['token']

    client = Clubhouse(
        user_id=config['Clubhouse']['user_id'],
        user_token=config['Clubhouse']['user_token'],
        user_device=config['Clubhouse']['user_device']
    )

    threading.Thread(target=process_audiofiles, args=()).start()
    logger.info('Started process_audiofiles')

    threading.Thread(target=process_queue, args=()).start()
    logger.info('Started process_queue')

    threading.Thread(target=process_token, args=()).start()
    logger.info('Started process_token')
