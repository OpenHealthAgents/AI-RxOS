import React, { useState, useEffect } from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import dynamic from 'next/dynamic';

// Dynamically import to avoid "window is not defined" SSR errors from react-force-graph-2d
const GraphViewerDynamic = dynamic(
  () => import('@ai-rxos/ui/GraphViewer').then((mod) => mod.GraphViewer),
  { ssr: false, loading: () => <div className="h-[600px] w-full flex items-center justify-center bg-muted rounded-md border text-muted-foreground animate-pulse">Loading Graph Engine...</div> }
);

const meta: Meta<typeof GraphViewerDynamic> = {
  title: 'Scientific/GraphViewer',
  component: GraphViewerDynamic,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof GraphViewerDynamic>;

const mockGraphData = {
  nodes: [
    { id: 'Imatinib', group: 1, color: 'hsl(var(--primary))' },
    { id: 'BCR-ABL1', group: 2, color: 'hsl(var(--destructive))' },
    { id: 'KIT', group: 2, color: 'hsl(var(--destructive))' },
    { id: 'PDGFRA', group: 2, color: 'hsl(var(--destructive))' },
    { id: 'Nilotinib', group: 1, color: 'hsl(var(--primary))' },
    { id: 'Dasatinib', group: 1, color: 'hsl(var(--primary))' },
    { id: 'SRC', group: 2, color: 'hsl(var(--destructive))' },
  ],
  links: [
    { source: 'Imatinib', target: 'BCR-ABL1', value: 10 },
    { source: 'Imatinib', target: 'KIT', value: 8 },
    { source: 'Imatinib', target: 'PDGFRA', value: 7 },
    { source: 'Nilotinib', target: 'BCR-ABL1', value: 10 },
    { source: 'Nilotinib', target: 'KIT', value: 9 },
    { source: 'Nilotinib', target: 'PDGFRA', value: 8 },
    { source: 'Dasatinib', target: 'BCR-ABL1', value: 10 },
    { source: 'Dasatinib', target: 'KIT', value: 9 },
    { source: 'Dasatinib', target: 'SRC', value: 10 },
  ],
};

export const Default: Story = {
  args: {
    data: mockGraphData,
    width: 800,
    height: 600,
  },
};
