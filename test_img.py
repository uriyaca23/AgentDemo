import gradio as gr
import urllib.parse
import uuid

def respond(message, history):
    query = message.get("text", "")
    encoded = urllib.parse.quote(query)
    image_url = f"https://image.pollinations.ai/prompt/{encoded}?nologo=true&seed={uuid.uuid4().int % 1000}"
    history.append({"role": "user", "content": query})
    
    # Method 1: Markdown
    # history.append({"role": "assistant", "content": f"![Image]({image_url})"})
    
    # Method 2: HTML
    history.append({"role": "assistant", "content": f"<img src='{image_url}' style='max-width: 100%; border-radius: 8px;' alt='img' />"})
    
    return "", history

with gr.Blocks() as demo:
    cb = gr.Chatbot(type="messages", render_markdown=True)
    txt = gr.MultimodalTextbox()
    txt.submit(respond, [txt, cb], [txt, cb])

demo.launch(server_port=7862)
