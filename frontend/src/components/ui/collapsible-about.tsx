'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface CollapsibleSectionProps {
  title: string;
  children: React.ReactNode;
  isOpen: boolean;
  onToggle: () => void;
}

function CollapsibleSection({ title, children, isOpen, onToggle }: CollapsibleSectionProps) {
  return (
    <div className="border-b border-gray-200 last:border-b-0">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between py-3 text-left transition-all duration-200 rounded-sm px-2 hover:bg-gray-50"
      >
        <span className="font-semibold text-gray-900 transition-colors duration-200">
          {title}
        </span>
        <div className="transition-transform duration-200">
          {isOpen ? (
            <ChevronDown className="h-4 w-4 text-gray-500 transition-colors duration-200" />
          ) : (
            <ChevronRight className="h-4 w-4 text-gray-500" />
          )}
        </div>
      </button>
      <div 
        className={`overflow-hidden transition-all duration-300 ease-in-out ${
          isOpen 
            ? 'max-h-screen opacity-100 transform translate-y-0' 
            : 'max-h-0 opacity-0 transform -translate-y-2'
        }`}
      >
        <div className="pb-4 px-2 text-sm text-gray-700 leading-relaxed">
          {children}
        </div>
      </div>
    </div>
  );
}

export default function CollapsibleAbout() {
  const [openSection, setOpenSection] = useState<string>('How it works'); // Default to "How it works" being open

  const handleToggle = (sectionTitle: string) => {
    setOpenSection(openSection === sectionTitle ? '' : sectionTitle);
  };

  return (
    <Card className="flex-1 flex flex-col">
      <CardHeader>
        <CardTitle className="text-xl font-bold">About GridGPT</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col">
        <div className="space-y-0">
            <CollapsibleSection 
              title="Welcome" 
              isOpen={openSection === 'Welcome'}
              onToggle={() => handleToggle('Welcome')}
            >
                <div>
                <p className="mb-4">
                    Hi fellow crossword enthusiasts! I&apos;m Marie, a data scientist based in Berlin with a huge passion for all sorts of games and riddles – especially crosswords.
                </p>
                <p className="mb-4">
                    There&apos;s something magical about that perfect &quot;aha!&quot; moment when a tricky clue finally clicks – it&apos;s similar to when you finally fix that frustrating bug that&apos;s been haunting your code for hours, or when your data pipeline runs flawlessly from start to finish.
                </p>
                <p className="mb-4">
                    So naturally, I thought: why not combine my love for puzzles with my passion for all things data and engineering?
                </p>
                <p className="font-medium text-gray-900">
                    That&apos;s how GridGPT was born!
                </p>
                </div>
            </CollapsibleSection>

            <CollapsibleSection 
              title="How it works"
              isOpen={openSection === 'How it works'}
              onToggle={() => handleToggle('How it works')}
            >
                <div>
                    <p className="mb-3">
                        GridGPT builds crosswords through a pipeline that blends real data, embeddings, optimization, and LLMs:
                    </p>
                    <p className="mb-3">
                        📚 <strong>Crossword database:</strong> A curated set of published words and clues ensures authenticity and quality.
                    </p>
                    <p className="mb-3">
                        🎯 <strong>Theme matching:</strong> Embeddings rank database words by semantic similarity to your theme, picking a strong theme entry that initializes the grid.
                    </p>
                    <p className="mb-3">
                        🤖 <strong>Backfill optimization:</strong> A custom algorithm fills the grid via constraint satisfaction, keeping every intersection valid and solvable.
                    </p>
                    <p className="mb-3">
                        ✍️ <strong>Clue generation:</strong> Choose between:
                    </p>
                    <ul className="list-disc ml-6 mb-3 space-y-2 text-sm">
                        <li>
                            <strong>Retrieved:</strong> Authentic clues randomly pulled from the database
                        </li>
                        <li>
                            <strong>Generated:</strong> LLM-generated clues, prompted for theme alignment, fairness, and wit
                        </li>
                    </ul>
                </div>
            </CollapsibleSection>
            
            <CollapsibleSection 
              title="Background"
              isOpen={openSection === 'Background'}
              onToggle={() => handleToggle('Background')}
            >
                <div>
                    <p className="mb-3">
                        I built GridGPT to mix data science optimization with LLM creativity – essentially creating a completely new, unique puzzle at the click of a button.
                    </p>
                    <p className="mb-3">
                        This is a hobby project born from curiosity: what happens when you blend algorithmic thinking with AI creativity?
                    </p>
                    <p className="mb-3">
                        Now, let me be clear – this in no way substitutes the brilliant human creativity and clever wordplay that goes into creating those delightful crosswords that professional constructors make. Human-made crosswords have soul, wit, and those perfect &quot;gotcha!&quot; moments that only come from genuine craftsmanship.
                    </p>
                    <p className="mb-3">
                        GridGPT is more like a fun experiment in computational creativity – for those moments when you want a quick puzzle fix, you&apos;re curious about a specific theme, or just seeing what an AI thinks makes a good crossword clue.
                    </p>
                    <p className="mb-3">
                        Whether you’re new to crosswords or a seasoned solver, enjoy exploring!
                    </p>
                </div>
            </CollapsibleSection> 

            <CollapsibleSection 
              title="Tech stack"
              isOpen={openSection === 'Tech stack'}
              onToggle={() => handleToggle('Tech stack')}
            >
                <div>
                <p className="mb-3">
                    <strong>Frontend:</strong> Next.js, React, TypeScript, Tailwind CSS
                </p>
                <p className="mb-3">
                    <strong>Backend:</strong> Python FastAPI with OpenAI API integration
                </p>
                <p className="mb-3">
                    <strong>Data:</strong> Scraped word database from <a href="https://www.worddb.com/" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">WordDB</a>
                </p>
                <p className="mb-3">
                    <strong>Deployment:</strong> Vercel (frontend) + Render (backend)
                </p>
                <p className="mb-3">
                    <strong>Code:</strong> Check out the repository here: <a href="https://github.com/mariecordes/gridgpt" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">gridgpt</a>
                </p>
                </div>
            </CollapsibleSection>

        </div>
      </CardContent>
    </Card>
  );
}
