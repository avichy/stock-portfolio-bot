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
current_total_minutes = current_hour * 60 + current_minute

# זיהוי האם ההפעלה היא ידנית או אוטומטית מגיטהאב
trigger_event = os.environ.get('TRIGGER_EVENT', 'schedule')

# מיפוי שמות הימים בעברית
days_map = {
    0: 'שני',
    1: 'שלישי',
    2: 'רביעי',
    3: 'חמישי',
    4: 'שישי',
    5: 'שבת',
    6: 'ראשון',
}
day_name = days_map[now_il.weekday()]

print(
    f'Current Israel Time: {now_il.strftime("%Y-%m-%d %H:%M")} - Day:'
    f' {day_name} - Event: {trigger_event}'
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


# שעות פעילות לעדכון אוטומטי: מ-10:30 בבוקר (630 דקות) ועד 23:30 בלילה (1410 דקות)
is_within_auto_hours = 630 <= current_total_minutes <= 1410

# תנאי עדכון: אם לחצת ידנית -> תמיד מעדכן! אם זה אוטומטי -> רק בשעות הפעילות.
should_update = (trigger_event == 'workflow_dispatch') or is_within_auto_hours

if should_update:
    update_type = 'ידני' if trigger_event == 'workflow_dispatch' else 'אוטומטי'
    msg = (
        f'📈 עדכון תיק השקעות ({update_type})!\nהיום: {day_name}, בשעה'
        f' {now_il.strftime("%H:%M")} שעון ישראל.'
    )
    send_telegram_push(msg)

    try:
        date_str = now_il.strftime('%d.%m.%Y')
        time_str = now_il.strftime('%H:%M')

        new_time_html = (
            f'עודכן לאחרונה: <span dir="ltr">{date_str} | {time_str}</span>'
        )
        new_title_text = (
            f'דו"ח סקייל שוק ההון המלא ליום {day_name} - נתונים מעודכנים 📊'
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

            if (
                idx_span_start != -1
                and idx_tag_end != -1
                and idx_span_end != -1
            ):
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
            'Successfully updated index.html locally with day: '
            f'{day_name} at {time_str}'
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
                    f'Update report title for day: {day_name} at {time_str}',
                ],
                check=True,
            )
            subprocess.run(['git', 'push'], check=True)
            print('Successfully pushed updated index.html to GitHub!')
        else:
            print('No changes detected by git.')

    except Exception as e:
        print(f'Error updating HTML: {e}')
else:
    print(
        'Outside active auto-update hours (23:30 - 10:30) and triggered by'
        ' schedule. Skipping update.'
    )
