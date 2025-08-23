'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface CollapsibleSectionProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

function CollapsibleSection({ title, children, defaultOpen = false }: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-gray-200 last:border-b-0">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between py-3 text-left hover:bg-gray-50 transition-colors rounded-sm px-2"
      >
        <span className="font-semibold text-gray-900">{title}</span>
        {isOpen ? (
          <ChevronDown className="h-4 w-4 text-gray-500" />
        ) : (
          <ChevronRight className="h-4 w-4 text-gray-500" />
        )}
      </button>
      {isOpen && (
        <div className="pb-4 px-2 text-sm text-gray-700 leading-relaxed">
          {children}
        </div>
      )}
    </div>
  );
}

export default function CollapsibleAbout() {
  return (
    <Card className="flex-1 flex flex-col">
      <CardHeader>
        <CardTitle className="text-xl font-bold">About GridGPT</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col">
        <div className="space-y-0">
          <CollapsibleSection title="The Story" defaultOpen={true}>
            <div>
              <p className="mb-4">
                Hi fellow crossword enthusiasts! I'm Marie, a data scientist based in Berlin with a huge passion for all sorts of games and riddles – especially crosswords.
              </p>
              <p className="mb-4">
                There's something magical about that perfect "aha!" moment when a tricky clue finally clicks – it's similar to when you finally squash that elusive bug that's been haunting your code for hours, or when your data pipeline runs flawlessly from start to finish.
              </p>
              <p className="mb-4">
                So naturally, I thought: why not combine my love for puzzles with my passion for all things data and engineering?
              </p>
              <p className="font-medium text-gray-900">
                That's how GridGPT was born!
              </p>
            </div>
          </CollapsibleSection>
        </div>
      </CardContent>
    </Card>
  );
}
