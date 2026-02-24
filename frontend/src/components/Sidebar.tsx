/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable @typescript-eslint/no-unused-vars */
import React, { useEffect, useState } from 'react';
import { MessageSquare, Plus, Search } from 'lucide-react';

interface Conversation {
    id: string;
    title: string;
    created_at: string;
}

interface SidebarProps {
    onSelectConversation: (id: string | null) => void;
    activeId: string | null;
}

export default function Sidebar({ onSelectConversation, activeId }: SidebarProps) {
    const [conversations, setConversations] = useState<Conversation[]>([]);
    const [search, setSearch] = useState("");

    useEffect(() => {
        const fetchConversations = async () => {
            try {
                const res = await fetch("http://localhost:8001/chat/conversations");
                if (res.ok) setConversations(await res.json());
            } catch (e) { console.error("Failed to load history", e); }
        };

        fetchConversations();
        // Refresh periodically 
        const interval = setInterval(fetchConversations, 5000);
        return () => clearInterval(interval);
    }, []);

    const filtered = conversations.filter(c => c.title.toLowerCase().includes(search.toLowerCase()));

    return (
        <div className="w-72 bg-[#12141a] border-r border-white/5 h-full flex flex-col hide-scroll">
            <div className="p-4 border-b border-white/5 space-y-4">
                <button
                    onClick={() => onSelectConversation(null)}
                    className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl py-3 text-sm font-medium transition-colors shadow-lg shadow-indigo-500/10"
                >
                    <Plus size={18} suppressHydrationWarning /> New Chat
                </button>
                <div className="relative">
                    <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" suppressHydrationWarning />
                    <input
                        type="text"
                        placeholder="Search history..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-indigo-500/50 text-white placeholder:text-white/30"
                    />
                </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-1 custom-scrollbar">
                <div className="text-xs font-semibold text-white/30 uppercase tracking-wider px-3 mb-2 mt-2">Recent</div>
                {filtered.map(c => (
                    <button
                        key={c.id}
                        onClick={() => onSelectConversation(c.id)}
                        className={`w-full text-left px-3 py-3 rounded-lg flex items-start gap-3 transition-colors ${activeId === c.id ? 'bg-indigo-500/10 text-indigo-300' : 'hover:bg-white/5 text-white/60 hover:text-white'}`}
                    >
                        <MessageSquare size={16} className="mt-0.5 shrink-0 opacity-70" suppressHydrationWarning />
                        <div className="truncate text-sm pr-2">
                            {c.title || "New Conversation"}
                        </div>
                    </button>
                ))}
                {filtered.length === 0 && (
                    <div className="text-center text-white/30 text-sm py-8">No matching chats.</div>
                )}
            </div>
        </div>
    );
}
