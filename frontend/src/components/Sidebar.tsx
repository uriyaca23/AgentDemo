"use client"

import { MessageSquarePlus, MessageSquare, Settings, Search, Globe } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { useAppState, Conversation } from "@/lib/AppStateContext";

export default function Sidebar() {
    const {
        isOffline, setIsOffline,
        currentConversationId, setCurrentConversationId,
        messages, setMessages,
        refreshHistoryTrigger
    } = useAppState();

    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [searchTerm, setSearchTerm] = useState("");

    // Fetch conversations
    useEffect(() => {
        async function fetchHistory() {
            try {
                const res = await fetch("http://localhost:8001/chat/conversations");
                if (res.ok) {
                    const data = await res.json();
                    setConversations(data);
                }
            } catch (err) {
                console.error("Failed to fetch history:", err);
            }
        }
        fetchHistory();
    }, [refreshHistoryTrigger]);

    // Handle offline toggle
    const handleOfflineToggle = async () => {
        const newState = !isOffline;
        try {
            await fetch("http://localhost:8001/settings/network-mode", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_enabled: !newState }) // API expects "enabled" logic where Offline is disabled network
            });
            setIsOffline(newState);
        } catch (err) {
            console.error("Failed to toggle network mode:", err);
            setIsOffline(newState); // Optimistic UI update even if backend fails
        }
    };

    // Start a new chat
    const handleNewChat = () => {
        setCurrentConversationId(null);
        setMessages([]);
    };

    // Select an existing chat
    const handleSelectChat = async (id: string) => {
        try {
            const res = await fetch(`http://localhost:8001/chat/conversations/${id}`);
            if (res.ok) {
                const data = await res.json();
                setCurrentConversationId(id);
                setMessages(data.messages || []);
            }
        } catch (err) {
            console.error("Failed to load conversation:", err);
        }
    };

    const filteredConversations = conversations.filter(c =>
        c.title?.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const getMessageText = (content: string | any[]) => {
        if (typeof content === 'string') return content;
        if (Array.isArray(content)) {
            const textItem = content.find(item => item.type === 'text');
            return textItem ? textItem.text : "Image...";
        }
        return "";
    };

    return (
        <div className="w-[280px] h-full bg-sidebar text-foreground flex flex-col p-3 transition-all duration-300">

            {/* New Chat Button */}
            <button
                onClick={handleNewChat}
                className="flex items-center gap-2 w-full px-4 py-3 bg-primary/10 hover:bg-primary/20 text-primary rounded-xl font-medium transition-colors border border-primary/20 hover:border-primary/40 group"
            >
                <MessageSquarePlus size={18} className="group-hover:scale-110 transition-transform" />
                <span className="flex-1 text-left">New Chat</span>
            </button>

            {/* Search History */}
            <div className="mt-4 relative px-1">
                <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search history..."
                    className="w-full bg-[#161b22] focus:bg-[#1c2128] border border-transparent focus:border-border transition-colors rounded-lg py-2 pl-9 pr-3 text-sm outline-none text-foreground placeholder:text-muted-foreground"
                />
            </div>

            {/* History List */}
            <div className="flex-1 overflow-y-auto mt-4 space-y-1 px-1 custom-scrollbar">
                <div className="text-xs font-semibold text-muted-foreground mb-2 mt-4 px-2 tracking-wide uppercase">Recent</div>

                {/* OPTIMISTIC NEW CHAT TITLE */}
                {!currentConversationId && messages.length > 0 && (
                    <button className="flex items-center gap-3 w-full px-3 py-2.5 bg-sidebar-hover rounded-lg text-sm text-foreground transition-colors group border border-white/5 shadow-sm">
                        <MessageSquare size={16} className="text-primary shrink-0 transition-colors" />
                        <span className="truncate italic opacity-80">{getMessageText(messages[0].content).substring(0, 35) + "..."}</span>
                    </button>
                )}

                {filteredConversations.length === 0 && (messages.length === 0 || currentConversationId) ? (
                    <div className="text-sm text-muted-foreground px-3 py-2 text-center">No history found.</div>
                ) : (
                    filteredConversations.map((c) => (
                        <button
                            key={c.id}
                            onClick={() => handleSelectChat(c.id)}
                            className="flex items-center gap-3 w-full px-3 py-2.5 hover:bg-sidebar-hover rounded-lg text-sm text-foreground/80 hover:text-foreground transition-colors group"
                        >
                            <MessageSquare size={16} className="text-muted-foreground group-hover:text-foreground shrink-0 transition-colors" />
                            <span className="truncate">{c.title || `Conversation ${c.id.substring(0, 8)}`}</span>
                        </button>
                    ))
                )}
            </div>

            {/* Network & Settings Footer */}
            <div className="mt-auto px-1 pt-4 pb-1 space-y-2 border-t border-border/50">

                {/* Network Toggle */}
                <div className={cn(
                    "flex items-center justify-between px-3 py-2.5 rounded-lg border transition-all duration-300",
                    isOffline
                        ? "bg-red-500/10 border-red-500/20 text-red-400"
                        : "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
                )}>
                    <div className="flex items-center gap-2">
                        <Globe size={16} className={cn(isOffline && "opacity-50")} />
                        <span className="text-sm font-medium">{isOffline ? "Offline Mode" : "Online Mode"}</span>
                    </div>
                    <button
                        onClick={handleOfflineToggle}
                        className={cn(
                            "relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors",
                            isOffline ? "bg-red-500/30" : "bg-emerald-500"
                        )}
                    >
                        <span className={cn(
                            "pointer-events-none block h-4 w-4 rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out",
                            isOffline ? "translate-x-[-8px]" : "translate-x-[8px]"
                        )} />
                    </button>
                </div>

                {/* Settings */}
                <button className="flex items-center gap-3 w-full px-3 py-2.5 hover:bg-sidebar-hover rounded-lg text-sm text-foreground/80 hover:text-foreground transition-colors mt-2">
                    <Settings size={18} className="text-muted-foreground" />
                    <span>Settings</span>
                </button>

            </div>
        </div>
    );
}
