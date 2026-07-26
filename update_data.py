from datetime import datetime
import os
import subprocess
import pytz
import requests

# הגדרת אזור זמן של ישראל
israel_tz = pytz.timezone('Asia/Jerusalem')
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute

# בדיקה האם אנחנו בתקופת מעבר
is_autumn_transition = (
    datetime(2026, 10, 25).date() <= current_date <= datetime(2026, 11, 1).date()
)
is_spring_transition = (
    datetime(2027, 3, 14).date() <= current_date <= datetime(2027, 3, 26).date()
)
is_transition_period = is_autumn_transition or is_spring_transition

if is_transition_period:
    target_times = [(10, 30), (15, 0), (22, 30)]
    period_name = 'תקופת מעבר'
else:
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


for target_h, target_m in target_times:
    if current_hour == target_h and abs(current_minute - target_m) < 15:
        msg = (
            f'📈 עדכון תיק השקעות ({period_name})!\nהפוש נשלח בשעה'
            f' {target_h}:{target_m:02d} שעון ישראל.'
        )
        send_telegram_push(msg)
        break

# עדכון אוטומטי של הכותרת והשעה בקובץ ה-HTML ושליחה לגיטהאב
try:
    date_str = now_il.strftime('%d.%m.%Y')
    time_str = now_il.strftime('%H:%M')

    new_time_html = (
        f'עודכן לאחרונה: <span dir="ltr">{date_str} | {time_str}</span>'
    )
    # פורמט הכותרת המבוקש עם התאריך והאייקון
    new_title_text = (
        f'דו"ח סקייל שוק ההון המלא ליום <span dir="ltr">{date_str}</span> - נתונים'
        ' מעודכנים 📊'
    )

    with open('index.html', 'r', encoding='utf-8-sig') as f:
        content = f.read()

    # 1. עדכון הכותרת הראשית (id="report-title")
    target_title_id = 'id="report-title"'
    if target_title_id not in content:
        target_title_id = "id='report-title'"

    if target_title_id in content:
        idx_id = content.find(target_title_id)
        idx_tag_end = content.find('>', idx_id)
        idx_tag_close = content.find('</h1>', idx_tag_end)

        if idx_tag_end != -1 and idx_tag_close != -1:
            content = (
                content[: idx_tag_end + 1]
                + new_title_text
                + content[idx_tag_close:]
            )

    # 2. עדכון שעת העדכון האחרון (id="last-updated")
    target_time_id = 'id="last-updated"'
    if target_time_id not in content:
        target_time_id = "id='last-updated'"

    if target_time_id in content:
        idx_id = content.find(target_time_id)
        idx_span_start = content.rfind('<span', 0, idx_id)
        idx_tag_end = content.find('>', idx_id)
        idx_span_end = content.find('</span>', idx_tag_end)

        if idx_span_start != -1 and idx_tag_end != -1 and idx_span_end != -1:
            opening_tag = content[idx_span_start : idx_tag_end + 1]
            content = (
                content[:idx_span_start]
                + opening_tag
                + new_time_html
                + content[idx_span_end:]
            )

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)

    print(
        f'Successfully updated index.html locally with date: {date_str} at'
        f' {time_str}'
    )

    # ביצוע Git Commit ו-Push אוטומטיים
    subprocess.run(
        ['git', 'config', '--global', 'user.name', 'github-actions[bot]'],
        check=True,
    )
    subprocess.run(
        [
            'git',
            'config',
            '--global',
            'user.email',
            'github-actions[bot]@users.noreply.github.com',
        ],
        check=True,
    )
    subprocess.run(['git', 'add', 'index.html'], check=True)

    status = subprocess.run(
        ['git', 'status', '--porcelain'],
        capture_output=True,
        text=True,
        check=True,
    )
    if 'index.html' in status.stdout:
        subprocess.run(
            [
                'git',
                'commit',
                '-m',
                'Auto-update report title with specific date and icon',
            ],
            check=True,
        )
        subprocess.run(['git', 'push'], check=True)
        print('Successfully pushed updated index.html to GitHub!')
    else:
        print('No changes detected by git.')

except Exception as e:
    print(f'Error updating HTML: {e}')
