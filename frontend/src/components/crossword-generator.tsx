'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import GridPreview from '@/components/ui/grid-preview';
import CollapsibleAbout from '@/components/ui/collapsible-about';
import { CrosswordData, GenerateRequest } from '@/lib/types';

export default function CrosswordGenerator() {
  const [formData, setFormData] = useState<GenerateRequest>({
    template: '',
    theme: '',
    themeEntry: '',
    difficulty: 'easy',
    clueType: undefined
  });
  
  const [crosswordData, setCrosswordData] = useState<CrosswordData | null>(null);
  const [userSolution, setUserSolution] = useState<{ [key: string]: string }>({});
  const [cellCorrectness, setCellCorrectness] = useState<{ [key: string]: 'correct' | 'incorrect' | 'unchecked' }>({});
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<{ correct: boolean; incorrectCount: number; totalCount: number } | null>(null);
  const [currentSlot, setCurrentSlot] = useState<string | null>(null);
  const [currentDirection, setCurrentDirection] = useState<'across' | 'down'>('across');

  const loadingMessages = [
    "📚 Finding theme-related words...",
    "🧩 Filling the crossword grid...",
    "✨ Writing clever clues...",
    "🔍 Double-checking everything...",
    "🎨 Adding finishing touches..."
  ];

  const templates = [
    { id: '5x5_blocked_corners', name: '5x5 Blocked Corners', difficulty: 'easy' },
    { id: '5x5_bottom_pillars', name: '5x5 Bottom Pillars', difficulty: 'medium' },
    { id: '5x5_diagonal_cut', name: '5x5 Diagonal Cut', difficulty: 'hard' }
  ];

  const handleInputChange = (field: keyof GenerateRequest, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const generateCrossword = async () => {
    setIsLoading(true);
    setError(null);
    setLoadingMessage(loadingMessages[0]);
    
    // Rotate through loading messages
    const messageInterval = setInterval(() => {
      setLoadingMessage(prev => {
        const currentIndex = loadingMessages.indexOf(prev);
        const nextIndex = (currentIndex + 1) % loadingMessages.length;
        return loadingMessages[nextIndex];
      });
    }, 1500);
    
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/api/generate-crossword`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to generate crossword. Please try again.');
      }

      const data = await response.json();
      setCrosswordData(data);
      setUserSolution({});
      setCellCorrectness({});
      setCheckResult(null);
      setCurrentSlot(null);
      setCurrentDirection('across');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      clearInterval(messageInterval);
      setIsLoading(false);
      setLoadingMessage('');
    }
  };

  const handleCellChange = (gridKey: string, value: string) => {
    setUserSolution(prev => ({
      ...prev,
      [gridKey]: value.toUpperCase()
    }));

    // Auto-advance to next cell in current slot
    if (value && currentSlot && crosswordData?.slots) {
      const slot = crosswordData.slots.find(s => s.id === currentSlot);
      if (slot) {
        const currentCellIndex = slot.cells.findIndex(([row, col]) => `${row}-${col}` === gridKey);
        if (currentCellIndex !== -1 && currentCellIndex < slot.cells.length - 1) {
          const nextCell = slot.cells[currentCellIndex + 1];
          const nextInput = document.querySelector(`input[data-cell="${nextCell[0]}-${nextCell[1]}"]`) as HTMLInputElement;
          if (nextInput) {
            nextInput.focus();
          }
        }
      }
    }
  };

  const handleCellClick = (gridKey: string) => {
    if (!crosswordData?.slots) return;

    const [row, col] = gridKey.split('-').map(Number);
    const slotsAtCell = crosswordData.slots.filter(slot => 
      slot.cells.some(([r, c]) => r === row && c === col)
    );

    if (slotsAtCell.length > 0) {
      // If clicking on the current slot, toggle direction
      if (currentSlot && slotsAtCell.some(s => s.id === currentSlot)) {
        const otherSlot = slotsAtCell.find(s => s.id !== currentSlot);
        if (otherSlot) {
          setCurrentSlot(otherSlot.id);
          setCurrentDirection(otherSlot.direction);
        }
      } else {
        // Default to across first, then down
        const acrossSlot = slotsAtCell.find(s => s.direction === 'across');
        const slotToSelect = acrossSlot || slotsAtCell[0];
        setCurrentSlot(slotToSelect.id);
        setCurrentDirection(slotToSelect.direction);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent, gridKey: string) => {
    if (!crosswordData?.slots) return;

    if (e.key === 'Tab') {
      e.preventDefault();
      
      // Navigate through slots
      const currentSlots = crosswordData.slots.filter(s => s.direction === currentDirection);
      const currentIndex = currentSlots.findIndex(s => s.id === currentSlot);
      
      let nextIndex;
      if (e.shiftKey) {
        nextIndex = currentIndex > 0 ? currentIndex - 1 : currentSlots.length - 1;
      } else {
        nextIndex = currentIndex < currentSlots.length - 1 ? currentIndex + 1 : 0;
      }
      
      const nextSlot = currentSlots[nextIndex];
      setCurrentSlot(nextSlot.id);
      
      // Focus on first cell of next slot
      const firstCell = nextSlot.cells[0];
      const firstInput = document.querySelector(`input[data-cell="${firstCell[0]}-${firstCell[1]}"]`) as HTMLInputElement;
      if (firstInput) {
        firstInput.focus();
      }
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      
      const [row, col] = gridKey.split('-').map(Number);
      let newRow = row;
      let newCol = col;
      
      switch (e.key) {
        case 'ArrowLeft':
          newCol = Math.max(0, col - 1);
          break;
        case 'ArrowRight':
          newCol = Math.min(4, col + 1);
          break;
        case 'ArrowUp':
          newRow = Math.max(0, row - 1);
          break;
        case 'ArrowDown':
          newRow = Math.min(4, row + 1);
          break;
      }
      
      const newInput = document.querySelector(`input[data-cell="${newRow}-${newCol}"]`) as HTMLInputElement;
      if (newInput) {
        newInput.focus();
        handleCellClick(`${newRow}-${newCol}`);
      }
    } else if (e.key === 'Backspace' && !(e.currentTarget as HTMLInputElement).value) {
      // Move to previous cell on backspace if current cell is empty
      if (currentSlot) {
        const slot = crosswordData.slots.find(s => s.id === currentSlot);
        if (slot) {
          const currentCellIndex = slot.cells.findIndex(([row, col]) => `${row}-${col}` === gridKey);
          if (currentCellIndex > 0) {
            const prevCell = slot.cells[currentCellIndex - 1];
            const prevInput = document.querySelector(`input[data-cell="${prevCell[0]}-${prevCell[1]}"]`) as HTMLInputElement;
            if (prevInput) {
              prevInput.focus();
            }
          }
        }
      }
    }
  };

  const checkSolution = () => {
    if (!crosswordData || !crosswordData.slots) return;
    
    const newCellCorrectness: { [key: string]: 'correct' | 'incorrect' | 'unchecked' } = {};
    let incorrectCount = 0;
    let totalCheckedCells = 0;
    let allCorrect = true;
    
    // Check each slot against user input (only across slots to avoid double counting)
    Object.entries(crosswordData.filled_slots).forEach(([slotId, correctAnswer]) => {
      // Only check across slots to avoid counting the same cell multiple times
      if (!slotId.includes('A')) return;
      
      // Find the slot data
      const slot = crosswordData.slots?.find(s => s.id === slotId);
      if (!slot) return;
      
      // Build the user's answer from grid cells and check each cell
      slot.cells.forEach(([row, col], index) => {
        const cellKey = `${row}-${col}`;
        const userValue = userSolution[cellKey] || '';
        const correctValue = correctAnswer[index] || '';
        
        // Count all cells in the crossword, not just filled ones
        totalCheckedCells++;
        if (userValue === correctValue && userValue !== '') {
          newCellCorrectness[cellKey] = 'correct';
        } else {
          newCellCorrectness[cellKey] = 'incorrect';
          incorrectCount++;
          allCorrect = false;
        }
      });
    });
    
    setCellCorrectness(newCellCorrectness);
    setCheckResult({ 
      correct: allCorrect && totalCheckedCells > 0, 
      incorrectCount, 
      totalCount: totalCheckedCells 
    });

    // Clear selection when all answers are correct so users can see the green feedback
    if (allCorrect && totalCheckedCells > 0) {
      setCurrentSlot(null);
    }
  };

  // Helper function to get clue numbers for a cell
  const getClueNumbers = (rowIndex: number, colIndex: number) => {
    if (!crosswordData?.slots) return [];
    
    const clueNumbers: string[] = [];
    
    // Check all slots to see if this cell is a starting position
    crosswordData.slots.forEach((slot: { id: string; start: [number, number] }) => {
      const [startRow, startCol] = slot.start;
      if (startRow === rowIndex && startCol === colIndex) {
        // Extract number from slot ID (e.g., "1A" -> "1", "10D" -> "10")
        const number = slot.id.match(/\d+/)?.[0];
        if (number && !clueNumbers.includes(number)) {
          clueNumbers.push(number);
        }
      }
    });
    
    return clueNumbers.sort((a, b) => parseInt(a) - parseInt(b));
  };

  const renderGrid = () => {
    if (!crosswordData) return null;

    return (
      <div className="grid grid-cols-5 gap-0 w-fit mx-auto border-2 border-gray-800">
        {crosswordData.grid.map((row, rowIndex) =>
          row.map((cell, colIndex) => {
            const clueNumbers = getClueNumbers(rowIndex, colIndex);
            const cellKey = `${rowIndex}-${colIndex}`;
            const correctness = cellCorrectness[cellKey];
            
            // Check if this cell is part of the currently selected slot
            const isInCurrentSlot = currentSlot && crosswordData.slots?.find(s => 
              s.id === currentSlot && s.cells.some(([r, c]) => r === rowIndex && c === colIndex)
            );
            
            // Determine cell background color based on correctness and selection
            let cellBgClass = 'bg-white hover:bg-blue-50';
            if (correctness === 'correct') {
              cellBgClass = 'bg-green-100 hover:bg-green-200';
            } else if (correctness === 'incorrect') {
              cellBgClass = 'bg-red-100 hover:bg-red-200';
            } else if (isInCurrentSlot) {
              cellBgClass = 'bg-blue-100 hover:bg-blue-150';
            }
            
            return (
              <div
                key={`${rowIndex}-${colIndex}`}
                className={`
                  w-12 h-12 border border-gray-400 relative
                  ${cell === '#' ? 'bg-black' : cellBgClass}
                `}
                onClick={() => handleCellClick(cellKey)}
              >
                {cell !== '#' && (
                  <>
                    {/* Clue number in upper-left corner */}
                    {clueNumbers.length > 0 && (
                      <div className="absolute top-0.5 left-0.5 text-xs font-bold text-gray-700 leading-none pointer-events-none z-10">
                        {clueNumbers[0]}
                      </div>
                    )}
                    
                    {/* Input field for the letter */}
                    <input
                      type="text"
                      maxLength={1}
                      data-cell={cellKey}
                      className="w-full h-full text-center border-none outline-none text-lg font-bold pt-2 bg-transparent focus:bg-yellow-100 transition-colors"
                      value={userSolution[cellKey] || ''}
                      onChange={(e) => handleCellChange(cellKey, e.target.value)}
                      onKeyDown={(e) => handleKeyDown(e, cellKey)}
                      style={{ textTransform: 'uppercase' }}
                      placeholder=""
                    />
                  </>
                )}
              </div>
            );
          })
        )}
      </div>
    );
  };

  const renderClues = () => {
    if (!crosswordData) return null;

    const acrossClues = Object.entries(crosswordData.clues).filter(([key]) => key.includes('A'));
    const downClues = Object.entries(crosswordData.clues).filter(([key]) => key.includes('D'));

    return (
      <div className="grid md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-base font-semibold mb-3">Across</h3>
          <div className="space-y-2">
            {acrossClues.map(([clueId, clue]) => (
              <div 
                key={clueId} 
                className={`text-sm p-2 rounded cursor-pointer transition-colors ${
                  currentSlot === clueId ? 'bg-blue-100 border border-blue-300' : 'hover:bg-gray-50'
                }`}
                onClick={() => {
                  setCurrentSlot(clueId);
                  setCurrentDirection('across');
                  // Focus on first cell of this slot
                  const slot = crosswordData.slots?.find(s => s.id === clueId);
                  if (slot) {
                    const firstCell = slot.cells[0];
                    const firstInput = document.querySelector(`input[data-cell="${firstCell[0]}-${firstCell[1]}"]`) as HTMLInputElement;
                    if (firstInput) {
                      firstInput.focus();
                    }
                  }
                }}
              >
                <span className="font-medium">{clueId}:</span> {clue}
              </div>
            ))}
          </div>
        </div>
        
        <div>
          <h3 className="text-base font-semibold mb-3">Down</h3>
          <div className="space-y-2">
            {downClues.map(([clueId, clue]) => (
              <div 
                key={clueId} 
                className={`text-sm p-2 rounded cursor-pointer transition-colors ${
                  currentSlot === clueId ? 'bg-blue-100 border border-blue-300' : 'hover:bg-gray-50'
                }`}
                onClick={() => {
                  setCurrentSlot(clueId);
                  setCurrentDirection('down');
                  // Focus on first cell of this slot
                  const slot = crosswordData.slots?.find(s => s.id === clueId);
                  if (slot) {
                    const firstCell = slot.cells[0];
                    const firstInput = document.querySelector(`input[data-cell="${firstCell[0]}-${firstCell[1]}"]`) as HTMLInputElement;
                    if (firstInput) {
                      firstInput.focus();
                    }
                  }
                }}
              >
                <span className="font-medium">{clueId}:</span> {clue}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col lg:flex-row gap-6 lg:gap-8 items-start">
      {/* Main Content - Left Side */}
      <div className="flex-1 lg:flex-[2] space-y-6">
        {/* Input Form */}
        <Card>
          <CardHeader>
            <CardTitle className="text-xl font-bold">Generate Crossword</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
          <div className="grid md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label className="text-base font-semibold">Template</Label>
              <Select
                value={formData.template || ''}
                onValueChange={(value) => handleInputChange('template', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select grid template" />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((template) => (
                    <SelectItem key={template.id} value={template.id}>
                      <div className="flex items-center space-x-3">
                        <GridPreview type={template.id} />
                        <span>{template.name}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label className="text-base font-semibold">Clues</Label>
              <Select
                value={formData.clueType || ''}
                onValueChange={(value) => handleInputChange('clueType', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Choose clue type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="existing">Retrieve existing clues</SelectItem>
                  <SelectItem value="generate">Generate new clues</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="theme" className="text-base font-semibold">Theme (optional)</Label>
              <Input
                id="theme"
                placeholder="e.g., food, music, space"
                value={formData.theme || ''}
                onChange={(e) => handleInputChange('theme', e.target.value)}
              />
            </div>
            
            {/* TODO: Theme entry component in case we want to make it available to the user to set their own theme entry */}
            {/* <div className="space-y-2">
              <Label htmlFor="themeEntry">Theme Entry (Optional)</Label>
              <Input
                id="themeEntry"
                placeholder="e.g., ASTRONAUT, PIZZA"
                value={formData.themeEntry || ''}
                onChange={(e) => handleInputChange('themeEntry', e.target.value)}
              />
            </div> */}

            {/* TODO: Difficulty selection for when this becomes an input parameter (e.g., for template selection, clue generation or crossword generation) */}
            {/* <div className="space-y-2">
              <Label>Difficulty</Label>
              <Select
                value={formData.difficulty || 'easy'}
                onValueChange={(value) => handleInputChange('difficulty', value as 'easy' | 'medium' | 'hard')}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="easy">Easy</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="hard">Hard</SelectItem>
                </SelectContent>
              </Select>
            </div> */}
          </div>
          
          <Button 
            onClick={generateCrossword} 
            disabled={isLoading || !formData.template || !formData.clueType}
            className="w-full"
          >
            {isLoading ? (
              <div className="flex items-center space-x-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                <span>Generating...</span>
              </div>
            ) : (
              'Generate Crossword'
            )}
          </Button>
          
          {isLoading && (
            <div className="text-center">
              <p className="text-sm text-gray-600 animate-pulse">{loadingMessage}</p>
            </div>
          )}
          
          {error && (
            <div className="text-red-600 text-sm">{error}</div>
          )}
        </CardContent>
      </Card>

      {/* Crossword Grid */}
      {crosswordData && (
        <Card>
          <CardHeader>
            <CardTitle className="text-xl font-bold">Crossword</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {renderGrid()}
              
              <div className="flex justify-center space-x-4">
                <Button onClick={checkSolution} variant="outline">
                  Check Solution
                </Button>
                <Button 
                  onClick={() => {
                    setCellCorrectness({});
                    setCheckResult(null);
                  }}
                  variant="outline"
                >
                  Clear Check
                </Button>
                <Button 
                  onClick={() => {
                    setUserSolution({});
                    setCellCorrectness({});
                    setCheckResult(null);
                  }}
                  variant="outline"
                >
                  Clear Grid
                </Button>
              </div>
              
              {checkResult && (
                <div className={`p-4 rounded-md ${checkResult.correct ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
                  {checkResult.correct ? (
                    <p className="font-semibold">🎉 Congratulations! All answers are correct!</p>
                  ) : (
                    <div>
                      <p className="font-semibold mb-2">
                        {/*{checkResult.incorrectCount} of {checkResult.totalCount} checked letters need correction.*/}
                        Not quite... Keep trying!
                      </p>
                      <p className="text-sm">
                        The crossword is not yet solved. Incorrect letters are highlighted in red, correct ones in green.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

        {/* Clues */}
        {crosswordData && (
          <Card>
            <CardHeader>
              <CardTitle className="text-xl font-bold">Clues</CardTitle>
            </CardHeader>
            <CardContent>
              {renderClues()}
            </CardContent>
          </Card>
        )}
      </div>

      {/* About Section - Right Side */}
      <div className="w-full lg:w-80 xl:w-[360px] flex">
        <CollapsibleAbout />
      </div>
    </div>
  );
}
