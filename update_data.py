import os
import yfinance as yf
from supabase import create_client, Client

# הגדרת חיבור למסד הנתונים בעזרת הסודות שהכנסת
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# רשימת המניות לעדכון
tickers = ["AMD", "INTC", "MU", "WMT"]

def update_market_data():
    for ticker in tickers:
        try:
            # משיכת נתונים מ-Yahoo Finance
            stock = yf.Ticker(ticker)
            data = stock.history(period="1d")
            
            if not data.empty:
                # לקיחת המחיר הנוכחי בסגירה
                current_price = round(data['Close'].iloc[-1], 2)
                
                # עדכון הנתון ב-Supabase (בהנחה ששם הטבלה הוא 'stocks')
                # הקוד מחפש את השורה של המניה לפי הסימול, ומעדכן את מחיר הסגירה
                supabase.table("stocks").update({"current_price": current_price}).eq("ticker", ticker).execute()
                
                print(f"✅ Updated {ticker} to ${current_price}")
            else:
                print(f"⚠️ No data found for {ticker}")
                
        except Exception as e:
            print(f"❌ Error updating {ticker}: {e}")

if __name__ == "__main__":
    update_market_data()
