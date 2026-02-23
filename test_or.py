import traceback
import urllib.request

key = "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"
url = "https://openrouter.ai/api/v1/auth/key"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})

try:
    with urllib.request.urlopen(req) as response:
        print("SUCCESS:", response.read().decode())
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code, e.reason)
    print("BODY:", e.read().decode())
except Exception as e:
    print("ERROR:", str(e))
