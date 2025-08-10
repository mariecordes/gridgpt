import CrosswordGenerator from "@/components/crossword-generator";

export default function Home() {
  return (
    <main className="container mx-auto py-6 px-4 max-w-6xl">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">GridGPT</h1>
        <p className="text-lg text-gray-600">AI-powered Mini Crossword Generator</p>
      </div>
      <CrosswordGenerator />
      
      {/* Footer */}
      <footer className="mt-12 pt-8 border-t border-gray-200">
        <div className="text-center text-sm text-gray-500">
          <p>
            Created by{" "}
            <a 
              href="https://github.com/mariecordes" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 underline"
            >
              mariecordes
            </a>
            {" "} with ♥︎ | Inspired by{" "}
            <a 
              href="https://www.nytimes.com/crosswords/game/mini" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 underline"
            >
              NYT's The Mini Crossword
            </a>
          </p>
        </div>
      </footer>
    </main>
  );
}