from datetime import datetime
import os
import subprocess
import pytz
import requests
import yfinance as yf

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

# הגדרת מניות לעדכון
US_TICKERS = ['AMD', 'WMT', 'MU']
FINNHUB_API_KEY = os.environ.get('FINNHUB_API_KEY', 'd9j76bpr01qg3bn3763gd9j76bpr01qg3bn37640')
IL_TICKERS = ['TEVA.TA', 'NICE.TA']

def fetch_market_data():
    market_data = {}
    
    # 1. שליפת השוק האמריקאי (מדויק דרך Finnhub)
    for ticker in US_TICKERS:
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}"
            response = requests.get(url)
            data = response.json()
            if data.get("c") is not None:
                market_data[ticker] = {
                    "price": data.get("c"),
                    "change": data.get("dp"),
                    "market": "US"
                }
        except Exception as e:
            print(f"Error fetching US stock {ticker}: {e}")

    # 2. שליפת השוק הישראלי (עם דיליי דרך yfinance)
    for ticker in IL_TICKERS:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='1d')
            if not hist.empty:
                current_price = round(hist['Close'].iloc[-1], 2)
                prev_close = stock.info.get('previousClose')
                if not prev_close and len(hist) > 1:
                    prev_close = hist['Close'].iloc[-2]
                
                change_pct = 0
                if prev_close:
                    change_pct = round(((current_price - prev_close) / prev_close) * 100, 2)
                
                market_data[ticker] = {
                    "price": current_price,
                    "change": change_pct,
                    "market": "IL"
                }
        except Exception as e:
            print(f"Error fetching IL stock {ticker}: {e}")

    return market_data

def send_telegram_push(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if token and chat_id:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
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

# שעות פעילות לעדכון האתר: מ-10:30 בבוקר ועד 23:30 בלילה
is_within_auto_hours = 630 <= current_total_minutes <= 1410
should_update = (trigger_event == 'workflow_dispatch') or is_within_auto_hours

if should_update:
    # שליפת הנתונים העדכניים לכל ריצה
    stocks = fetch_market_data()
    
    try:
        date_str = now_il.strftime('%d.%m.%Y')
        time_str = now_il.strftime('%H:%M')

        new_time_html = f'עודכן לאחרונה: <span dir="ltr">{date_str} | {time_str}</span>'
        new_title_text = f'דו"ח סקייל שוק ההון המלא ליום {day_name} - נתונים מעודכנים 📊'

        # יצירת HTML מעודכן המכיל את כרטיסיות המניות
        stocks_html_cards = ""
        for ticker, info in stocks.items():
            emoji = "🟢" if info['change'] >= 0 else "🔴"
            market_label = "US (Real-time)" if info['market'] == "US" else "IL (20m delay)"
            stocks_html_cards += f"""
            <div class="stock-card" style="background: white; padding: 15px; margin-bottom: 10px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h3>{ticker} <span style="font-size: 0.8em; color: #7f8c8d;">({market_label})</span></h3>
                <p>מחיר: <b>${info['price']}</b> | שינוי יומי: {emoji} <b>{info['change']}%</b></p>
            </div>"""

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
                content = content[: idx_tag_end + 1] + new_title_text + content[idx_tag_close:]

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
                content = content[:idx_span_start] + opening_tag + new_time_html + content[idx_span_end:]

        # 3. הזרקת נתוני המניות לאזור ייעודי באתר (אם קיים id="stocks-container")
        target_stocks_id = 'id="stocks-container"'
        if target_stocks_id in content:
            idx_id = content.find(target_stocks_id)
            idx_tag_end = content.find('>', idx_id)
            idx_div_close = content.find('</div>', idx_tag_end)
            if idx_tag_end != -1 and idx_div_close != -1:
                content = content[: idx_tag_end + 1] + "\n" + stocks_html_cards + "\n" + content[idx_div_close:]

        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(content)

        print('Successfully updated index.html locally with market data.')

        # שליחת התראת טלגרם אך ורק ב-3 שעות היעוד או בהפעלה ידנית
        # שעות התראה לדוגמה: 10:30, 16:30, 22:30 (או בהפעלה ידנית)
        notification_times = [(10, 30), (16, 30), (22, 30)]
        is_notification_time = (current_hour, current_minute) in notification_times

        if (trigger_event == 'workflow_dispatch') or is_notification_time:
            update_type = 'ידני' if trigger_event == 'workflow_dispatch' else 'מתוזמן (3 ביום)'
            msg = f'📈 *עדכון תיק השקעות ({update_type})* - {day_name}, {now_il.strftime("%H:%M")}\n\n'
            for ticker, info in stocks.items():
                emoji = "🟢" if info['change'] >= 0 else "🔴"
                msg += f"🔹 *{ticker}*: `${info['price']}` ({emoji} `{info['change']}%`)\n"
            
            send_telegram_push(msg)

        # ביצוע Git Commit ו-Push אוטומטיים
        subprocess.run(['git', 'config', '--global', 'user.name', 'github-actions[bot]'], check=True)
        subprocess.run(['git', 'config', '--global', 'user.email', 'github-actions[bot]@users.noreply.github.com'], check=True)
        subprocess.run(['git', 'add', 'index.html'], check=True)

        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, check=True)
        if 'index.html' in status.stdout:
            subprocess.run(['git', 'commit', '-m', f'Update market data for {day_name} at {time_str}'], check=True)
            subprocess.run(['git', 'push'], check=True)
            print('Successfully pushed updated index.html to GitHub!')
        else:
            print('No changes detected by git.')

    except Exception as e:
        print(f'Error updating HTML: {e}')
else:
    print('Outside active auto-update hours. Skipping update.')
