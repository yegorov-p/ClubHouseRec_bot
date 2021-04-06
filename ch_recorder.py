#!/usr/bin/python3

import traceback
import threading
from pymongo import MongoClient
from time import sleep
import configparser
import logging.config
import subprocess

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
            'filename': 'ch_recorder.log',
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

logger = logging.getLogger(__name__)


def run_cmd(cmd, room_id):
    proc = subprocess.Popen([cmd], shell=True)
    TASKS.update_one({'_id': room_id}, {'$set': {'status': 'DOWNLOADING',
                                                 'pid': proc.pid}})
    proc.wait()


if __name__ == "__main__":
    while True:
        config = configparser.ConfigParser()
        config.read('settings.ini')
        UID = config['Clubhouse']['user_id']
        sleep(5)
        try:
            for task in TASKS.find({'status': 'GOT_TOKEN'}):
                room_id = task['_id']
                logger.info(f'Recording {room_id}')
                token = task['token']

                cmd = f'./recorder_local --channel {room_id} --appId 938de3e8055e42b281bb8c6f69c21f78 --uid {UID} --channelKey {token} --appliteDir bin --isMixingEnabled 1 --isAudioOnly 1 --idle 120 --recordFileRootDir records --logLevel 2'
                logger.info(cmd)
                threading.Thread(target=run_cmd, args=(cmd,room_id,)).start()
        except:
            logger.critical(f'start_record has broken')
            print(traceback.format_exc())
