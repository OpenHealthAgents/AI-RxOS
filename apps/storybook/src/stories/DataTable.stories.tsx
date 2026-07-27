import type { Meta, StoryObj } from '@storybook/react';
import { DataTable } from '@ai-rxos/ui';

const meta: Meta<typeof DataTable> = {
  title: 'Visualization/DataTable',
  component: DataTable,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof DataTable>;

const columns = [
  {
    accessorKey: 'id',
    header: 'Compound ID',
  },
  {
    accessorKey: 'name',
    header: 'Name',
  },
  {
    accessorKey: 'mw',
    header: 'Molecular Weight',
  },
  {
    accessorKey: 'logp',
    header: 'LogP',
  },
  {
    accessorKey: 'status',
    header: 'Status',
  },
];

const mockData = [
  { id: 'CHEM-001', name: 'Aspirin', mw: 180.15, logp: 1.19, status: 'Approved' },
  { id: 'CHEM-002', name: 'Imatinib', mw: 493.6, logp: 3.8, status: 'Approved' },
  { id: 'CHEM-003', name: 'Experimental-X1', mw: 350.2, logp: 2.5, status: 'Phase III' },
  { id: 'CHEM-004', name: 'Remdesivir', mw: 602.6, logp: 2.1, status: 'Approved' },
  { id: 'CHEM-005', name: 'Paxlovid', mw: 499.5, logp: 3.1, status: 'Approved' },
  { id: 'CHEM-006', name: 'Compound-Y', mw: 210.4, logp: 1.5, status: 'Preclinical' },
  { id: 'CHEM-007', name: 'Compound-Z', mw: 420.8, logp: 4.2, status: 'Phase I' },
];

export const Default: Story = {
  args: {
    columns: columns,
    data: mockData,
  },
};
