import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ApiKeyModal from '../src/components/ApiKeyModal';
import '@testing-library/jest-dom';

// Mock the global fetch
global.fetch = jest.fn();

describe('ApiKeyModal Component', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('initially does not render, fetching status automatically...', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ is_locked: false })
        });

        render(<ApiKeyModal />);
        // Wait for the effect to run
        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledWith('http://localhost:8001/settings/api-key-status');
        });

        // Should not render the modal since is_locked is false
        expect(screen.queryByText(/Unlock OpenRouter/i)).not.toBeInTheDocument();
    });

    it('renders modal when API key is locked', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ is_locked: true })
        });

        render(<ApiKeyModal />);

        await waitFor(() => {
            expect(screen.getByText(/Unlock OpenRouter/i)).toBeInTheDocument();
        });
        expect(screen.getByPlaceholderText(/Enter unlock password/i)).toBeInTheDocument();
    });

    it('shows error on wrong password', async () => {
        // 1. Initial status fetch
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ is_locked: true })
        });

        render(<ApiKeyModal />);
        await waitFor(() => {
            expect(screen.getByText(/Unlock OpenRouter/i)).toBeInTheDocument();
        });

        // 2. Mock unlock failure
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: false,
            json: async () => ({ detail: "Incorrect password. Please try again." })
        });

        const input = screen.getByPlaceholderText(/Enter unlock password/i);
        const button = screen.getByRole('button', { name: /Unlock Key/i });

        fireEvent.change(input, { target: { value: 'wrongpass' } });
        fireEvent.click(button);

        await waitFor(() => {
            expect(screen.getByText(/Incorrect password. Please try again./i)).toBeInTheDocument();
        });
    });

    it('unlocks successfully and dismisses modal', async () => {
        jest.useFakeTimers();
        // 1. Initial status fetch
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ is_locked: true })
        });

        render(<ApiKeyModal />);
        await waitFor(() => {
            expect(screen.getByText(/Unlock OpenRouter/i)).toBeInTheDocument();
        });

        // 2. Mock unlock success
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ status: "success" })
        });

        const input = screen.getByPlaceholderText(/Enter unlock password/i);
        const button = screen.getByRole('button', { name: /Unlock Key/i });

        fireEvent.change(input, { target: { value: 'Quantom2321999' } });
        fireEvent.click(button);

        await waitFor(() => {
            expect(screen.getByText(/Unlocked!/i)).toBeInTheDocument();
        });

        // Fast-forward timeout to close modal
        jest.advanceTimersByTime(1500);

        await waitFor(() => {
            expect(screen.queryByText(/Unlock OpenRouter/i)).not.toBeInTheDocument();
        });

        jest.useRealTimers();
    });
});
