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

    // Step 4: Convert \begin{equation}...\end{equation} → $$...$$
    result = result.replace(
        /\\begin\{(equation|align|align\*|gather|gather\*|multline|multline\*)\}([\s\S]*?)\\end\{\1\}/g,
        (_, env, math) => `\n$$\n\\begin{${env}}${math}\\end{${env}}\n$$\n`
    );

    // Step 5: Detect lines that are purely LaTeX commands (not inside $ already)
    // This catches lines like: \int_{-\infty}^{+\infty} e^{-2x^2} dx = \sqrt{\frac{\pi}{a}}
    // Pattern: line starts with a common LaTeX command and isn't already wrapped
    const latexCommands = [
        '\\int', '\\sum', '\\prod', '\\lim', '\\frac', '\\sqrt',
        '\\alpha', '\\beta', '\\gamma', '\\delta', '\\epsilon',
        '\\theta', '\\lambda', '\\mu', '\\sigma', '\\omega', '\\pi',
        '\\infty', '\\partial', '\\nabla', '\\forall', '\\exists',
        '\\mathbb', '\\mathcal', '\\mathbf', '\\mathrm', '\\text',
        '\\left', '\\right', '\\Big', '\\big', '\\cdot', '\\times',
        '\\leq', '\\geq', '\\neq', '\\approx', '\\equiv',
        '\\in', '\\subset', '\\cup', '\\cap', '\\vec',
        '\\hat', '\\bar', '\\dot', '\\ddot', '\\tilde',
    ];

    // Build a set for O(1) lookup of the command prefixes
    const cmdRegex = latexCommands.map(c => c.replace(/\\/g, '\\\\')).join('|');

    // Process line by line to catch standalone LaTeX expressions
    const lines = result.split('\n');
    const processedLines = lines.map(line => {
        const trimmed = line.trim();

        // Skip empty lines, lines already containing $, lines that are code placeholders
        if (!trimmed || trimmed.includes('$') || trimmed.startsWith('%%CODEBLOCK')) {
            return line;
        }

        // If the line is predominantly a LaTeX expression (starts with a command or
        // contains multiple LaTeX commands), wrap it as display math
        const commandMatches = trimmed.match(new RegExp(`(${cmdRegex})`, 'g'));
        if (commandMatches && commandMatches.length >= 2 && !trimmed.startsWith('#') && !trimmed.startsWith('-') && !trimmed.startsWith('*')) {
            // Line has 2+ LaTeX commands and isn't a markdown heading/list → display math
            return `$$${trimmed}$$`;
        }

        // For inline occurrences within mixed text lines, wrap individual LaTeX
        // expressions that aren't already in dollar signs
        // Match sequences like \frac{...}{...} or \int_{...}^{...} etc.
        if (commandMatches && commandMatches.length >= 1) {
            // Replace standalone LaTeX command sequences within the line with inline math
            const inlineResult = line.replace(
                new RegExp(`((?:${cmdRegex})(?:[_^]\\{[^}]*\\}|[_^]\\w|\\{[^}]*\\}|\\([^)]*\\)|[\\w\\s+\\-=*/.,])*(?:\\{[^}]*\\})*)`, 'g'),
                (match) => {
                    // Don't double-wrap if already inside $ or if it's trivially short
                    if (match.length < 3) return match;
                    return `$${match}$`;
                }
            );
            return inlineResult;
        }

        return line;
    });

    result = processedLines.join('\n');

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
