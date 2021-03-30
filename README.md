# Installation

1) Run
>apt update && apt upgrade && apt install tmux ffmpeg python3-pip mongodb mc && mkdir -p ~/agora/bin && pip3 install psutil pymongo pytz python-telegram-bot clubhouse-py psutil

2) Download Agora On-premise Recording SDK: https://docs.agora.io/en/All/downloads?platform=Linux

3) Unpack and compile: https://docs.agora.io/en/Recording/recording_cmd_cpp?platform=Linux#compile-the-sample-code

4) Copy `recorder_local` next to `ch_recorder.py`
   
5) Run `python3 auther.py` to generate settings.

6) Run `ch_bot.py`, `ch_cron.py` and `ch_recorder.py` (tmux is your friend!)


# Greets and respects

https://github.com/stypr/clubhouse-py

https://github.com/Seia-Soto/clubhouse-api



