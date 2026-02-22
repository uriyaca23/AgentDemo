"use client"

import { Sparkles, Zap, BrainCircuit, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppState } from "@/lib/AppStateContext";

const MODES = [
    { id: "auto", name: "Auto", icon: Sparkles, desc: "Balanced intelligence" },
    { id: "fast", name: "Fast", icon: Zap, desc: "Quickest response" },
    { id: "thinking", name: "Thinking", icon: BrainCircuit, desc: "Chain-of-thought analysis" },
    { id: "pro", name: "Pro", icon: ShieldAlert, desc: "Deepest reasoning (slow)" },
];

export default function ModeSelector() {
    const { selectedMode, setSelectedMode } = useAppState();

    return (
        <div className="flex items-center gap-1 bg-black/20 p-1 rounded-xl border border-white/5 backdrop-blur-sm self-center justify-self-center mt-4 w-fit mx-auto relative z-20">
            {MODES.map((mode) => {
                const Icon = mode.icon;
                const isActive = selectedMode === mode.id;

                return (
                    <button
                        key={mode.id}
                        onClick={() => setSelectedMode(mode.id as ReturnType<typeof useAppState>["selectedMode"])}
                        className={cn(
                            "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 relative overflow-hidden group",
                            isActive
                                ? "text-primary-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                        )}
                        title={mode.desc}
                    >
                        {isActive && (
                            <span className="absolute inset-0 bg-primary/20 bg-gradient-to-tr from-primary/80 to-purple-600/80 rounded-lg -z-10 animate-in fade-in" />
                        )}
                        <Icon size={16} className={cn(isActive && "animate-pulse-slow")} />
                        {mode.name}
                    </button>
                );
            })}
        </div>
    );
}
