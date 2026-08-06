import os
from google import genai

def get_working_gemini_client():
    """אווסף את כל המפתחות שהוגדרו בסביבה לרשימה"""
    api_key_names = [
        'GEMINI_API_KEY', 
        'GEMINI_API_KEY_1', 
        'GEMINI_API_KEY_2', 
        'GEMINI_API_KEY_3', 
        'GEMINI_API_KEY_4', 
        'GEMINI_API_KEY_5'
    ]
    
    available_keys = []
    for name in api_key_names:
        key = os.getenv(name)
        if key:
            available_keys.append((name, key))
            
    if not available_keys:
        raise ValueError("No Gemini API keys found in environment variables!")
        
    return available_keys

def generate_with_gemini_fallback(contents):
    """מנסה ליצור תוכן מול Gemini, ואם מפתח נכשל (כמו שגיאת 429), עובר למפתח הבא"""
    keys = get_working_gemini_client()
    last_error = None
    
    for name, key in keys:
        try:
            print(f"Trying Gemini API with key: {name}")
            client = genai.Client(api_key=key)
            
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=contents
            )
            return response
        except Exception as e:
            print(f"Key {name} failed with error: {e}")
            last_error = e
            continue  # עובר למפתח הבא ברשימה
            
    raise Exception(f"All Gemini API keys exhausted or failed. Last error: {last_error}")
