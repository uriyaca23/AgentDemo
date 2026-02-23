import React from 'react';
import { render, screen } from '@testing-library/react';
import MarkdownRenderer from '../src/components/MarkdownRenderer';
import '@testing-library/jest-dom';

jest.mock('react-markdown', () => (props: any) => <div data-testid="markdown">{props.children}</div>);
jest.mock('remark-math', () => () => { });
jest.mock('rehype-katex', () => () => { });
jest.mock('rehype-raw', () => () => { });
jest.mock('remark-gfm', () => () => { });

describe('MarkdownRenderer Component', () => {
    it('renders standard markdown text inside mock', () => {
        render(<MarkdownRenderer content="**Bold Text**" />);
        expect(screen.getByTestId('markdown')).toHaveTextContent('**Bold Text**');
    });

    it('renders pre-processed <think> block gracefully', () => {
        const content = "<think>I need to process this.</think>\nFinal Answer";
        render(<MarkdownRenderer content={content} />);

        // It should preprocess into HTML string and inject it into the mock children
        const rendered = screen.getByTestId('markdown').textContent;
        expect(rendered).toContain('<summary');
        expect(rendered).toContain('Thinking Process');
        expect(rendered).toContain('I need to process this.');
        expect(rendered).toContain('Final Answer');
    });

    it('renders unclosed <think> blocks gracefully while streaming with pulse animation', () => {
        const content = "<think>Thinking about something...";
        render(<MarkdownRenderer content={content} />);

        const rendered = screen.getByTestId('markdown').textContent;
        expect(rendered).toContain('<details open class="mb-4 bg-black/30 border border-indigo-500/20 rounded-lg overflow-hidden animate-pulse">');
        expect(rendered).toContain('Thinking (In Progress...)');
        expect(rendered).toContain('Thinking about something...');
    });

    it('pre-processes LaTeX block delimiters into $$ for remark-math', () => {
        const content = "Equation: \\[ H = \\frac{p^2}{2m} \\] and inline \\( x=2 \\)";
        render(<MarkdownRenderer content={content} />);

        const rendered = screen.getByTestId('markdown').textContent;
        // remark-math needs raw $$ without the escape slashes
        expect(rendered).toContain('$$ H = \\frac{p^2}{2m} $$');
        expect(rendered).toContain('$ x=2 $');
    });
});
