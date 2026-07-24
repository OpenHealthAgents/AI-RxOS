import React from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import dynamic from 'next/dynamic';

// Dynamically import to avoid SSR errors
const DockingViewerDynamic = dynamic(
  () => import('@ai-rxos/ui/DockingViewer').then((mod) => mod.DockingViewer),
  { ssr: false, loading: () => <div className="h-[500px] w-full flex items-center justify-center bg-black rounded-md text-white/50">Initializing 3D Viewer...</div> }
);

const meta: Meta<typeof DockingViewerDynamic> = {
  title: 'Scientific/DockingViewer',
  component: DockingViewerDynamic,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof DockingViewerDynamic>;

export const Default: Story = {
  args: {
    pdbUrl: 'https://models.rcsb.org/1iep.bcif', // Example URL for Imatinib bound to ABL kinase
    width: '100%',
    height: '500px',
  },
};
