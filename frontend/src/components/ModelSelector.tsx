/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable @typescript-eslint/no-unused-vars */
import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Search, Database, Coins } from 'lucide-react';

interface ModelInfo {
    id: string;
    name: string;
    provider: string;
    context_length?: number;
    pricing?: {
        prompt: string | number;
        completion: string | number;
    };
}

interface ModelSelectorProps {
    models: ModelInfo[];
    selectedId: string;
    onSelect: (id: string) => void;
}

export default function ModelSelector({ models, selectedId, onSelect }: ModelSelectorProps) {
    const [isOpen, setIsOpen] = useState(false);
    const [search, setSearch] = useState("");
    const dropdownRef = useRef<HTMLDivElement>(null);

    const selectedModel = models.find(m => m.id === selectedId) || models[0];

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    const filtered = models.filter(m =>
        m.name.toLowerCase().includes(search.toLowerCase()) ||
        m.id.toLowerCase().includes(search.toLowerCase())
    );

    const formatPrice = (p: string | number | undefined) => {
        if (p === undefined || p === null) return "Unknown";
        const num = typeof p === 'string' ? parseFloat(p) : p;
        if (num === 0) return "Free";
        return `$${(num * 1000000).toFixed(2)}/M`;
    };

    const formatContext = (c: number | undefined) => {
        if (!c) return "Unknown";
        return c >= 1000 ? `${(c / 1000).toFixed(0)}k` : c.toString();
    };

    return (
        <div className="relative" ref={dropdownRef}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center justify-between w-64 bg-black/40 border border-white/10 rounded-lg px-3 py-1.5 text-sm font-medium focus:outline-none focus:border-indigo-500/50 hover:bg-black/60 transition-colors text-white"
                data-testid="model-selector-button"
            >
                <div className="truncate text-left flex-1" data-testid="selected-model-name" title={selectedModel ? selectedModel.id : ""}>
                    {selectedModel ? selectedModel.name : "Loading models..."}
                </div>
                <ChevronDown size={14} className={`ml-2 text-white/50 transition-transform ${isOpen ? "rotate-180" : ""}`} />
            </button>

            {isOpen && (
                <div className="absolute top-full left-0 mt-2 w-80 bg-[#1a1d24] border border-white/10 rounded-xl shadow-2xl overflow-hidden z-50 flex flex-col max-h-[400px]">
                    <div className="p-2 border-b border-white/5 bg-black/20 shrink-0">
                        <div className="relative">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
                            <input
                                type="text"
                                placeholder="Search models..."
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                                className="w-full bg-black/40 border border-white/10 rounded-lg pl-9 pr-3 py-1.5 text-sm focus:outline-none focus:border-indigo-500/50 text-white placeholder:text-white/30"
                                data-testid="model-search-input"
                            />
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto custom-scrollbar p-1">
                        {filtered.length === 0 ? (
                            <div className="p-4 text-center text-sm text-white/40">No models found</div>
                        ) : (
                            filtered.map(m => (
                                <button
                                    key={m.id}
                                    onClick={() => {
                                        onSelect(m.id);
                                        setIsOpen(false);
                                        setSearch("");
                                    }}
                                    className={`w-full text-left px-3 py-2.5 rounded-lg mb-1 flex flex-col gap-1 transition-colors ${selectedId === m.id ? 'bg-indigo-600/20 border border-indigo-500/30' : 'hover:bg-white/5 border border-transparent'}`}
                                    data-testid={`model-option-${m.id.replace(/[^a-zA-Z0-9]/g, '-')}`}
                                >
                                    <div className="flex items-center justify-between">
                                        <span className="font-semibold text-sm text-white truncate pr-2" title={m.id}>{m.name}</span>
                                        <span className="text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider bg-white/10 text-white/60 shrink-0">
                                            {m.provider}
                                        </span>
                                    </div>

                                    <div className="flex items-center gap-3 text-xs text-white/40 mt-1">
                                        <div className="flex items-center gap-1" title="Context Length">
                                            <Database size={12} /> {formatContext(m.context_length)}
                                        </div>
                                        <div className="flex items-center gap-1" title="Prompt Price">
                                            <Coins size={12} /> In: {formatPrice(m.pricing?.prompt)}
                                        </div>
                                        <div className="flex items-center gap-1" title="Completion Price">
                                            Out: {formatPrice(m.pricing?.completion)}
                                        </div>
                                    </div>
                                </button>
                            ))
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
