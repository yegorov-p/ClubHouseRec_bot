from clubhouse import Clubhouse
import configparser

input("[Step 1] Send a Clubhouse invite to a fake phone number. Press Enter when ready.")
client = Clubhouse()

result = None
while True:
    user_phone_number = input("[Step 2] Enter the fake phone number (+79991234567 format) > ")
    result = client.start_phone_number_auth(user_phone_number)
    print(result)
    if not result['success']:
        print(f"[-] Error occured ({result['error_message']})")
        continue
    break

result = None
while True:
    verification_code = input("[Step 3] Please enter the SMS verification code (1234) > ")
    result = client.complete_phone_number_auth(user_phone_number, verification_code)
    if not result['success']:
        print(f"[-] Error occured ({result['error_message']})")
        continue
    break

user_id = str(result['user_profile']['user_id'])
user_token = result['auth_token']
user_device = client.HEADERS.get("CH-DeviceId")
print(f'user_id = {user_id}')
print(f'user_token = {user_token}')
print(f'user_device = {user_device}')

config = configparser.ConfigParser()

config['Clubhouse'] = {'user_device': user_device,
                       'user_id': user_id,
                       'user_token': user_token}

client = Clubhouse(user_id=user_id, user_token=user_token, user_device=user_device)

user_name = input("[Step 4] Please enter fake user name (Ivan Petrov) > ")
client.update_name(user_name)

user_login = input("[Step 5] Please enter fake user login (ivanpetrov1988) > ")
client.update_username(user_login)

tg_token = input(
    "[Step 6] Please enter your telegram bot access token (1701234739:AAGsjdfjhksdfgRe8oQNby2Jbx7sdfOnGw) > ")

tg_id = input("[Step 7] Please enter your telegram chat_id. Just contact http://t.me/username_to_id_bot > ")

config['Telegram'] = {'token': tg_token,
                      'white_list': tg_id}

with open('settings.ini', 'w') as configfile:
    config.write(configfile)
