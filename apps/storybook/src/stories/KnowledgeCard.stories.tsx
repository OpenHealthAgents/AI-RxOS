import type { Meta, StoryObj } from '@storybook/react';
import { KnowledgeCard } from '@ai-rxos/ui';

const meta: Meta<typeof KnowledgeCard> = {
  title: 'Scientific/KnowledgeCard',
  component: KnowledgeCard,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof KnowledgeCard>;

export const Gene: Story = {
  args: {
    title: 'BRCA1',
    type: 'Gene',
    description: 'BRCA1 (BRCA1 DNA repair associated), also known as breast cancer type 1 susceptibility protein, is a protein that in humans is encoded by the BRCA1 gene. Orthologs are common in other vertebrate species.',
    metadata: {
      Location: '17q21.31',
      MIM: '113705',
    }
  },
};

export const Disease: Story = {
  args: {
    title: 'Breast Cancer',
    type: 'Disease',
    description: 'Breast cancer is cancer that develops from breast tissue. Signs of breast cancer may include a lump in the breast, a change in breast shape, dimpling of the skin, fluid coming from the nipple, a newly inverted nipple, or a red or scaly patch of skin.',
    metadata: {
      ICD10: 'C50',
      DOID: '1612',
    }
  },
};
