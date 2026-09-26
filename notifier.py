import requests

def send_telegram(token, chat_id, message):
    if not token or not chat_id:
        print('[TELEGRAM NOT CONFIGURED]\\n' + message)
        return False
    r = requests.post(f'https://api.telegram.org/bot{token}/sendMessage', json={'chat_id': chat_id, 'text': message, 'disable_web_page_preview': True}, timeout=20)
    r.raise_for_status()
    return True
