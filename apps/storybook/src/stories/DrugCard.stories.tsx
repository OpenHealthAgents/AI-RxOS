import type { Meta, StoryObj } from '@storybook/react';
import { DrugCard } from '@ai-rxos/ui';

const meta: Meta<typeof DrugCard> = {
  title: 'Scientific/DrugCard',
  component: DrugCard,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof DrugCard>;

export const Default: Story = {
  args: {
    name: 'Imatinib',
    chemblId: 'CHEMBL941',
    smiles: 'Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc4nccc(n4)c5cccnc5',
    synonyms: ['Gleevec', 'Glivec', 'STI-571', 'CGP-57148'],
    targets: ['BCR-ABL1', 'KIT', 'PDGFRA'],
    phase: 4,
    imageSrc: 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/Imatinib_structure.svg/1200px-Imatinib_structure.svg.png',
  },
};

export const Experimental: Story = {
  args: {
    name: 'Compound Alpha',
    chemblId: 'CHEMBL1234567',
    smiles: 'CC1(C)C2CCC1(C)C2(C)C(=O)O',
    targets: ['Unknown Kinase'],
    phase: 1,
  },
};
