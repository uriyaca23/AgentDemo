import os
import json
import httpx
from models.schemas import ChatRequest
from sqlalchemy.orm import Session
from services import history
from ddgs import DDGS
import asyncio

def get_api_key():
    key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../api_key.txt"))
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            return f.read().strip()
    return ""

async def generate_title_background(prompt: str, conv_id: str, model: str):
    api_key = get_api_key()
    if not api_key: return
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Agent V2 Setup",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a title generator. Generate a highly concise title (maximum 4 words) for the following conversation prompt. Respond with the title only, use spaces normally, and avoid quotes or conversational filler."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 10
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                title = data["choices"][0]["message"]["content"].strip().strip('"').strip("'")
                
                from database import SessionLocal
                from services import history
                db = SessionLocal()
                try:
                    history.update_conversation_title(db, conv_id, title)
                finally:
                    db.close()
        except:
            pass

async def generate_chat_openrouter(request: ChatRequest, offline_mode: bool, conv_id: str = None, db: Session = None):
    api_key = get_api_key()
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Agent V2 Setup",
        "Content-Type": "application/json"
    }

    messages = [m.model_dump() for m in request.messages]
    payload = {
        "model": request.model,
        "messages": messages,
        "stream": True
    }
    
    # Inject tool schema only if online
    if not offline_mode:
        payload["tools"] = [{
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Searches the live internet for up-to-date information, news, or facts to answer the user's prompt. Use this whenever the user asks about current events, specific recent code documentation, or facts you aren't 100% sure about.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The specific search query to look up on the web."
                        }
                    },
                    "required": ["query"]
                }
            }
        }]

    system_instruction = None
    if request.mode == "fast":
        payload["temperature"] = 0.7
        payload["max_tokens"] = 512
        system_instruction = {"role": "system", "content": "You are in FAST mode. Be highly concise and direct in your response."}
    elif request.mode == "thinking":
        payload["temperature"] = 0.2
        system_instruction = {"role": "system", "content": "You are in THINKING mode. Before answering, wrap your step-by-step reasoning inside <think>...</think> XML tags. After the closing </think> tag, provide your clear final answer."}
    elif request.mode == "auto":
        payload["temperature"] = 0.5
        system_instruction = {"role": "system", "content": "You are in AUTO mode. First, analyze the user's prompt. If it requires complex math, deep reasoning, logic puzzles, or non-trivial coding, you MUST place your step-by-step logical reasoning inside <think>...</think> XML tags before providing the final answer. If simple, answer directly without tags."}
    elif request.mode == "pro":
        payload["temperature"] = 0.5
        system_instruction = {"role": "system", "content": "You are in PRO mode. Provide an expert, nuanced, and highly detailed professional response."}
    
    if offline_mode:
        offline_instruction = "You are operating in an air-gapped, offline environment. You DO NOT have access to the internet. Do not formulate plans to search the web or provide fabricated internet links."
        if system_instruction:
            system_instruction["content"] += "\n" + offline_instruction
        else:
            system_instruction = {"role": "system", "content": offline_instruction}

    if system_instruction:
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] += "\n" + system_instruction["content"]
        else:
            messages.insert(0, system_instruction)

    full_response = ""
    tool_call_buffer = {"name": "", "arguments": "", "id": ""}
    is_calling_tool = False

    async with httpx.AsyncClient() as client:
        try:
            attempt = 0
            retry_needed = True
            while retry_needed and attempt < 2:
                retry_needed = False
                attempt += 1
                
                async with client.stream("POST", url, headers=headers, json=payload, timeout=60.0) as response:
                    if response.status_code != 200:
                        error_msg = await response.aread()
                        error_text = error_msg.decode()
                        
                        # Gracefully fallback if the model completely lacks tool-use capabilities
                        if "tools" in payload and "tool" in error_text.lower():
                            payload.pop("tools", None)
                            retry_needed = True
                            continue
                        else:
                            yield f"data: {json.dumps({'error': f'OpenRouter API Error: {error_text}'})}\n\n"
                            return
                    
                    async for chunk in response.aiter_lines():
                        if chunk:
                            if chunk.startswith("data: ") and chunk != "data: [DONE]":
                                try:
                                    data = json.loads(chunk[6:])
                                    if data.get("choices") and len(data["choices"]) > 0:
                                        delta = data["choices"][0].get("delta", {})
                                        
                                        # Check for tool_calls delta
                                        if "tool_calls" in delta and delta["tool_calls"]:
                                            is_calling_tool = True
                                            tc = delta["tool_calls"][0]
                                            if "id" in tc and tc["id"]:
                                                tool_call_buffer["id"] = tc["id"]
                                            if "function" in tc:
                                                if "name" in tc["function"] and tc["function"]["name"]:
                                                    tool_call_buffer["name"] += tc["function"]["name"]
                                                if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                                    tool_call_buffer["arguments"] += tc["function"]["arguments"]
                                            continue # Don't yield tool chunks to user yet
                                            
                                        if not is_calling_tool and "content" in delta and delta["content"]:
                                            full_response += delta["content"]
                                            yield chunk + "\n\n"
                                except json.JSONDecodeError:
                                    pass
                                
            # If the model decided to call a tool, we need to execute it and run a second completion
            if is_calling_tool and tool_call_buffer["name"] == "web_search":
                # Let user know we are searching
                search_query = ""
                try:
                    args = json.loads(tool_call_buffer["arguments"])
                    search_query = args.get("query", "")
                except: pass
                
                yield f"data: {json.dumps({'choices': [{'delta': {'content': f'\n\n> 🔍 **Searching the Web**: `{search_query}`...\n\n'}}]})}\n\n"
                
                search_results = "No results found."
                if search_query:
                    try:
                        # run duckduckgo in thread
                        def do_search():
                            with DDGS() as ddgs:
                                try:
                                    text_results = list(ddgs.text(search_query, max_results=3))
                                except: text_results = []
                                try:
                                    news_results = list(ddgs.news(search_query, max_results=3))
                                except: news_results = []
                                
                                scraped_text = ""
                                if news_results:
                                    import urllib.request
                                    from bs4 import BeautifulSoup
                                    for item in news_results[:2]:
                                        try:
                                            url = item.get("url") or item.get("href")
                                            if url:
                                                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'})
                                                html = urllib.request.urlopen(req, timeout=3.0).read()
                                                soup = BeautifulSoup(html, "html.parser")
                                                for skip in soup(["script", "style", "header", "footer", "nav", "aside"]): 
                                                    skip.decompose()
                                                scraped_text += f"-- SOURCE: {url} --\n"
                                                scraped_text += " ".join(soup.stripped_strings)[:2000] + "\n\n"
                                        except Exception:
                                            continue
                                            
                                return json.dumps({
                                    "web_results": text_results, 
                                    "news_results": news_results,
                                    "focus_article_scrape": scraped_text
                                })
                        
                        search_results = await asyncio.to_thread(do_search)
                    except Exception as e:
                        search_results = f"Search failed with error: {e}"
                        
                # Append tool call and tool result to messages for the second pass
                messages.append({
                    "role": "assistant",
                    "content": full_response if full_response else None,
                    "tool_calls": [{
                        "id": tool_call_buffer["id"],
                        "type": "function",
                        "function": {
                            "name": tool_call_buffer["name"],
                            "arguments": tool_call_buffer["arguments"]
                        }
                    }]
                })
                
                messages.append({
                    "tool_call_id": tool_call_buffer["id"],
                    "role": "tool",
                    "name": tool_call_buffer["name"],
                    "content": search_results
                })
                
                # Second API call with the results
                payload["messages"] = messages
                # Remove tools to prevent infinite loops (forcing it to answer now)
                payload.pop("tools", None) 
                
                async with client.stream("POST", url, headers=headers, json=payload, timeout=60.0) as followup_response:
                    if followup_response.status_code != 200:
                         yield f"data: {json.dumps({'error': 'Followup OpenRouter API Error.'})}\n\n"
                         return
                         
                    async for chunk in followup_response.aiter_lines():
                        if chunk and chunk.startswith("data: ") and chunk != "data: [DONE]":
                            try:
                                data = json.loads(chunk[6:])
                                if data.get("choices") and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta and delta["content"]:
                                        full_response += delta["content"]
                                        yield chunk + "\n\n"
                            except: pass

            if conv_id and db and full_response:
                db_conv = history.get_conversation(db, conv_id)
                if db_conv:
                    updated_msgs = db_conv.messages + [{"role": "assistant", "content": full_response}]
                    history.update_conversation(db, conv_id, updated_msgs)

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
