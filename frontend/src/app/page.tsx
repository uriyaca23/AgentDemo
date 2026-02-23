"use client";

import { useState, useRef, useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import ApiKeyModal from "@/components/ApiKeyModal";
import ModelSelector from "@/components/ModelSelector";
import { Send, Upload, Settings2, ShieldCheck, Zap, Bot, Brain, X, ImageIcon } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string | any[];
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [model, setModel] = useState("openai/gpt-4o-mini");
  const [mode, setMode] = useState("auto");
  const [availableModels, setAvailableModels] = useState<any[]>([]);
  const [attachments, setAttachments] = useState<{ url: string, mime: string, name: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // UI states
  const [offlineMode, setOfflineMode] = useState(false);
  const [statusText, setStatusText] = useState("Connecting...");

  // Skill states
  const [showSkills, setShowSkills] = useState(false);
  const availableSkills = [
    { command: "@generate_image", description: "Generate a custom AI image from a text prompt." }
  ];

  const bottomRef = useRef<HTMLDivElement>(null);

  // Initial load
  useEffect(() => {
    fetch("http://localhost:8001/models").then(r => r.json()).then(m => {
      setAvailableModels(m);
      setStatusText("Connected");
      if (m.length > 0 && !m.find((x: any) => x.id === model)) setModel(m[0].id);
    }).catch(() => setStatusText("Backend Offline"));

    fetch("http://localhost:8001/settings/network-mode").then(r => r.json()).then(data => {
      setOfflineMode(!data.enabled);
    });
  }, []);

  // Scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Explicitly load conversation from sidebar rather than via useEffect race-conditions
  const loadConversation = async (id: string | null) => {
    if (!id) {
      setActiveConvId(null);
      setMessages([]);
      return;
    }
    setActiveConvId(id);
    try {
      const res = await fetch(`http://localhost:8001/chat/conversations/${id}`);
      const data = await res.json();
      const parsed = data.messages.map((m: any) => ({
        role: m.role,
        content: typeof m.content === "string" ? m.content : m.content[0]?.text || ""
      }));
      setMessages(parsed);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSend = async () => {
    if ((!input.trim() && attachments.length === 0) || isLoading) return;

    let userContent: any = input;

    // Convert to multimodal array if attachments exist
    if (attachments.length > 0) {
      userContent = [];
      if (input.trim()) {
        userContent.push({ type: "text", text: input });
      }
      for (const att of attachments) {
        userContent.push({
          type: "image_url",
          image_url: { url: att.url }
        });
      }
    }

    const payloadMsg = { role: "user", content: userContent };

    setInput("");
    setAttachments([]);

    // For rendering in the UI safely, we can map the complex array into a temporary structure
    // but the array itself is perfectly valid to just store in the state if we update the renderer.
    const newMessages = [...messages, payloadMsg];
    setMessages(newMessages as Message[]);
    setIsLoading(true);

    try {
      const res = await fetch("http://localhost:8001/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: newMessages,
          model: model,
          mode: mode,
          conversation_id: activeConvId
        })
      });

      if (!res.ok) throw new Error("HTTP " + res.status);

      const newConvId = res.headers.get("x-conversation-id");
      if (newConvId && newConvId !== activeConvId) setActiveConvId(newConvId);

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No reader available");

      const decoder = new TextDecoder();
      let aiText = "";
      setMessages(prev => [...prev, { role: "assistant", content: "" }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunkStr = decoder.decode(value, { stream: true });
        const lines = chunkStr.split("\n\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.substring(6);
            if (dataStr === "[DONE]") break;
            try {
              const data = JSON.parse(dataStr);
              if (data.error) {
                aiText += `\n\n> ⚠️ Error: ${data.error}\n\n`;
              } else if (data.choices && data.choices[0].delta.content) {
                aiText += data.choices[0].delta.content;
              }
              // Update last message
              setMessages(prev => {
                const copy = [...prev];
                copy[copy.length - 1].content = aiText;
                return copy;
              });
            } catch (e) {
              // ignore partial JSON from chunks if any
            }
          }
        }
      }

    } catch (error: any) {
      setMessages(prev => [...prev, { role: "assistant", content: `⚠️ Request failed: ${error.message}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleNetwork = async () => {
    const newVal = !offlineMode;
    setOfflineMode(newVal);
    await fetch("http://localhost:8001/settings/network-mode", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !newVal })
    });
    // Relist models
    const m = await fetch("http://localhost:8001/models").then(r => r.json());
    setAvailableModels(m);
    if (m.length > 0) setModel(m[0].id);
  };

  return (
    <main className="flex h-screen bg-background overflow-hidden text-foreground selection:bg-indigo-500/30">
      <ApiKeyModal />

      {/* Sidebar */}
      <div className="hidden md:block">
        <Sidebar activeId={activeConvId} onSelectConversation={loadConversation} />
      </div>

      {/* Main Chat View */}
      <div className="flex-1 flex flex-col h-full bg-[#0d1117] relative">

        {/* Header Navbar */}
        <header className="h-16 border-b border-white/5 bg-[#12141a]/80 backdrop-blur flex items-center justify-between px-6 shrink-0 z-10 sticky top-0">
          <div className="flex items-center gap-4">
            <ModelSelector models={availableModels} selectedId={model} onSelect={setModel} />
          </div>

          <div className="flex items-center gap-3">
            <div className="flex bg-black/40 rounded-lg p-1 border border-white/5">
              {['auto', 'fast', 'thinking', 'pro'].map(m => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-4 py-1.5 rounded-md text-xs font-semibold capitalize transition-all flex items-center gap-1.5 ${mode === m ? 'bg-indigo-600 text-white shadow-lg' : 'text-white/40 hover:text-white/80'}`}
                >
                  {m === 'auto' && <Bot size={14} />}
                  {m === 'fast' && <Zap size={14} />}
                  {m === 'thinking' && <Brain size={14} />}
                  {m === 'pro' && <ShieldCheck size={14} />}
                  {m}
                </button>
              ))}
            </div>

            <button
              onClick={toggleNetwork}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors border ${offlineMode ? 'bg-red-500/10 text-red-400 border-red-500/20' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'}`}
            >
              <div className={`w-2 h-2 rounded-full ${offlineMode ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]' : 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)] animate-pulse'}`} />
              {offlineMode ? 'Offline Mode' : 'Online'}
            </button>
          </div>
        </header>

        {/* Chat History */}
        <div className="flex-1 overflow-y-auto p-6 md:p-12 pb-32 space-y-8 custom-scrollbar scroll-smooth">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto opacity-70">
              <div className="w-16 h-16 bg-indigo-500/10 rounded-2xl border border-indigo-500/20 flex items-center justify-center mb-6">
                <Bot size={32} className="text-indigo-400" />
              </div>
              <h2 className="text-2xl font-bold mb-3 text-white">How can I assist you?</h2>
              <p className="text-white/50 text-sm leading-relaxed mb-8">
                I am an enterprise LLM agent. Type a message below, use \`@generate_image\` to create graphics, or browse the web context.
              </p>
              <div className="flex gap-2 flex-wrap justify-center">
                <span className="text-xs px-3 py-1.5 rounded-full bg-white/5 border border-white/5 text-white/60 font-mono">@generate_image</span>
                <span className="text-xs px-3 py-1.5 rounded-full bg-white/5 border border-white/5 text-white/60 font-mono">/search</span>
              </div>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'} group animate-in slide-in-from-bottom-2 fade-in duration-300`}>
                <div className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-6 py-4 relative shadow-xl ${m.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-tr-sm border border-indigo-500 font-medium'
                  : 'bg-[#1a1d24] text-white/90 rounded-tl-sm border border-white/5'
                  }`}>
                  {m.role === 'user' ? (
                    <div className="whitespace-pre-wrap">
                      {typeof m.content === 'string' ? m.content : (
                        <div className="flex flex-col gap-2">
                          <div>{m.content.find((c: any) => c.type === 'text')?.text}</div>
                          <div className="flex gap-2 flex-wrap mt-2">
                            {m.content.filter((c: any) => c.type === 'image_url').map((img: any, idx: number) => (
                              <img key={idx} src={img.image_url.url} alt="Attachment" className="max-w-[200px] max-h-[200px] rounded-lg border border-white/20 object-cover shadow-md" />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <MarkdownRenderer content={m.content as string} />
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} className="h-4" />
        </div>

        {/* Input Area */}
        <div className="absolute bottom-0 w-full bg-gradient-to-t from-[#0d1117] via-[#0d1117]/95 to-transparent p-6 z-20">
          <div className="max-w-4xl mx-auto relative group flex flex-col gap-2">

            {/* Attachment Previews */}
            {attachments.length > 0 && (
              <div className="flex gap-3 overflow-x-auto pb-2 px-2 custom-scrollbar">
                {attachments.map((att, idx) => (
                  <div key={idx} className="relative group/att shrink-0">
                    <img src={att.url} alt="Preview" className="w-16 h-16 object-cover rounded-xl border border-white/10 shadow-lg" />
                    <button
                      onClick={() => setAttachments(prev => prev.filter((_, i) => i !== idx))}
                      className="absolute -top-2 -right-2 bg-red-500 hover:bg-red-400 text-white rounded-full p-1 opacity-0 group-hover/att:opacity-100 transition-opacity shadow-lg"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <input
              type="file"
              ref={fileInputRef}
              className="hidden"
              multiple
              accept="image/*"
              onChange={(e) => {
                const files = e.target.files;
                if (!files) return;

                Array.from(files).forEach(file => {
                  const reader = new FileReader();
                  reader.onload = (ev) => {
                    const url = ev.target?.result as string;
                    setAttachments(prev => [...prev, { url, mime: file.type, name: file.name }]);
                  };
                  reader.readAsDataURL(file);
                });
                // Reset input so the same file can be selected again if removed
                e.target.value = '';
              }}
            />

            <div className="relative">

              {/* Skills Popup */}
              {showSkills && (
                <div className="absolute bottom-full left-12 mb-2 bg-[#1a1d24] border border-white/10 rounded-xl shadow-2xl p-2 w-80 animate-in slide-in-from-bottom-2 fade-in duration-200">
                  <div className="text-xs text-white/50 px-2 pb-2 mb-1 border-b border-white/5 uppercase tracking-wider font-semibold">Available Skills</div>
                  {availableSkills.map(skill => (
                    <button
                      key={skill.command}
                      data-testid={`skill-option-${skill.command.replace('@', '')}`}
                      onClick={() => {
                        const words = input.split(' ');
                        words.pop(); // remove the partial @ word
                        const newText = (words.length > 0 ? words.join(' ') + ' ' : '') + skill.command + ' ';
                        setInput(newText);
                        setShowSkills(false);
                      }}
                      className="w-full text-left p-2 hover:bg-indigo-500/20 rounded-lg transition-colors flex flex-col gap-1 border border-transparent hover:border-indigo-500/30"
                    >
                      <span className="text-indigo-400 font-mono text-sm font-semibold">{skill.command}</span>
                      <span className="text-white/60 text-xs">{skill.description}</span>
                    </button>
                  ))}
                </div>
              )}

              <textarea
                value={input}
                onChange={(e) => {
                  const val = e.target.value;
                  setInput(val);
                  const words = val.split(' ');
                  const lastWord = words[words.length - 1];
                  if (lastWord.startsWith('@')) {
                    setShowSkills(true);
                  } else {
                    setShowSkills(false);
                  }
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Message the agent..."
                className="w-full bg-[#1a1d24] border border-white/10 rounded-2xl pl-12 pr-14 py-4 focus:outline-none focus:border-indigo-500/50 hover:border-white/20 transition-colors resize-none hide-scroll shadow-2xl text-white placeholder:text-white/30"
                rows={1}
                style={{ minHeight: '60px', maxHeight: '200px' }}
                disabled={isLoading}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="absolute left-4 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/80 transition-colors w-8 h-8 flex items-center justify-center rounded-lg hover:bg-white/5"
              >
                <Upload size={18} />
              </button>
              <button
                onClick={handleSend}
                disabled={(!input.trim() && attachments.length === 0) || isLoading}
                className="absolute right-3 top-1/2 -translate-y-1/2 bg-indigo-600 hover:bg-indigo-500 text-white p-2 rounded-xl transition-all disabled:opacity-50 disabled:hover:bg-indigo-600 shadow-lg shadow-indigo-500/20"
              >
                <Send size={18} className={isLoading ? "animate-pulse" : ""} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
