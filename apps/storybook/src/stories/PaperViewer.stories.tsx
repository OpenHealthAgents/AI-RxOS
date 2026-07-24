import type { Meta, StoryObj } from '@storybook/react';
import { PaperViewer } from '@ai-rxos/ui';

const meta: Meta<typeof PaperViewer> = {
  title: 'Scientific/PaperViewer',
  component: PaperViewer,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj<typeof PaperViewer>;

export const Default: Story = {
  args: {
    title: 'Attention Is All You Need',
    authors: ['Ashish Vaswani', 'Noam Shazeer', 'Niki Parmar', 'Jakob Uszkoreit', 'Llion Jones', 'Aidan N. Gomez', 'Lukasz Kaiser', 'Illia Polosukhin'],
    abstract: 'The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely. Experiments on two machine translation tasks show these models to be superior in quality while being more parallelizable and requiring significantly less time to train. Our model achieves 28.4 BLEU on the WMT 2014 English-to-German translation task, improving over the existing best results, including ensembles, by over 2 BLEU. On the WMT 2014 English-to-French translation task, our model establishes a new single-model state-of-the-art BLEU score of 41.8 after training for 3.5 days on eight GPUs, a small fraction of the training costs of the best models from the literature.',
    journal: 'Advances in Neural Information Processing Systems',
    year: '2017',
    doi: '10.48550/arXiv.1706.03762',
    pdfUrl: 'https://arxiv.org/pdf/1706.03762.pdf',
  },
};
