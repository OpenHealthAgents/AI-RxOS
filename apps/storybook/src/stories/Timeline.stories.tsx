import type { Meta, StoryObj } from '@storybook/react';
import { Timeline } from '@ai-rxos/ui';

const meta: Meta<typeof Timeline> = {
  title: 'Application/Timeline',
  component: Timeline,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof Timeline>;

export const ClinicalTrial: Story = {
  args: {
    events: [
      {
        id: '1',
        title: 'Preclinical Testing Completed',
        date: 'Jan 15, 2023',
        description: 'In vitro and in vivo studies successfully concluded with promising safety profile.',
        status: 'completed',
      },
      {
        id: '2',
        title: 'IND Application Submitted',
        date: 'Mar 10, 2023',
        description: 'Investigational New Drug application submitted to the FDA for review.',
        status: 'completed',
      },
      {
        id: '3',
        title: 'Phase I Trial Initiated',
        date: 'Jun 05, 2023',
        description: 'First patient dosed in the Phase I clinical trial focusing on safety and dosage.',
        status: 'current',
      },
      {
        id: '4',
        title: 'Interim Safety Analysis',
        date: 'Sep 20, 2023',
        description: 'Scheduled safety review by the Data Monitoring Committee (DMC).',
        status: 'upcoming',
      },
      {
        id: '5',
        title: 'Phase II Trial Planned',
        date: 'Q1 2024',
        description: 'Expected initiation of efficacy studies in target patient population.',
        status: 'upcoming',
      },
    ],
  },
};

export const WithError: Story = {
  args: {
    events: [
      {
        id: '1',
        title: 'Data Collection',
        date: 'Aug 01, 2023',
        status: 'completed',
      },
      {
        id: '2',
        title: 'Pipeline Execution Failed',
        date: 'Aug 02, 2023',
        description: 'Error processing genomic sequences: Connection timeout to primary database.',
        status: 'error',
      },
    ],
  },
};
