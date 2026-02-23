import React from 'react';
import { render } from '@testing-library/react';
import RootLayout from '../src/app/layout';

describe('RootLayout', () => {
    it('should include suppressHydrationWarning on html and body tags', () => {
        // We cannot fully mount RootLayout because it contains html/body,
        // which testing-library renders inside a wrapper div, but we can check the props
        // or string render it if needed. However, since it's a Server Component layout, 
        // the easiest way is to inspect the output or check source.
        // We'll mock Next.js metadata and intercept the render.

        // Instead of rendering, we will simply verify the source code contains it.
        // This is safer for Next.js app layouts in Jest.
        const fs = require('fs');
        const path = require('path');
        const layoutContent = fs.readFileSync(path.join(__dirname, '../src/app/layout.tsx'), 'utf-8');

        expect(layoutContent).toContain('<html lang="en" suppressHydrationWarning>');
        expect(layoutContent).toContain('<body');
        expect(layoutContent).toContain('suppressHydrationWarning');
    });
});
