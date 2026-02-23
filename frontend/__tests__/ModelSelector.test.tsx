import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ModelSelector from '../src/components/ModelSelector';
import '@testing-library/jest-dom';

describe('ModelSelector Component', () => {
    const mockModels = [
        { id: 'openai/gpt-4o', name: 'GPT-4o', provider: 'OpenRouter', context_length: 128000, pricing: { prompt: "0.000002", completion: "0.000006" } },
        { id: 'anthropic/claude-3', name: 'Claude 3 Opus', provider: 'Anthropic', context_length: 200000, pricing: { prompt: "0.000015", completion: "0.000075" } },
        { id: 'google/gemini', name: 'Gemini 1.5 Pro', provider: 'Google', context_length: 1000000, pricing: { prompt: "0.000001", completion: "0.000004" } }
    ];

    it('renders the selected model name', () => {
        render(<ModelSelector models={mockModels} selectedId="anthropic/claude-3" onSelect={() => { }} />);
        expect(screen.getByTestId('selected-model-name')).toHaveTextContent('Claude 3 Opus');
    });

    it('opens dropdown when clicked and shows all models', () => {
        render(<ModelSelector models={mockModels} selectedId="openai/gpt-4o" onSelect={() => { }} />);

        fireEvent.click(screen.getByTestId('model-selector-button'));

        expect(screen.getByTestId('model-option-openai-gpt-4o')).toBeInTheDocument();
        expect(screen.getByTestId('model-option-anthropic-claude-3')).toBeInTheDocument();
        expect(screen.getByTestId('model-option-google-gemini')).toBeInTheDocument();

        // Verify formatted text for context length and pricing
        expect(screen.getByText('200k')).toBeInTheDocument(); // Claude context
        expect(screen.getByText('1000k')).toBeInTheDocument(); // Gemini context
    });

    it('filters models based on search input', () => {
        render(<ModelSelector models={mockModels} selectedId="openai/gpt-4o" onSelect={() => { }} />);

        fireEvent.click(screen.getByTestId('model-selector-button'));

        const searchInput = screen.getByTestId('model-search-input');
        fireEvent.change(searchInput, { target: { value: 'gemini' } });

        expect(screen.getByText('Gemini 1.5 Pro')).toBeInTheDocument();
        expect(screen.queryByText('Claude 3 Opus')).not.toBeInTheDocument();
    });

    it('calls onSelect and closes dropdown when an option is clicked', () => {
        const mockOnSelect = jest.fn();
        render(<ModelSelector models={mockModels} selectedId="openai/gpt-4o" onSelect={mockOnSelect} />);

        fireEvent.click(screen.getByTestId('model-selector-button'));

        const option = screen.getByTestId('model-option-anthropic-claude-3');
        fireEvent.click(option);

        expect(mockOnSelect).toHaveBeenCalledWith('anthropic/claude-3');
        expect(screen.queryByTestId('model-search-input')).not.toBeInTheDocument(); // Dropdown closed
    });
});
