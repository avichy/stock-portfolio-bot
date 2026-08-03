import os
import json
import datetime
import yfinance as yf
import google.generativeai as genai

# קובץ מטמון ל-AI
CACHE_FILE = "ai_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving cache: {e}")

def get_gemini_response(prompt_text):
    # רוטציה בין מפתחות API מרובים מתוך משתני הסביבה
    api_keys = []
    for i in range(1, 6):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            api_keys.append(key)
    single_key = os.getenv("GEMINI_API_KEY")
    if single_key and single_key not in api_keys:
        api_keys.append(single_key)
        
    if not api_keys:
        print("No Gemini API keys found in environment variables.")
        return None

    for api_key in api_keys:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content(prompt_text)
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"API key failed, trying next... Error: {e}")
            continue
    return None

def fetch_market_data(tickers):
    data = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                change = ((current_price - prev_close) / prev_close) * 100
                
                info = t.info
                target = info.get('targetMeanPrice', 0)
                
                data[ticker] = {
                    "price": float(current_price),
                    "change": float(change),
                    "target": float(target) if target else 0
                }
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            data[ticker] = {"price": 0, "change": 0, "target": 0}
    return data

def format_num(val):
    if val is None:
        return "0.00"
    return f"{val:,.2f}"

def format_pct_colored(val):
    if val is None:
        return "0.00%"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}%"

