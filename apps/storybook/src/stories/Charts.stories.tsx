import type { Meta, StoryObj } from '@storybook/react';
import { SimpleLineChart, SimpleBarChart, SimplePieChart } from '@ai-rxos/ui';

// We'll create a meta for SimpleLineChart, but render others in stories too.
const meta: Meta<typeof SimpleLineChart> = {
  title: 'Visualization/Charts',
  component: SimpleLineChart,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof SimpleLineChart>;

const lineData = [
  { epoch: 1, loss: 0.85, accuracy: 0.52 },
  { epoch: 2, loss: 0.72, accuracy: 0.65 },
  { epoch: 3, loss: 0.55, accuracy: 0.78 },
  { epoch: 4, loss: 0.41, accuracy: 0.85 },
  { epoch: 5, loss: 0.35, accuracy: 0.89 },
  { epoch: 6, loss: 0.28, accuracy: 0.92 },
  { epoch: 7, loss: 0.22, accuracy: 0.94 },
];

export const LineChart: Story = {
  args: {
    data: lineData,
    xAxisKey: 'epoch',
    lineKey: 'loss',
  },
};

const barData = [
  { compound: 'Cmpd A', bindingAffinity: 8.5 },
  { compound: 'Cmpd B', bindingAffinity: 7.2 },
  { compound: 'Cmpd C', bindingAffinity: 9.1 },
  { compound: 'Cmpd D', bindingAffinity: 6.8 },
  { compound: 'Cmpd E', bindingAffinity: 8.9 },
];

export const BarChart: StoryObj<typeof SimpleBarChart> = {
  render: (args) => <SimpleBarChart {...args} />,
  args: {
    data: barData,
    xAxisKey: 'compound',
    barKey: 'bindingAffinity',
  },
};

const pieData = [
  { category: 'Approved', count: 45 },
  { category: 'Phase III', count: 20 },
  { category: 'Phase II', count: 35 },
  { category: 'Phase I', count: 80 },
];

export const PieChart: StoryObj<typeof SimplePieChart> = {
  render: (args) => <SimplePieChart {...args} />,
  args: {
    data: pieData,
    nameKey: 'category',
    valueKey: 'count',
  },
};
