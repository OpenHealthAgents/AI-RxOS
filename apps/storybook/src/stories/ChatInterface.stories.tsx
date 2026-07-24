import type { Meta, StoryObj } from '@storybook/react';
import { ChatInterface } from '@ai-rxos/ui';

const meta: Meta<typeof ChatInterface> = {
  title: 'Application/ChatInterface',
  component: ChatInterface,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof ChatInterface>;

export const Default: Story = {
  args: {
    messages: [
      { id: '1', role: 'assistant', content: 'Hello! I am your AI-RxOS research assistant. How can I help you today?' },
      { id: '2', role: 'user', content: 'Can you show me the predicted binding affinity of Imatinib to BCR-ABL1?' },
      { id: '3', role: 'assistant', content: 'Based on the latest molecular docking simulation, Imatinib shows a strong binding affinity to the BCR-ABL1 kinase domain with an estimated ΔG of -10.5 kcal/mol. The primary interactions are hydrogen bonds with the hinge region residues (Glu286 and Met290).' },
    ],
    isLoading: false,
    onSendMessage: (msg) => console.log('Message sent:', msg),
  },
};

export const Loading: Story = {
  args: {
    messages: [
      { id: '1', role: 'assistant', content: 'Hello! I am your AI-RxOS research assistant. How can I help you today?' },
      { id: '2', role: 'user', content: 'Run a virtual screen of the top 100 compounds against this target.' },
    ],
    isLoading: true,
    onSendMessage: (msg) => console.log('Message sent:', msg),
  },
};
