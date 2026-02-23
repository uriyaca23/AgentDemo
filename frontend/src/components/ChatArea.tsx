"use client"

import { Bot, User } from "lucide-react";
import MessageInput from "./MessageInput";
import ModelSelector from "./ModelSelector";
import ModeSelector from "./ModeSelector";
import MarkdownRenderer from "./MarkdownRenderer";
import { useAppState } from "@/lib/AppStateContext";
import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

export default function ChatArea() {
    const {
        isOffline, selectedModel, selectedMode,
        currentConversationId, setCurrentConversationId,
        messages, setMessages,
        isStreaming, setIsStreaming,
        triggerHistoryRefresh
    } = useAppState();

    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages]);

    const handleSendMessage = async (text: string, images: string[] = []) => {
        if ((!text.trim() && images.length === 0) || isStreaming || !selectedModel) return;

        let contentObj: any = text.trim();
        if (images.length > 0) {
            contentObj = [];
            if (text.trim()) contentObj.push({ type: "text", text: text.trim() });
            images.forEach(img => contentObj.push({ type: "image_url", image_url: { url: img } }));
        }

        const newUserMsg = { role: "user" as const, content: contentObj };
        setMessages((prev) => [...prev, newUserMsg]);
        setIsStreaming(true);

        try {
            // Add a temporary empty assistant message to stream into
            setMessages((prev) => [...prev, { role: "assistant" as const, content: "" }]);

            const requestBody = {
                model: selectedModel.id,
                messages: [...messages, newUserMsg],
                mode: selectedMode,
                conversation_id: currentConversationId
            };

            const response = await fetch("http://localhost:8001/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(requestBody),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || "Server error");
            }

            // If we didn't have a conversation ID, the backend created one. 
            // We need to parse the headers (or a specialized SSE event) to get it. 
            // Our backend returns x-conversation-id header.
            const newConvId = response.headers.get("x-conversation-id");
            if (newConvId && !currentConversationId) {
                setCurrentConversationId(newConvId);
                triggerHistoryRefresh();
            }

            if (!response.body) throw new Error("No response body");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            let lastUpdate = Date.now();
            let accumulatedDelta = "";
            let inReasoningBlock = false;

            const flushDelta = () => {
                if (!accumulatedDelta) return;
                // Capture and clear BEFORE calling setMessages to prevent
                // React StrictMode double-invocation from appending twice
                const deltaToFlush = accumulatedDelta;
                accumulatedDelta = "";
                setMessages((prev) => {
                    const newMessages = [...prev];
                    const last = { ...newMessages[newMessages.length - 1] };
                    if (last.role === 'assistant') {
                        last.content = (last.content || "") + deltaToFlush;
                    }
                    newMessages[newMessages.length - 1] = last;
                    return newMessages;
                });
            };

            while (true) {
                const { value, done } = await reader.read();
                if (done) {
                    flushDelta();
                    break;
                }

                buffer += decoder.decode(value, { stream: true });
                const events = buffer.split("\n\n");
                buffer = events.pop() || "";

                for (const event of events) {
                    if (event.startsWith("data: ")) {
                        const data = event.substring(6);
                        if (data === "[DONE]") continue;

                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.error) {
                                throw new Error(parsed.error);
                            }
                            if (parsed.choices && parsed.choices.length > 0) {
                                const choice = parsed.choices[0];
                                // Handle reasoning_content for thinking models (e.g. DeepSeek R1)
                                const reasoning = choice.delta?.reasoning_content || choice.delta?.reasoning || "";
                                if (reasoning) {
                                    if (!inReasoningBlock) {
                                        accumulatedDelta += "<think>";
                                        inReasoningBlock = true;
                                    }
                                    accumulatedDelta += reasoning;
                                }
                                const delta = choice.delta?.content || "";
                                if (delta) {
                                    // Close thinking block if we were in one and now got content
                                    if (inReasoningBlock) {
                                        accumulatedDelta += "</think>";
                                        inReasoningBlock = false;
                                    }
                                    accumulatedDelta += delta;
                                }
                                // If finish_reason exists and we're still in reasoning, close it
                                if (choice.finish_reason && inReasoningBlock) {
                                    accumulatedDelta += "</think>";
                                    inReasoningBlock = false;
                                }
                            }
                        } catch (e) {
                            // Partial JSON, will be caught in next buffer pass
                        }
                    }
                }

                // Throttle React state commits (~30 FPS) for smooth rendering
                if (Date.now() - lastUpdate > 33 && accumulatedDelta) {
                    flushDelta();
                    lastUpdate = Date.now();
                }
            }

        } catch (error: any) {
            console.error("Chat error:", error);
            setMessages((prev) => {
                const newMessages = [...prev];
                const last = newMessages[newMessages.length - 1];
                if (last.role === 'assistant') {
                    last.content = `Error: ${error.message}. Please check if the backend Server is running.`;
                }
                return newMessages;
            });
        } finally {
            setIsStreaming(false);
            triggerHistoryRefresh();
        }
    };

    const renderTextWithThinking = (text: string) => {
        const parts = text.split(/(<think>[\s\S]*?<\/think>|<think>[\s\S]*)/);
        return parts.map((part, idx) => {
            if (part.startsWith("<think>")) {
                const inner = part.replace(/<\/?think>/g, "").trim();
                if (!inner) return null;
                const isClosed = part.endsWith("</think>");
                return (
                    <details key={idx} className="mb-3 bg-black/20 rounded-lg border border-white/5 overflow-hidden group/think" open={!isClosed}>
                        <summary className="px-3 py-2 text-[11px] font-semibold text-muted-foreground cursor-pointer hover:bg-white/5 transition-colors select-none flex items-center justify-between uppercase tracking-wider">
                            <span className="flex items-center gap-2">
                                <span className={cn("w-2 h-2 rounded-full shadow-md", isClosed ? "bg-emerald-500/50" : "bg-amber-500 animate-pulse")}></span>
                                {isClosed ? "Thought Process" : "Thinking..."}
                            </span>
                            <span className="opacity-50 group-open/think:rotate-180 transition-transform">▼</span>
                        </summary>
                        <div className="px-4 py-3 text-[14px] text-muted-foreground/90 border-t border-white/5 bg-black/10 italic">
                            <MarkdownRenderer content={inner} />
                        </div>
                    </details>
                );
            }
            if (!part.trim()) return null;
            return <MarkdownRenderer key={idx} content={part} />;
        });
    }

    const renderMessageContent = (content: string | any[]) => {
        if (typeof content === 'string') {
            return <div>{renderTextWithThinking(content)}</div>;
        }
        if (Array.isArray(content)) {
            return (
                <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap gap-2">
                        {content.filter(c => c.type === 'image_url').map((c, idx) => (
                            <img key={idx} src={c.image_url.url} alt="attached" className="max-w-[250px] max-h-[250px] object-cover rounded-lg border border-white/10 shadow-sm" />
                        ))}
                    </div>
                    {content.filter(c => c.type === 'text').map((c, idx) => (
                        <div key={`txt-${idx}`}>{renderTextWithThinking(c.text)}</div>
                    ))}
                </div>
            )
        }
        return null;
    }

    return (
        <div className="flex flex-col h-full w-full relative bg-gradient-to-br from-[#0b0c0f] to-[#12141a] overflow-hidden">

            {/* Top Header / Model Selector Area */}
            <header className="h-[60px] w-full border-b border-white/5 flex items-center px-6 justify-between bg-black/10 backdrop-blur-sm z-20 shrink-0">
                <div className="flex items-center gap-3">
                    <ModelSelector />
                </div>
                <div className="flex items-center justify-end">
                    <ModeSelector />
                </div>
            </header>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto min-h-0 px-6 py-8 space-y-8 custom-scrollbar scroll-smooth">
                {messages.length === 0 ? (
                    /* Empty State / Welcome */
                    <div className="h-full flex flex-col items-center justify-center text-center max-w-2xl mx-auto space-y-4">
                        <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-primary to-purple-600 flex items-center justify-center shadow-lg shadow-primary/20 mb-4 animate-pulse-slow">
                            <Bot size={32} className="text-white" />
                        </div>
                        <h1 className="text-3xl font-semibold tracking-tight">How can I help you today?</h1>
                        <p className="text-muted-foreground leading-relaxed">
                            I am your advanced multimodal agent. I can browse local files, analyze images, and connect with your organization's skills.
                        </p>
                    </div>
                ) : (
                    /* Message History */
                    <div className="max-w-4xl mx-auto space-y-6 pb-20">
                        {messages.map((msg, i) => (
                            <div key={i} className={cn("flex gap-4", msg.role === 'user' ? "flex-row-reverse" : "flex-row")}>
                                <div className={cn(
                                    "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-1 shadow-sm border",
                                    msg.role === 'user'
                                        ? "bg-accent/20 border-accent/30 text-accent-foreground"
                                        : "bg-primary/20 bg-gradient-to-br from-primary/50 to-purple-600/50 border-primary/30 text-primary-foreground"
                                )}>
                                    {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
                                </div>
                                <div className={cn(
                                    "px-4 py-3 rounded-2xl max-w-[85%] text-[15px] leading-relaxed",
                                    msg.role === 'user'
                                        ? "bg-user-bubble text-white rounded-tr-sm"
                                        : "bg-bot-bubble border border-white/5 text-foreground rounded-tl-sm shadow-md"
                                )}>
                                    {msg.content === "" && isStreaming && i === messages.length - 1 ? (
                                        <span className="flex gap-1 items-center h-5">
                                            <span className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                                            <span className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                                            <span className="w-1.5 h-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                                        </span>
                                    ) : (
                                        renderMessageContent(msg.content)
                                    )}
                                </div>
                            </div>
                        ))}
                        <div ref={messagesEndRef} />
                    </div>
                )}
            </div>

            {/* Input Area */}
            <div className="w-full p-4 bg-gradient-to-t from-[#0b0c0f] via-[#0b0c0f]/80 to-transparent z-20 shrink-0">
                <div className="max-w-4xl mx-auto">
                    <MessageInput onSendMessage={handleSendMessage} disabled={isStreaming} />
                </div>
            </div>
        </div>
    );
}
