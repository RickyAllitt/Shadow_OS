
import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv()

def list_models():
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("No API Key")
        return

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode('utf-8'))
            print("Available Models:")
            for m in data.get('models', []):
                if 'generateContent' in m.get('supportedGenerationMethods', []):
                    print(f"- {m['name']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    list_models()
