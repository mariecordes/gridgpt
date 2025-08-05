import CrosswordGenerator from "@/components/crossword-generator";

export default function Home() {
  return (
    <main className="container mx-auto py-6 px-4 max-w-6xl">
      <div className="text-center mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">GridGPT</h1>
        <p className="text-lg text-gray-600">AI-powered Crossword Generator</p>
      </div>
      <CrosswordGenerator />
    </main>
  );
}