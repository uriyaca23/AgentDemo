import requests
import json

base_url = "http://127.0.0.1:8001"

def test_settings(enabled: bool):
    print(f"\n--- Setting Network to {'Online' if enabled else 'Offline'} ---")
    res = requests.put(f"{base_url}/settings/network-mode", json={"enabled": enabled})
    print("Settings Response:", res.json())

def test_chat(model: str, message: str):
    print(f"\n--- Testing Chat with {model} ---")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "mode": "auto"
    }
    try:
        res = requests.post(f"{base_url}/chat", json=payload, stream=True)
        print("Response Stream:")
        for line in res.iter_lines():
            if line:
                print(line.decode('utf-8'))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Test 1: Offline mode with internal LLM (will fail since vLLM isn't running, but we can see the prompt injection in theory, though internal LLM currently errors out if vLLM is down)
    
    # Let's test OpenRouter in Online mode
    test_settings(True)
    test_chat("openai/gpt-4o-mini", "Hello, are you online? Can you search the web?")
    
    # Test OpenRouter in Offline mode
    test_settings(False)
    test_chat("openai/gpt-4o-mini", "Hello, I need you to search the web for the latest news.")
