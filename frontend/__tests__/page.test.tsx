import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Home from '../src/app/page';
import '@testing-library/jest-dom';

jest.mock('react-markdown', () => (props: any) => <div data-testid="markdown">{props.children}</div>);
jest.mock('remark-math', () => () => { });
jest.mock('rehype-katex', () => () => { });
jest.mock('rehype-raw', () => () => { });
jest.mock('remark-gfm', () => () => { });

global.fetch = jest.fn();

// Mock scrollIntoView to prevent JSDOM errors
window.HTMLElement.prototype.scrollIntoView = jest.fn();

describe('Chat UI Page Component', () => {
    beforeEach(() => {
        jest.clearAllMocks();

        // Default setup for the initial page load fetches
        (global.fetch as jest.Mock).mockImplementation(async (url: string) => {
            if (url.includes('/models')) {
                return { ok: true, json: async () => [{ id: 'test-model', name: 'Test', provider: 'INTERNAL' }] };
            }
            if (url.includes('/settings/network-mode')) {
                return { ok: true, json: async () => ({ enabled: true }) };
            }
            if (url.includes('/chat/conversations')) {
                return { ok: true, json: async () => [] };
            }
            if (url.includes('/settings/api-key-status')) {
                return { ok: true, json: async () => ({ is_locked: false }) };
            }
            return { ok: true, json: async () => ({}) };
        });
    });

    it('renders correctly and loads initial state', async () => {
        render(<Home />);

        await waitFor(() => {
            expect(screen.getByText('Online')).toBeInTheDocument();
        });

        // Verify onboarding screen is there when no messages
        expect(screen.getByText('How can I assist you?')).toBeInTheDocument();
    });

    it('toggles network mode correctly and ensures models do not disappear', async () => {
        render(<Home />);

        await waitFor(() => {
            expect(screen.getByText('Online')).toBeInTheDocument();
        });

        // Open drop down
        fireEvent.click(screen.getByTestId('model-selector-button'));

        await waitFor(() => {
            // Verify models are rendered
            expect(screen.getAllByText('Test').length).toBeGreaterThan(0);
        });

        // Toggle to offline
        const toggleBtn = screen.getByText('Online');
        fireEvent.click(toggleBtn);

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledWith('http://localhost:8001/settings/network-mode', expect.any(Object));
            expect(screen.getByText('Offline Mode')).toBeInTheDocument();
        });

        // The model list should be refetched by the effect logic
        expect(global.fetch).toHaveBeenCalledWith('http://localhost:8001/models');

        // Models should still remain in the dropdown menu even while Offline
        fireEvent.click(screen.getByTestId('model-selector-button'));

        await waitFor(() => {
            expect(screen.getAllByText('Test').length).toBeGreaterThan(0);
            expect(screen.queryByText('No models found')).not.toBeInTheDocument();
        });
    });

    it('can type and send a message', async () => {
        // Setup a mock SSE reader
        const mockRead = jest.fn()
            .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"choices":[{"delta":{"content":"Hello back!"}}]}\n\n') })
            .mockResolvedValueOnce({ done: true });

        const mockGetReader = jest.fn().mockReturnValue({ read: mockRead });

        (global.fetch as jest.Mock).mockImplementation(async (url: string, options) => {
            if (url.includes('/chat') && options?.method === 'POST') {
                return {
                    ok: true,
                    headers: new Headers({ 'x-conversation-id': 'new_id' }),
                    body: { getReader: mockGetReader }
                };
            }
            // Fallback for initialization
            return { ok: true, json: async () => ([]) };
        });

        render(<Home />);

        // Type in text area
        const input = await screen.findByPlaceholderText('Message the agent...');
        fireEvent.change(input, { target: { value: 'Hi' } });

        // Click send
        const sendButton = input.parentElement?.querySelector('button:last-child');
        if (sendButton) {
            fireEvent.click(sendButton);
        }

        await waitFor(() => {
            // It should display user string immediately
            expect(screen.getByText('Hi')).toBeInTheDocument();
        });

        await waitFor(() => {
            // It should parse the SSE chunk and display AI response
            expect(screen.getByText('Hello back!')).toBeInTheDocument();
        });
    });

    it('shows skill autocomplete when typing @ and completes on click', async () => {
        render(<Home />);

        const input = await screen.findByPlaceholderText('Message the agent...');
        fireEvent.change(input, { target: { value: 'Help me @gen' } });

        // Wait for popup
        await waitFor(() => {
            expect(screen.getByText('Available Skills')).toBeInTheDocument();
            expect(screen.getByTestId('skill-option-generate_image')).toBeInTheDocument();
        });

        // Click the skill
        fireEvent.click(screen.getByTestId('skill-option-generate_image'));

        // Should replace the word
        expect(input).toHaveValue('Help me @generate_image ');

        // Popup should disappear
        expect(screen.queryByText('Available Skills')).not.toBeInTheDocument();
    });

    it('attaches files and converts them into a multimodal array payload', async () => {
        // Mock fetch for send
        (global.fetch as jest.Mock).mockImplementation(async (url: string, options) => {
            if (url.includes('/chat') && options?.method === 'POST') {
                return {
                    ok: true,
                    headers: new Headers({ 'x-conversation-id': 'new_id' }),
                    body: { getReader: () => ({ read: async () => ({ done: true }) }) }
                };
            }
            return { ok: true, json: async () => ([]) };
        });

        render(<Home />);

        // Trigger file upload
        // We simulate a file being selected because the Upload button clicks a hidden input
        const fileInput = document.querySelector('input[type="file"]');
        expect(fileInput).not.toBeNull();

        const file = new File(['mockbase'], 'hello.png', { type: 'image/png' });

        // Wait for state updates naturally
        fireEvent.change(fileInput!, { target: { files: [file] } });

        // Wait for preview to appear natively parsed by JSDOM
        await waitFor(() => {
            expect(screen.getByAltText('Preview')).toBeInTheDocument();
        });

        // Add some text
        const input = await screen.findByPlaceholderText('Message the agent...');
        fireEvent.change(input, { target: { value: 'Look at this' } });

        // Click send
        const sendButton = input.parentElement?.querySelector('button:last-child');
        if (sendButton) {
            fireEvent.click(sendButton);
        }

        // Verify the payload shape
        await waitFor(() => {
            const fetchCalls = (global.fetch as jest.Mock).mock.calls;
            const chatCall = fetchCalls.find(call => call[0].includes('/chat') && call[1]?.method === 'POST');
            expect(chatCall).toBeDefined();

            const body = JSON.parse(chatCall[1].body);
            const lastMessage = body.messages[body.messages.length - 1];

            // Should be structured as a Multimodal array
            expect(Array.isArray(lastMessage.content)).toBe(true);
            expect(lastMessage.content[0].type).toBe('text');
            expect(lastMessage.content[0].text).toBe('Look at this');
            expect(lastMessage.content[1].type).toBe('image_url');
            expect(lastMessage.content[1].image_url.url).toContain('data:image/png;base64,');
        });

        // Restore
    });
});
