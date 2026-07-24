import type { Meta, StoryObj } from '@storybook/react';
import { Notebook } from '@ai-rxos/ui';

const meta: Meta<typeof Notebook> = {
  title: 'Application/Notebook',
  component: Notebook,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof Notebook>;

export const Default: Story = {
  args: {
    content: `
      <h2>Experiment Notes: Synthesis of Compound Alpha</h2>
      <p>Today we initiated the synthesis protocol for Compound Alpha. The initial reaction seems to be proceeding as expected.</p>
      <ul>
        <li>Reagents mixed at 25°C</li>
        <li>Stirred for 4 hours</li>
        <li>Initial color change observed from clear to pale yellow</li>
      </ul>
      <blockquote>Ensure proper ventilation during the extraction phase as minor off-gassing was noted in previous runs.</blockquote>
      <p>Next steps: Perform LC-MS tomorrow morning to verify product formation.</p>
    `,
  },
};
