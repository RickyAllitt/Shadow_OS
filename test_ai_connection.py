
import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

def test_ai():
    api_key = os.environ.get('GEMINI_API_KEY')
    print(f"API Key present: {bool(api_key)}")
    if not api_key:
        return

    # Testing gemma-3-27b-it for comparison
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-3-27b-it:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    data = {
        "contents": [{
            "parts": [{"text": "System Check."}]
        }]
    }
    
    encoded_data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=encoded_data, headers=headers, method='POST')
    
    print(f"Testing URL: {url.split('?')[0]}...")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            print(f"Status: {response.status}")
            print(f"Body: {response.read().decode('utf-8')[:100]}...")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("SUCCESS: 429 Error CAUGHT safely. Fallback logic would trigger here.")
        else:
            print(f"FAILURE: Uncaught HTTP Error {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"FAILURE: Unexpected Exception: {e}")

if __name__ == "__main__":
    test_ai()
