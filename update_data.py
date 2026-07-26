from datetime import datetime
import os
import re
import pytz
import requests

# הגדרת אזור זמן של ישראל
israel_tz = pytz.timezone('Asia/Jerusalem')
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute

# בדיקה האם אנחנו בתקופת מעבר (לפי התאריכים שהגדרת)
is_autumn_transition = (
    datetime(2026, 10, 25).date() <= current_date <= datetime(2026, 11, 1).date()
)
is_spring_transition = (
    datetime(2027, 3, 14).date() <= current_date <= datetime(2027, 3, 26).date()
)
is_transition_period = is_autumn_transition or is_spring_transition

# קביעת שעות הפושים
if is_transition_period:
  # תקופת מעבר: 10:30, 15:00, 22:30
  target_times = [(10, 30), (15, 0), (22, 30)]
  period_name = 'תקופת מעבר'
else:
  # שעון רגיל: 10:30, 16:00, 23:30
  target_times = [(10, 30), (16, 0), (23, 30)]
  period_name = 'שעון רגיל'

print(
    f'Current Israel Time: {now_il.strftime("%Y-%m-%d %H:%M")} ({period_name})'
)


def send_telegram_push(message):
  token = os.environ.get('TELEGRAM_BOT_TOKEN')
  chat_id = os.environ.get('TELEGRAM_CHAT_ID')
  if token and chat_id:
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    payload = {'chat_id': chat_id, 'text': message}
    try:
      response = requests.post(url, json=payload)
      if response.status_code == 200:
        print('Push sent successfully!')
      else:
        print(f'Failed to send push: {response.text}')
    except Exception as e:
      print(f'Error sending push: {e}')
  else:
    print('Telegram credentials missing.')


# בדיקה האם השעה הנוכחית תואמת לאחד מיעדי הפוש (בטווח של 15 דקות)
for target_h, target_m in target_times:
  if current_hour == target_h and abs(current_minute - target_m) < 15:
    msg = (
        f'📈 עדכון תיק השקעות ({period_name})!\nהפוש נשלח בשעה'
        f' {target_h}:{target_m:02d} שעון ישראל.'
    )
    send_telegram_push(msg)
    break

# עדכון אוטומטי של התאריך והשעה בקובץ ה-HTML
try:
  date_str = now_il.strftime('%d.%m.%Y')
  time_str = now_il.strftime('%H:%M')

  new_inner_html = f'עדכון אחרון: {date_str}<br>שעה: {time_str}'

  with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

  # החלפת התוכן בתוך ה-span עם id="last-updated"
  new_content = re.sub(
      r'(<span[^>]*id=["\']last-updated["\'][^>]*>)(.*?)(</span>)',
      r'\1' + new_inner_html + r'\3',
      content,
      flags=re.DOTALL,
  )

  with open('index.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

  print(f'Successfully updated index.html: {date_str} at {time_str}')
except Exception as e:
  print(f'Error updating time in HTML: {e}')
