"use client"

import { Paperclip, Send, ArrowUp, Zap, Image as ImageIcon } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

export default function MessageInput({ onSendMessage, disabled }: { onSendMessage: (msg: string, images: string[]) => void, disabled?: boolean }) {
    const [message, setMessage] = useState("");
    const [showSkills, setShowSkills] = useState(false);
    const [images, setImages] = useState<string[]>([]);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
        }
    }, [message]);

    const handleSend = () => {
        if ((message.trim() || images.length > 0) && !disabled) {
            onSendMessage(message.trim(), images);
            setMessage("");
            setImages([]);
        }
    }

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        files.forEach(file => {
            const reader = new FileReader();
            reader.onload = (event) => {
                const base64String = event.target?.result as string;
                setImages(prev => [...prev, base64String]);
            };
            reader.readAsDataURL(file);
        });
        // Clear input to allow re-uploading the same file
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
        // Handle the slash or @ trigger for Future Skills
        if (e.key === '@' || (e.key === '/' && message.length === 0)) {
            setShowSkills(true);
        } else if (e.key === 'Escape' || e.key === 'Backspace' && message === "") {
            setShowSkills(false);
        }
    };

    const handleSkillSelect = (skill: string) => {
        setMessage((prev) => prev.replace(/[@\/]$/, '') + `@${skill} `);
        setShowSkills(false);
        textareaRef.current?.focus();
    };

    return (
        <div className="relative w-full">
            {/* Optional Skills popup menu (mimicking Gemini Nano triggers) */}
            {showSkills && (
                <div className="absolute bottom-full left-0 mb-3 w-64 bg-sidebar border border-white/10 rounded-xl shadow-2xl overflow-hidden animate-in slide-in-from-bottom-2 fade-in z-50">
                    <div className="px-3 py-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider bg-black/20">
                        Available Skills
                    </div>
                    <div className="p-1 flex flex-col">
                        <button
                            onClick={() => handleSkillSelect('local_search')}
                            className="flex items-center gap-2 px-3 py-2 hover:bg-white/5 rounded-md text-sm text-left transition-colors"
                        >
                            <Zap size={14} className="text-amber-400" />
                            <span>local_search</span>
                            <span className="ml-auto text-xs text-muted-foreground block">Find files</span>
                        </button>
                        <button
                            onClick={() => handleSkillSelect('web_browser')}
                            className="flex items-center gap-2 px-3 py-2 hover:bg-white/5 rounded-md text-sm text-left transition-colors"
                        >
                            <GlobeIcon size={14} className="text-blue-400" />
                            <span>web_browser</span>
                            <span className="ml-auto text-xs text-muted-foreground block">Search web</span>
                        </button>
                    </div>
                </div>
            )}

            {/* Input container */}
            <div className={cn("flex flex-col bg-sidebar border border-white/10 rounded-2xl p-2 pb-3 shadow-2xl focus-within:ring-1 focus-within:ring-primary/50 focus-within:border-primary/50 transition-all duration-300", disabled && "opacity-50 pointer-events-none")}>

                {/* Image Previews */}
                {images.length > 0 && (
                    <div className="flex gap-2 p-2 overflow-x-auto custom-scrollbar mb-2">
                        {images.map((img, idx) => (
                            <div key={idx} className="relative w-16 h-16 rounded-xl overflow-hidden shrink-0 border border-white/10 shadow-sm group">
                                <img src={img} alt="preview" className="w-full h-full object-cover" />
                                <button
                                    onClick={() => setImages(prev => prev.filter((_, i) => i !== idx))}
                                    className="absolute top-1 right-1 bg-black/60 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
                                </button>
                            </div>
                        ))}
                    </div>
                )}

                {/* Textbox */}
                <textarea
                    ref={textareaRef}
                    value={message}
                    onChange={(e) => {
                        setMessage(e.target.value);
                        if (!e.target.value.includes('@') && !e.target.value.includes('/')) setShowSkills(false);
                    }}
                    onKeyDown={handleKeyDown}
                    disabled={disabled}
                    placeholder="Ask anything, or type @ for skills..."
                    className="w-full bg-transparent resize-none outline-none text-foreground placeholder:text-muted-foreground py-2 px-3 text-base min-h-[44px] max-h-[200px] mb-2 custom-scrollbar"
                    rows={1}
                />

                {/* Toolbar */}
                <div className="flex items-center justify-between px-1">
                    <div className="flex items-center gap-1">
                        <button disabled={disabled} className="p-2 text-muted-foreground hover:text-foreground hover:bg-white/5 rounded-lg transition-colors group" title="Attach file">
                            <Paperclip size={18} className="group-hover:scale-110 transition-transform" />
                        </button>
                        <button onClick={() => fileInputRef.current?.click()} disabled={disabled} className="p-2 text-muted-foreground hover:text-foreground hover:bg-white/5 rounded-lg transition-colors group" title="Upload image">
                            <ImageIcon size={18} className="group-hover:scale-110 transition-transform" />
                        </button>
                        <input
                            type="file"
                            accept="image/*"
                            multiple
                            ref={fileInputRef}
                            style={{ display: 'none' }}
                            onChange={handleFileUpload}
                        />
                    </div>

                    <button
                        onClick={handleSend}
                        className={cn(
                            "p-2 rounded-xl flex items-center justify-center transition-all duration-300",
                            message.trim().length > 0 && !disabled
                                ? "bg-primary text-primary-foreground hover:bg-primary/90 hover:scale-105 shadow-lg shadow-primary/20"
                                : "bg-white/5 text-muted-foreground cursor-not-allowed"
                        )}
                        disabled={!message.trim() || disabled}
                    >
                        <ArrowUp size={20} strokeWidth={2.5} />
                    </button>
                </div>
            </div>

            <div className="text-center mt-3 text-xs text-muted-foreground/70">
                AI can make mistakes. Consider verifying important information.
            </div>
        </div>
    );
}

const GlobeIcon = ({ className, size }: { className?: string, size?: number }) => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        width={size || 24}
        height={size || 24}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
    >
        <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z" />
        <path d="M2 12H22" />
        <path d="M12 2C15.3137 2 18 6.47715 18 12C18 17.5228 15.3137 22 12 22C8.68629 22 6 17.5228 6 12C6 6.47715 8.68629 2 12 2Z" />
    </svg>
)
