import os
import json
import httpx
from models.schemas import ChatRequest
from sqlalchemy.orm import Session
from services import history
from ddgs import DDGS
import asyncio
from settings import settings

# Cache the emulator's actual model ID to avoid repeated lookups
_emulator_model_cache: str | None = None
_resolve_lock = asyncio.Lock()

async def _resolve_emulator_model(fallback: str) -> str:
    """Auto-detect the model actually loaded in the emulator, with caching."""
    global _emulator_model_cache
    if _emulator_model_cache:
        return _emulator_model_cache
        
    async with _resolve_lock:
        # Check again after acquiring lock
        if _emulator_model_cache:
            return _emulator_model_cache
            
        try:
            url = f"{settings.get_llm_base_url().rstrip('/')}/models"
            print(f"[Model Resolve] Fetching from {url}...")
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data") and len(data["data"]) > 0:
                        resolved_id = data["data"][0]["id"]
                        print(f"[Model Resolve] Detected emulator model: {resolved_id}")
                        _emulator_model_cache = resolved_id
                        return resolved_id
                    else:
                        print(f"[Model Resolve] LLM /models returned empty data")
                else:
                    print(f"[Model Resolve] LLM /models returned {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[Model Resolve] Error: {e}")
        return fallback

def invalidate_emulator_model_cache():
    """Call when switching providers to clear the cached model ID."""
    global _emulator_model_cache
    _emulator_model_cache = None

def get_api_key():
    """Returns the API key. For internal emulator, returns a dummy key."""
    if settings.is_internal_llm():
        return "internal-emulator-key"
    key_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../api_key.txt"))
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            return f.read().strip()
    return ""

async def generate_title_background(prompt: str, conv_id: str, model: str):
    # Wait for the main chat request to start and resolve the model if needed
    await asyncio.sleep(2.0)
    
    api_key = get_api_key()
    if not api_key: return
    
    # Auto-detect the correct model when using the emulator
    actual_model = model
    if settings.is_internal_llm():
        actual_model = await _resolve_emulator_model(model)

    url = f"{settings.get_llm_base_url()}/chat/completions"
    # Robust Authorization header
    auth_val = api_key if api_key.lower().startswith("bearer ") else f"Bearer {api_key}"
    headers = {
        "Authorization": auth_val,
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Agent V2 Setup",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": "Generate a short title (3-5 words) for the following user message. Rules: output ONLY the title text, no quotes, no punctuation, no explanation. Use normal spacing between words."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 25
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=15.0)
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
            else:
                print(f"[Titling] LLM returned {response.status_code}: {response.text[:200]}")
        except Exception as e:
            print(f"[Titling] Title generation failed for conv {conv_id}: {e}")

