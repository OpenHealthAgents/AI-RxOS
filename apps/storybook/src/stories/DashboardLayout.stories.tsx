import type { Meta, StoryObj } from '@storybook/react';
import { DashboardLayout } from '@ai-rxos/ui';

const meta: Meta<typeof DashboardLayout> = {
  title: 'Application/DashboardLayout',
  component: DashboardLayout,
  parameters: {
    layout: 'fullscreen',
  },
};

export default meta;
type Story = StoryObj<typeof DashboardLayout>;

export const Default: Story = {
  args: {
    sidebar: (
      <div className="p-4 space-y-2 text-sm">
        <div className="px-2 py-1 rounded bg-muted">Home</div>
        <div className="px-2 py-1 rounded hover:bg-muted/50">Knowledge Graph</div>
        <div className="px-2 py-1 rounded hover:bg-muted/50">Experiments</div>
        <div className="px-2 py-1 rounded hover:bg-muted/50">Settings</div>
      </div>
    ),
    header: <div className="text-sm font-medium">Dashboard Overview</div>,
    children: (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <div className="h-40 border rounded-lg bg-card p-4">Card 1</div>
        <div className="h-40 border rounded-lg bg-card p-4">Card 2</div>
        <div className="h-40 border rounded-lg bg-card p-4">Card 3</div>
        <div className="h-96 md:col-span-2 lg:col-span-3 border rounded-lg bg-card p-4">Main Content Area</div>
      </div>
    ),
  },
};
