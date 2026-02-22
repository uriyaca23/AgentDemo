import requests
import os

key_path = "../api_key.txt"
if not os.path.exists(key_path):
    print(f"Error: API key file not found at {key_path}")
    exit(1)

with open(key_path, "r") as f:
    api_key = f.read().strip()

url = "https://openrouter.ai/api/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "HTTP-Referer": "http://localhost:8000",
    "X-Title": "Offline LLM Chat Prototype",
    "Content-Type": "application/json"
}

data = {
    "model": "openai/gpt-4o-mini", 
    "messages": [
        {"role": "user", "content": "Hello, OpenRouter!"}
    ]
}

print("Testing OpenRouter API...")
response = requests.post(url, headers=headers, json=data)

if response.status_code == 200:
    print("Success! OpenRouter API access verified.")
    print("Response:", response.json()['choices'][0]['message']['content'])
else:
    print(f"Failed with status {response.status_code}")
    print(response.text)