async def generate_chat_openrouter(request: ChatRequest, offline_mode: bool, conv_id: str = None, db: Session = None):
    api_key = get_api_key()
    
    # Auto-detect the correct model when using the emulator
    # The UI-selected model ID may not match what vLLM has loaded
    actual_model = request.model
    if settings.is_internal_llm():
        actual_model = await _resolve_emulator_model(request.model)
    
    url = f"{settings.get_llm_base_url()}/chat/completions"
    # Clean and robust Authorization header
    clean_key = api_key.strip()
    auth_val = clean_key if clean_key.lower().startswith("bearer ") else f"Bearer {clean_key}"
    headers = {
        "Authorization": auth_val,
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Agent V2 Setup",
        "Content-Type": "application/json"
    }

    messages = [m.model_dump() for m in request.messages]
    payload = {
        "model": actual_model,
        "messages": messages,
        "stream": True
    }
    
    # Inject tool schema if online and NOT using the internal emulator.
    # Small internal models often hallucinate tool calls or fail to parse them, causing chat hangs.
    if not offline_mode and not settings.is_internal_llm():
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

    # Detect if the model is a native reasoning model (e.g. DeepSeek-R1, OpenAI o1/o3)
    # For these models, we should NOT inject simulated thinking instructions,
    # as they have their own internal reasoning field or specific formatting.
    m_id_low = actual_model.lower()
    is_native_reasoning = any(x in m_id_low for x in ["deepseek-r1", "openai/o1", "openai/o3", "reasoning"])
    
    system_instruction = None
    if request.mode == "fast":
        payload["temperature"] = 0.7
        payload["max_tokens"] = 512
        system_instruction = {"role": "system", "content": "You are in FAST mode. Be highly concise and direct in your response."}
    elif request.mode == "thinking":
        payload["temperature"] = 0.3 # Lower temp for more logical reasoning
        if is_native_reasoning:
            system_instruction = {"role": "system", "content": "You are a native reasoning model. Please provide your full, detailed internal chain of thought before the final answer."}
        else:
            system_instruction = {"role": "system", "content": """You are in THINKING mode. You MUST structure your response in exactly this format:

<think>
[Your exhaustive, step-by-step logical reasoning process. Break down the problem, verify constants/formulas, consider edge cases, and show all work. This section must be highly detailed.]
</think>

[Final clear answer following the closing </think> tag.]

IMPORTANT: You MUST include the <think> and </think> XML tags. Never provide an empty thinking section. If you omit the tags, your response will be rejected."""}
    elif request.mode == "auto":
        payload["temperature"] = 0.5
        system_instruction = {"role": "system", "content": "You are in AUTO mode. First, evaluate the complexity of the user's prompt. If it involves math, complex logic, coding, or deep analysis, you MUST use <think>...</think> tags for your reasoning before the final answer. If simple, answer directly."}
    elif request.mode == "pro":
        payload["temperature"] = 0.5
        system_instruction = {"role": "system", "content": "You are in PRO mode. Provide an expert, comprehensive, and highly professional response with detailed context and nuance."}
    
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
                            
                            # Give the model instructions to explain why no tool was used
                            tool_fail_msg = " [System Notice: This model does not support tool use. Apologize and explain you'll answer without searching.]"
                            if payload.get("messages") and payload["messages"][-1]["role"] == "user":
                                if isinstance(payload["messages"][-1]["content"], str):
                                    payload["messages"][-1]["content"] += tool_fail_msg
                                elif isinstance(payload["messages"][-1]["content"], list):
                                    payload["messages"][-1]["content"].append({"type": "text", "text": tool_fail_msg})

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
                                            
                                        if not is_calling_tool:
                                            # Extract potential fields
                                            delta = data["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            reasoning = delta.get("reasoning") or delta.get("thought")
                                            
                                            to_yield = None
                                            
                                            if reasoning:
                                                # Handle native reasoning
                                                if "<think>" not in full_response:
                                                    reasoning_chunk = f"<think>\n{reasoning}"
                                                    full_response += reasoning_chunk
                                                else:
                                                    full_response += reasoning
                                                    reasoning_chunk = reasoning
                                                
                                                # Create a copy for the UI that puts reasoning into content
                                                to_yield = json.loads(chunk[6:])
                                                to_yield["choices"][0]["delta"]["content"] = reasoning_chunk
                                                
                                            elif content:
                                                # Check if we were in thinking mode and need to close tags
                                                if "<think>" in full_response and "</think>" not in full_response:
                                                    content = f"\n</think>\n\n{content}"
                                                
                                                full_response += content
                                                
                                                # Create a copy if we modified the content
                                                if content != delta.get("content"):
                                                    to_yield = json.loads(chunk[6:])
                                                    to_yield["choices"][0]["delta"]["content"] = content
                                                else:
                                                    to_yield = None # Signal to yield raw chunk
                                            
                                            if to_yield:
                                                yield f"data: {json.dumps(to_yield)}\n\n"
                                            elif content or reasoning: # Yield original if it was content or reasoning in content
                                                # Safety: if content is present, ensure we yield it
                                                if content:
                                                    yield chunk + "\n\n"
                                            else:
                                                # Metadata, heartbeat, or other non-content chunks
                                                pass

                                except json.JSONDecodeError:
                                    pass
                                
            # Post-stream thinking enforcement: ensure thinking mode ALWAYS has
            # substantial content inside <think> tags.
            if request.mode == "thinking" and full_response and not is_calling_tool:
                import re as _re
                has_think = "<think>" in full_response
                # Check if think tags exist but are empty or trivially short
                think_match = _re.search(r'<think>([\s\S]*?)</think>', full_response) if has_think else None
                think_inner = think_match.group(1).strip() if think_match else ""
                
                if not has_think:
                    # Case 1: No <think> tags at all — wrap entire response
                    wrapped_think = f"<think>\n{full_response}\n</think>\n\n{full_response}"
                    yield f'data: {json.dumps({"choices": [{"delta": {"content": wrapped_think}}]})}\n\n'
                    full_response = wrapped_think
                elif len(think_inner) < 10:
                    # Case 2: <think></think> with empty/trivial content — fill it in
                    # IMPORTANT: Strip ANY existing tags (even nested ones) to avoid mess
                    # We want to remove ALL <think>...</think> occurrences
                    clean_text = _re.sub(r'</?think>', '', full_response).strip()
                    if clean_text:
                        filled = f"<think>\n{clean_text}\n</think>\n\n{clean_text}"
                    else:
                        filled = f"<think>\n{full_response}\n</think>\n\n{full_response}"
                    yield f'data: {json.dumps({"choices": [{"delta": {"content": filled}}]})}\n\n'
                    full_response = filled

            # If the model decided to call a tool, we need to execute it and run a second completion
            if is_calling_tool and tool_call_buffer["name"] == "web_search":
                # Let user know we are searching
                search_query = ""
                try:
                    args = json.loads(tool_call_buffer["arguments"])
                    search_query = args.get("query", "")
                except: pass
                
                search_msg = f"\n\n> 🔍 **Searching the Web**: `{search_query}`...\n\n"
                yield f"data: {json.dumps({'choices': [{'delta': {'content': search_msg}}]})}\n\n"
                
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
