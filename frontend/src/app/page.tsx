import CrosswordGenerator from "@/components/crossword-generator";
import Image from "next/image";

export default function Home() {
  return (
    <main className="container mx-auto py-6 px-4 max-w-8xl">
      <div className="text-center mb-8 flex flex-col items-center gap-3">
        <h1 className="sr-only">GridGPT</h1>
        <Image
          src="/logo.png"
          alt="GridGPT logo"
          width={250}
          height={250}
          priority
          className="drop-shadow-sm"
        />
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
              NYT&apos;s The Mini Crossword
            </a>
          </p>
        </div>
      </footer>
    </main>
  );
}