"use client";

import { useState, useEffect } from "react";
import { Lock, Unlock, AlertCircle, Key, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export default function ApiKeyModal() {
    const [isOpen, setIsOpen] = useState(false);
    const [password, setPassword] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState("");
    const [isSuccess, setIsSuccess] = useState(false);

    useEffect(() => {
        const checkStatus = async () => {
            try {
                const res = await fetch("http://localhost:8001/settings/api-key-status");
                if (res.ok) {
                    const data = await res.json();
                    if (data.is_locked) {
                        setIsOpen(true);
                    }
                }
            } catch (err) {
                console.error("Failed to check API key status", err);
            }
        };
        checkStatus();
    }, []);

    const handleUnlock = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!password.trim()) return;

        setIsLoading(true);
        setError("");

        try {
            const res = await fetch("http://localhost:8001/settings/unlock-key", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ password })
            });

            if (res.ok) {
                setIsSuccess(true);
                setTimeout(() => {
                    setIsOpen(false);
                }, 1500);
            } else {
                const data = await res.json();
                setError(data.detail || "Incorrect password. Please try again.");
            }
        } catch (err) {
            setError("Network error. Make sure the backend is running on 8001.");
        } finally {
            setIsLoading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-md transition-opacity">
            <div className="bg-[#12141a] border border-white/10 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-300 relative">
                <div className="absolute -top-32 -right-32 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
                <div className="p-8">
                    <div className="flex justify-center mb-6">
                        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-indigo-500/20 to-purple-600/20 border border-white/5 flex items-center justify-center relative">
                            {isSuccess ? (
                                <Unlock size={28} className="text-emerald-400" />
                            ) : (
                                <Lock size={28} className="text-indigo-400" />
                            )}
                            {isSuccess && <Sparkles size={16} className="text-emerald-300 absolute -top-1 -right-1 animate-pulse" />}
                        </div>
                    </div>
                    <div className="text-center mb-8">
                        <h2 className="text-2xl font-bold tracking-tight mb-2 text-white">Unlock OpenRouter</h2>
                        <p className="text-white/60 text-sm leading-relaxed">
                            The API key is securely encrypted. Enter your password to unlock cloud models.
                        </p>
                    </div>
                    <form onSubmit={handleUnlock} className="space-y-4">
                        <div className="relative">
                            <Key size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Enter unlock password..."
                                className="w-full bg-black/40 border border-white/10 rounded-xl pl-10 pr-4 py-3 text-sm focus:outline-none focus:border-indigo-500 transition-all text-white placeholder:text-white/20 font-medium"
                                autoFocus
                                disabled={isLoading || isSuccess}
                            />
                        </div>
                        {error && (
                            <div className="flex items-center gap-2 text-red-400 text-xs bg-red-500/10 p-3 rounded-lg">
                                <AlertCircle size={14} className="shrink-0" />
                                <span>{error}</span>
                            </div>
                        )}
                        <button
                            type="submit"
                            disabled={!password.trim() || isLoading || isSuccess}
                            className={cn(
                                "w-full py-3 rounded-xl font-medium text-sm transition-all flex items-center justify-center gap-2",
                                isSuccess
                                    ? "bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/20"
                                    : "bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                            )}
                        >
                            {isLoading ? <><Loader2 size={16} className="animate-spin" /> Unlocking...</> : isSuccess ? <>Unlocked!</> : <>Unlock Key</>}
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );
}
