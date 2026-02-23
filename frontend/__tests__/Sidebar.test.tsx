import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import Sidebar from '../src/components/Sidebar';
import '@testing-library/jest-dom';

global.fetch = jest.fn();

describe('Sidebar Component', () => {
    const mockConversations = [
        { id: '1', title: 'First Chat', created_at: '2023-01-01T00:00:00Z' },
        { id: '2', title: 'Second Chat', created_at: '2023-01-02T00:00:00Z' }
    ];

    beforeEach(() => {
        jest.clearAllMocks();
        (global.fetch as jest.Mock).mockResolvedValue({
            ok: true,
            json: async () => mockConversations
        });
    });

    it('renders correctly and fetches history on mount', async () => {
        const onSelect = jest.fn();
        render(<Sidebar onSelectConversation={onSelect} activeId={null} />);

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledWith('http://localhost:8001/chat/conversations');
        });

        expect(await screen.findByText('First Chat')).toBeInTheDocument();
        expect(screen.getByText('Second Chat')).toBeInTheDocument();
    });

    it('selects a conversation when clicked', async () => {
        const onSelect = jest.fn();
        render(<Sidebar onSelectConversation={onSelect} activeId={null} />);

        await waitFor(() => {
            expect(screen.getByText('First Chat')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByText('First Chat'));
        expect(onSelect).toHaveBeenCalledWith('1');
    });

    it('filters conversations based on search input', async () => {
        const onSelect = jest.fn();
        render(<Sidebar onSelectConversation={onSelect} activeId={null} />);

        await waitFor(() => {
            expect(screen.getByText('First Chat')).toBeInTheDocument();
        });

        const searchInput = screen.getByPlaceholderText('Search history...');
        fireEvent.change(searchInput, { target: { value: 'Second' } });

        expect(screen.queryByText('First Chat')).not.toBeInTheDocument();
        expect(screen.getByText('Second Chat')).toBeInTheDocument();
    });

    it('handles "New Chat" button click', async () => {
        const onSelect = jest.fn();
        render(<Sidebar onSelectConversation={onSelect} activeId="1" />);

        const newChatBtn = screen.getByText(/New Chat/i);
        fireEvent.click(newChatBtn);

        expect(onSelect).toHaveBeenCalledWith(null);
    });
});