def main():
    print("Starting market dashboard update script...")
    
    # הגדרת רשימת המניות בתיק האישי ובמעקב
    portfolio_stocks = [
        {"symbol": "AMD", "shares": 10, "avg_price": 120.0},
        {"symbol": "INTC", "shares": 15, "avg_price": 30.0},
        {"symbol": "MU", "shares": 8, "avg_price": 90.0},
        {"symbol": "NVDA", "shares": 5, "avg_price": 100.0}
    ]
    
    watchlist = [s["symbol"] for s in portfolio_stocks] + ["TSLA", "AAPL", "MSFT"]
    watchlist = list(set(watchlist)) # הסרת כפיפויות
    
    # 1. שליפת נתונים פיננסיים בזמן אמת
    market_data = fetch_market_data(watchlist)
    
    # 2. ניהול מטמון וקריאת AI
    cache = load_cache()
    now = datetime.datetime.now()
    
    ai_prompt = "תן לי ניתוח קצר למניות NVDA, TSLA, AMD בפורמט JSON הכולל רשימת long_term ו-swing עם שדות: symbol, name, rationale, target, sector_desc."
    
    ai_raw_text = get_gemini_response(ai_prompt)
    if ai_raw_text:
        try:
            clean_json = ai_raw_text.replace("```json", "").replace("```", "").strip()
            ai_data = json.loads(clean_json)
            cache['ai_data'] = ai_data
            cache['last_update'] = now.strftime("%Y-%m-%d %H:%M:%S")
            save_cache(cache)
        except Exception as e:
            print(f"Failed to parse AI JSON: {e}")
            ai_data = cache.get('ai_data', {"long_term": [], "swing": []})
    else:
        ai_data = cache.get('ai_data', {"long_term": [], "swing": []})

    long_term_stocks = ai_data.get("long_term", [
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "rationale": "מובילת שוק ה-AI עם ביקוש שיא לשבבים.", "target": "140"},
        {"symbol": "AMD", "name": "Advanced Micro Devices", "rationale": "צמיחה חזקה בתחום מעבדי השרתים וה-AI.", "target": "180"}
    ])
    
    swing_stocks = ai_data.get("swing", [
        {"symbol": "TSLA", "name": "Tesla Inc.", "rationale": "תנודתיות גבוהה המאפשרת הזדמנויות סווינג קצרות טווח.", "sector_desc": "רכב חשמלי ואנרגיה", "target": "250"}
    ])

    # 3. בניית הבלוקים של תיק ההשקעות האישי עם לוגואים אוטומטיים במקום סימן הברק
    portfolio_html_blocks = ""
    for stock in portfolio_stocks:
        sym = stock["symbol"]
        shares = stock["shares"]
        avg_price = stock["avg_price"]
        p_info = market_data.get(sym, {"price": 0, "change": 0, "target": 0})
        current_price = p_info["price"]
        total_value = current_price * shares
        profit_loss = (current_price - avg_price) * shares if current_price > 0 else 0
        pct_str = format_pct_colored(p_info["change"])
        
        logo_url = f"https://assets.parqet.com/logos/symbol/{sym}?format=png"
        
        portfolio_html_blocks += (
            '<tr class="border-b border-gray-700">'
            f'<td class="py-2 px-3 flex items-center gap-2">'
            f'<img src="{logo_url}" alt="{sym}" style="width: 20px; height: 20px; display: inline-block; vertical-align: middle; border-radius: 4px;" onerror="this.style.display=\'none\'">'
            f'<strong>{sym}</strong></td>'
            f'<td class="py-2 px-3">{shares}</td>'
            f'<td class="py-2 px-3">${format_num(avg_price)}</td>'
            f'<td class="py-2 px-3">${format_num(current_price)}</td>'
            f'<td class="py-2 px-3 text-cyan-300">{pct_str}</td>'
            f'<td class="py-2 px-3">${format_num(total_value)}</td>'
            '</tr>'
        )

    # 4. בניית הבלוקים של ה-AI (ארוך טווח וסווינג) עם לוגואים אוטומטיים
    long_term_html_blocks = ""
    for stock in long_term_stocks:
        sym = stock.get("symbol", "")
        name = stock.get("name", sym)
        rationale = stock.get("rationale", "")
        p_info = market_data.get(sym, {"price": 0, "change": 0, "target": 0})
        price_str = f"${format_num(p_info['price'])}" if p_info["price"] else "N/A"
        pct_str = format_pct_colored(p_info["change"])
        target_str = f"${format_num(p_info['target'])}" if p_info["target"] else stock.get("target", "N/A")
        
        logo_url = f"https://assets.parqet.com/logos/symbol/{sym}?format=png"
        
        long_term_html_blocks += (
            '<p class="border-b border-gray-700 pb-3">'
            f'<img src="{logo_url}" alt="{sym}" style="width: 20px; height: 20px; display: inline-block; vertical-align: middle; margin-left: 6px; border-radius: 4px;" onerror="this.style.display=\'none\'">'
            f"<strong>{name}</strong> (סמל: <strong>{sym}</strong>)<br>"
            f'מחיר נוכחי: <strong>{price_str}</strong> (<span class="text-cyan-300">{pct_str}</span>)<br>'
            f"מחיר יעד אנליסטים ממוצע: <strong>{target_str}</strong><br>"
            f'<strong>רציונל וניתוח AI ארוך טווח:</strong> <span class="text-gray-200">{rationale}</span>'
            "</p>"
        )

    swing_html_blocks = ""
    for stock in swing_stocks:
        sym = stock.get("symbol", "")
        name = stock.get("name", sym)
        sector_desc = stock.get("sector_desc", "מסחר סווינג ומומנטום")
        rationale = stock.get("rationale", "")
        p_info = market_data.get(sym, {"price": 0, "change": 0, "target": 0})
        price_str = f"${format_num(p_info['price'])}" if p_info["price"] else "N/A"
        pct_str = format_pct_colored(p_info["change"])
        target_str = f"${format_num(p_info['target'])}" if p_info["target"] else stock.get("target", "N/A")
        
        logo_url = f"https://assets.parqet.com/logos/symbol/{sym}?format=png"
        
        swing_html_blocks += (
            '<p class="border-b border-gray-700 pb-3">'
            f'<img src="{logo_url}" alt="{sym}" style="width: 20px; height: 20px; display: inline-block; vertical-align: middle; margin-left: 6px; border-radius: 4px;" onerror="this.style.display=\'none\'">'
            f"<strong>{name}</strong> (סמל: <strong>{sym}</strong>)<br>"
            f'מחיר נוכחי: <strong>{price_str}</strong> (<span class="text-cyan-300">{pct_str}</span>)<br>'
            f"יעד למסחר סווינג: <strong>{target_str}</strong><br>"
            f"תחום עיסוק: {sector_desc}<br>"
            f'<strong>רציונל וטריגר למסחר:</strong> <span class="text-gray-200">{rationale}</span>'
            "</p>"
        )

    # 5. עדכון קובץ ה-HTML הסופי מהתבנית
    template_file = "index.template.html"
    output_file = "index.html"
    
    if os.path.exists(template_file):
        with open(template_file, "r", encoding="utf-8") as f:
            template_content = f.read()
            
        final_content = template_content.replace("{{PORTFOLIO_STOCKS}}", portfolio_html_blocks)
        final_content = final_content.replace("{{LONG_TERM_STOCKS}}", long_term_html_blocks)
        final_content = final_content.replace("{{SWING_STOCKS}}", swing_html_blocks)
        final_content = final_content.replace("{{LAST_UPDATE}}", now.strftime("%Y-%m-%d %H:%M:%S"))
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(final_content)
        print(f"Successfully generated {output_file}")
    else:
        print(f"Template file {template_file} not found.")

if __name__ == "__main__":
    main()
