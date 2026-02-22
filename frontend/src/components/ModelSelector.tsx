import React, { useEffect, useState, useMemo } from "react";
import { ChevronDown, Cpu, Sparkles, GlobeOff, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppState, ModelOption } from "@/lib/AppStateContext";

export default function ModelSelector() {
    const { isOffline, selectedModel, setSelectedModel } = useAppState();
    const [isOpen, setIsOpen] = useState(false);
    const [models, setModels] = useState<ModelOption[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");

    useEffect(() => {
        async function fetchModels() {
            try {
                // Fetch dynamic models from backend
                const res = await fetch("http://localhost:8001/models");
                if (res.ok) {
                    const data = await res.json();
                    setModels(data);
                    // Select a default model if not explicitly set
                    if (!selectedModel && data.length > 0) {
                        setSelectedModel(data[0]);
                    }
                }
            } catch (err) {
                console.error("Failed to fetch models", err);
                // Fallback models in case backend is completely down
                const fallbacks: ModelOption[] = [
                    { id: "qwen2.5-vl-72b-instruct", name: "Qwen2.5-VL-72B", provider: "internal", description: "Local model", cost_per_m: 0, context_length: 32000, intelligence: 9, speed: 7 },
                    { id: "gpt-4o", name: "GPT-4o", provider: "openrouter", description: "Cloud model", cost_per_m: 5.0, context_length: 128000, intelligence: 10, speed: 8 },
                ];
                setModels(fallbacks);
                if (!selectedModel) setSelectedModel(fallbacks[0]);
            } finally {
                setIsLoading(false);
            }
        }
        fetchModels();
    }, []);

    const filteredModels = useMemo(() => {
        if (!searchQuery.trim()) return models;
        const lowerQuery = searchQuery.toLowerCase();
        return models.filter(m =>
            m.name.toLowerCase().includes(lowerQuery) ||
            m.id.toLowerCase().includes(lowerQuery) ||
            m.provider.toLowerCase().includes(lowerQuery)
        );
    }, [models, searchQuery]);

    if (!selectedModel) return (
        <div className="h-9 px-3 bg-black/20 animate-pulse rounded-lg w-40 border border-white/5"></div>
    );

    const Icon = selectedModel.provider === 'internal' ? Cpu : Sparkles;

    return (
        <div className="relative">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="h-9 px-3 bg-black/20 hover:bg-black/40 backdrop-blur-md rounded-lg text-sm font-medium text-foreground flex items-center transition-all border border-white/10 shadow-sm"
            >
                <Icon size={16} className={cn("mr-2", selectedModel.provider === 'internal' ? 'text-primary' : 'text-purple-400')} />
                {selectedModel.name}
                <span className={cn(
                    "ml-2 text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded",
                    selectedModel.provider === 'internal' ? "bg-primary/20 text-primary-foreground" : "bg-purple-500/20 text-purple-300"
                )}>
                    {selectedModel.provider}
                </span>
                <ChevronDown size={14} className={cn("ml-2 opacity-50 transition-transform", isOpen && "rotate-180")} />
            </button>

            {isOpen && (
                <div className="absolute top-full left-0 mt-2 w-[340px] bg-[#1e293b]/95 backdrop-blur-xl border border-white/10 rounded-xl shadow-2xl overflow-hidden z-50 animate-in fade-in slide-in-from-top-2">

                    <div className="px-3 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider bg-black/30 flex items-center justify-between border-b border-white/5">
                        <span>Available Models</span>
                        {isOffline && <span className="text-red-400 flex items-center gap-1"><GlobeOff size={12} /> Offline</span>}
                    </div>

                    <div className="p-2 border-b border-white/5 bg-black/20">
                        <div className="relative">
                            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
                            <input
                                type="text"
                                placeholder="Search models..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full bg-black/20 border border-white/10 rounded-lg pl-8 pr-3 py-1.5 text-sm outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/50 text-foreground placeholder:text-muted-foreground transition-all"
                                autoFocus
                            />
                        </div>
                    </div>

                    <div className="p-1 flex flex-col max-h-[350px] overflow-y-auto custom-scrollbar pr-1">
                        {filteredModels.length === 0 ? (
                            <div className="p-4 flex flex-col items-center justify-center text-center text-muted-foreground space-y-2">
                                <Search size={24} className="opacity-20" />
                                <p className="text-sm">No models found</p>
                            </div>
                        ) : (
                            filteredModels.map((model) => {
                                const disabled = isOffline && model.provider !== 'internal';
                                const MIcon = model.provider === 'internal' ? Cpu : Sparkles;
                                const isSelected = selectedModel.id === model.id && selectedModel.provider === model.provider;

                                return (
                                    <button
                                        key={`${model.id}-${model.provider}`}
                                        disabled={disabled}
                                        onClick={() => { setSelectedModel(model); setIsOpen(false); setSearchQuery(""); }}
                                        className={cn(
                                            "flex flex-col px-3 py-2.5 rounded-lg text-left transition-colors mb-0.5",
                                            disabled
                                                ? "opacity-40 cursor-not-allowed grayscale"
                                                : "hover:bg-white/5",
                                            isSelected && "bg-white/10 border border-white/10 shadow-sm"
                                        )}
                                    >
                                        <div className="flex items-center justify-between w-full">
                                            <span className="text-sm font-medium flex items-center gap-2 truncate pr-2">
                                                <MIcon size={14} className={cn("shrink-0", model.provider === 'internal' ? 'text-primary' : 'text-purple-400')} />
                                                <span className="truncate">{model.name}</span>
                                            </span>
                                            <span className="text-xs text-muted-foreground tracking-tight shrink-0">{Math.round(model.context_length / 1000)}K</span>
                                        </div>
                                        <div className="flex items-center justify-between mt-1.5">
                                            <span className={cn("text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded", model.provider === 'internal' ? 'bg-primary/20 text-primary-foreground' : 'bg-purple-500/20 text-purple-300')}>
                                                {model.provider === 'internal' ? 'Local' : 'OpenRouter'}
                                            </span>
                                            <span className="text-xs font-semibold text-emerald-400/90">
                                                {model.cost_per_m === 0 ? 'Free' : `$${(model.cost_per_m).toFixed(2)}/M`}
                                            </span>
                                        </div>
                                    </button>
                                )
                            })
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
