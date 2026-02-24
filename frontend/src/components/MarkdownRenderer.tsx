/* eslint-disable @typescript-eslint/no-explicit-any */
/* eslint-disable @typescript-eslint/no-unused-vars */
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';
import 'katex/dist/katex.min.css';

interface MarkdownRendererProps {
    content: string;
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
    // Basic <think> tag pre-processor to turn them into collapsible details segments
    const preprocessMarkdown = (text: string) => {
        let processed = text;
        const thinkRegex = /<think>([\s\S]*?)<\/think>/g;
        processed = processed.replace(thinkRegex, (match, p1) => {
            return `\n<details class="mb-4 bg-black/30 border border-indigo-500/20 rounded-lg overflow-hidden">\n<summary class="cursor-pointer select-none bg-indigo-500/10 px-4 py-2 text-indigo-300 font-medium hover:bg-indigo-500/20 transition-colors flex items-center outline-none">Thinking Process</summary>\n<div class="p-4 text-white/70 whitespace-pre-wrap text-sm border-t border-indigo-500/20">\n\n${p1.trim()}\n\n</div>\n</details>\n`;
        });

        // Handle unclosed <think> tag gracefully if stream is still going
        const openThinkRegex = /<think>(?!.*<\/think>)([\s\S]*)$/i;
        processed = processed.replace(openThinkRegex, (match, p1) => {
            return `\n<details open class="mb-4 bg-black/30 border border-indigo-500/20 rounded-lg overflow-hidden animate-pulse">\n<summary class="cursor-pointer select-none bg-indigo-500/20 px-4 py-2 text-indigo-300 font-medium flex items-center outline-none">Thinking (In Progress...)</summary>\n<div class="p-4 text-white/70 whitespace-pre-wrap text-sm border-t border-indigo-500/20">\n\n${p1.trim()}\n\n</div>\n</details>\n`;
        });

        // Hide leaked DSML tool call tags from DeepSeek / OpenRouter
        const dsmlRegex = /<\s*\|\s*DSML\s*\|[\s\S]*?(?:<\s*\/\s*\|\s*DSML\s*\|\s*[a-zA-Z_]+\s*>|<\s*\/\s*\|\s*DSML\s*\|\s*function_calls\s*>)/gi;
        processed = processed.replace(dsmlRegex, '');
        // Sometimes tags stream incompletely at the end, clean up dangling partial tags
        const partialDsml = /<\s*\|\s*DSML\s*\|[\s\S]*$/i;
        processed = processed.replace(partialDsml, '');

        // Fix LaTeX blocks: replace \[ ... \] with $$ ... $$
        processed = processed.replace(/\\\[/g, '$$$$');
        processed = processed.replace(/\\\]/g, '$$$$');
        // Fix inline LaTeX: replace \( ... \) with $ ... $
        processed = processed.replace(/\\\(/g, '$$');
        processed = processed.replace(/\\\)/g, '$$');

        return processed;
    };

    return (
        <div className="prose prose-invert max-w-none break-words leading-relaxed
            prose-p:text-white/80 prose-headings:text-white prose-strong:text-white
            prose-code:bg-white/10 prose-code:text-indigo-200 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:before:content-none prose-code:after:content-none
            prose-pre:bg-[#0d1117] prose-pre:border prose-pre:border-white/10 prose-pre:shadow-xl
            prose-a:text-indigo-400 hover:prose-a:text-indigo-300 prose-a:no-underline
            prose-ul:text-white/80 prose-ol:text-white/80
            prose-img:rounded-xl prose-img:shadow-2xl prose-img:border prose-img:border-white/10">
            <ReactMarkdown
                remarkPlugins={[remarkMath, remarkGfm]}
                rehypePlugins={[rehypeKatex, rehypeRaw]}
                components={{
                    // Allow raw HTML for our custom <details> block
                    p: ({ node, children, ...props }) => {
                        // Very rough un-escaping logic to allow our think block html to render as a normal block if it was strings
                        return <p className="mb-4 last:mb-0" {...props}>{children}</p>
                    },
                    code: ({ node, inline, className, children, ...props }: any) => {
                        return (
                            <code className={className} {...props}>
                                {children}
                            </code>
                        );
                    }
                }}
            >
                {preprocessMarkdown(content)}
            </ReactMarkdown>
        </div>
    );
}
