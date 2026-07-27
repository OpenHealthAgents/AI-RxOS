import type { Preview } from '@storybook/nextjs-vite'
import React from 'react'
import { ThemeProvider } from 'next-themes'
import '@ai-rxos/ui/styles.css'

const withTheme = (StoryFn: any) => {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="min-h-screen bg-background text-foreground p-4">
        <StoryFn />
      </div>
    </ThemeProvider>
  )
}

const preview: Preview = {
  decorators: [withTheme],
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      test: 'todo'
    }
  },
};

export default preview;