"use client"

import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { useMemo } from 'react';
import 'katex/dist/katex.min.css';

interface MarkdownRendererProps {
    content: string;
}

/**
 * Preprocesses LLM output to normalize all math delimiter formats
 * into the $...$ and $$...$$ format that remark-math expects.
 *
 * Models output math in many ways:
 *  1.  \( ... \)   → inline math   → $ ... $
 *  2.  \[ ... \]   → display math  → $$ ... $$
 *  3.  $ ... $     → already correct (inline)
 *  4.  $$ ... $$   → already correct (display)
 *  5.  \begin{equation} ... \end{equation}  → $$ ... $$
 *  6.  \begin{align} ... \end{align}        → $$ ... $$
 *  7.  Raw LaTeX like \frac{a}{b} on its own line → wrap in $$ ... $$
 */
function preprocessLaTeX(content: string): string {
    if (!content) return content;

    let result = content;

    // Step 1: Protect code blocks from being processed
    // Replace code blocks with placeholders, process, then restore
    const codeBlocks: string[] = [];
    result = result.replace(/(```[\s\S]*?```|`[^`\n]+`)/g, (match) => {
        codeBlocks.push(match);
        return `%%CODEBLOCK_${codeBlocks.length - 1}%%`;
    });

    // Step 2: Convert \[ ... \] to $$ ... $$ (display math)
    // Handle multiline: \[ can be on its own line
    result = result.replace(/\\\[\s*([\s\S]*?)\s*\\\]/g, (_, math) => {
        return `\n$$\n${math.trim()}\n$$\n`;
    });

    // Step 3: Convert \( ... \) to $ ... $ (inline math)
    result = result.replace(/\\\(\s*([\s\S]*?)\s*\\\)/g, (_, math) => {
        return `$${math.trim()}$`;
    });

    // Step 4: Convert \begin{environment}...\end{environment} → $$...$$
    result = result.replace(
        /\\begin\{(equation|align|align\*|gather|gather\*|multline|multline\*)\}([\s\S]*?)\\end\{\1\}/g,
        (_, env, math) => `\n$$\n\\begin{${env}}${math}\\end{${env}}\n$$\n`
    );

    // We removed the aggressive Step 5 (heuristic whole-line replacement) 
    // because it falsely matched normal text or inline code variables,
    // resulting in them rendering as raw red code blocks.

    // Step 6: Clean up any double-dollar artifacts like $$$$ → $$
    result = result.replace(/\${3,}/g, '$$');

    // Step 7: Restore code blocks
    result = result.replace(/%%CODEBLOCK_(\d+)%%/g, (_, idx) => {
        return codeBlocks[parseInt(idx)];
    });

    return result;
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
    const processedContent = useMemo(() => preprocessLaTeX(content), [content]);

    return (
        <div className="markdown-body">
            <ReactMarkdown
                remarkPlugins={[remarkMath, remarkGfm]}
                rehypePlugins={[rehypeKatex, rehypeHighlight]}
                components={{
                    // Custom code block rendering
                    code({ node, className, children, ...props }: any) {
                        const match = /language-(\w+)/.exec(className || '');
                        const isInline = !match && !className;

                        if (isInline) {
                            return (
                                <code className="inline-code" {...props}>
                                    {children}
                                </code>
                            );
                        }

                        return (
                            <div className="code-block-wrapper">
                                {match && (
                                    <div className="code-block-header">
                                        <span className="code-lang">{match[1]}</span>
                                        <button
                                            className="copy-btn"
                                            onClick={() => {
                                                const text = String(children).replace(/\n$/, '');
                                                navigator.clipboard.writeText(text);
                                            }}
                                        >
                                            Copy
                                        </button>
                                    </div>
                                )}
                                <pre className="code-block-pre">
                                    <code className={className} {...props}>
                                        {children}
                                    </code>
                                </pre>
                            </div>
                        );
                    },
                    // Tables
                    table({ children }: any) {
                        return (
                            <div className="table-wrapper">
                                <table>{children}</table>
                            </div>
                        );
                    },
                    // Images
                    img({ src, alt }: any) {
                        return (
                            <img
                                src={src}
                                alt={alt || 'image'}
                                className="chat-image"
                                loading="lazy"
                            />
                        );
                    },
                    // Links
                    a({ href, children }: any) {
                        return (
                            <a href={href} target="_blank" rel="noopener noreferrer" className="chat-link">
                                {children}
                            </a>
                        );
                    },
                }}
            >
                {processedContent}
            </ReactMarkdown>
        </div>
    );
}
