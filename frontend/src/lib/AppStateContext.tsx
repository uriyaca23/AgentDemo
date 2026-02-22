"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";

// Types
export interface Message {
    role: "system" | "user" | "assistant";
    content: string | any[];
}

export interface Conversation {
    id: string;
    title: string;
    created_at: string;
    messages: Message[];
}

export interface ModelOption {
    id: string;
    name: string;
    provider: "openrouter" | "internal";
    description: string;
    cost_per_m: number;
    context_length: number;
    intelligence: number;
    speed: number;
}

export type ModeType = "auto" | "fast" | "thinking" | "pro";

interface AppStateContextType {
    // Global App States
    isOffline: boolean;
    setIsOffline: (val: boolean) => void;

    // Model & Mode Selection
    selectedModel: ModelOption | null;
    setSelectedModel: (model: ModelOption | null) => void;
    selectedMode: ModeType;
    setSelectedMode: (mode: ModeType) => void;

    // Chat States
    currentConversationId: string | null;
    setCurrentConversationId: (id: string | null) => void;
    messages: Message[];
    setMessages: (messages: Message[] | ((prev: Message[]) => Message[])) => void;
    isStreaming: boolean;
    setIsStreaming: (val: boolean) => void;

    // Triggers
    refreshHistoryTrigger: number;
    triggerHistoryRefresh: () => void;
}

const AppStateContext = createContext<AppStateContextType | undefined>(undefined);

export function AppStateProvider({ children }: { children: ReactNode }) {
    const [isOffline, setIsOffline] = useState(false);
    const [selectedModel, setSelectedModel] = useState<ModelOption | null>(null);
    const [selectedMode, setSelectedMode] = useState<ModeType>("auto");

    const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
    const [messages, setMessages] = useState<Message[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);

    const [refreshHistoryTrigger, setRefreshHistoryTrigger] = useState(0);

    const triggerHistoryRefresh = () => {
        setRefreshHistoryTrigger(prev => prev + 1);
    };

    return (
        <AppStateContext.Provider
            value={{
                isOffline, setIsOffline,
                selectedModel, setSelectedModel,
                selectedMode, setSelectedMode,
                currentConversationId, setCurrentConversationId,
                messages, setMessages,
                isStreaming, setIsStreaming,
                refreshHistoryTrigger, triggerHistoryRefresh
            }}
        >
            {children}
        </AppStateContext.Provider>
    );
}

export function useAppState() {
    const context = useContext(AppStateContext);
    if (context === undefined) {
        throw new Error("useAppState must be used within an AppStateProvider");
    }
    return context;
}
