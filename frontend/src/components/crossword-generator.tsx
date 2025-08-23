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
import colors from '@/lib/colors';

// Helper function to find the next empty cell in a slot
const findNextEmptyInSlot = (slot: any, currentIndex: number, direction: number, userSolution: { [key: string]: string } = {}) => {
  const cells = slot.cells;
  let index = currentIndex + direction;
  
  while (index >= 0 && index < cells.length) {
    const [row, col] = cells[index];
    const cellKey = `${row}-${col}`;
    if (!userSolution[cellKey] || userSolution[cellKey] === '') {
      return index;
    }
    index += direction;
  }
  
  return -1; // No empty cell found
};

// Helper function to find the first empty cell in a slot (for Tab navigation)
const findNextEmptyCell = (slot: any, startIndex: number, userSolution: { [key: string]: string } = {}) => {
  const cells = slot.cells;
  
  // Start from beginning if startIndex is -1, or from startIndex + 1
  let index = startIndex === -1 ? 0 : startIndex + 1;
  
  while (index < cells.length) {
    const [row, col] = cells[index];
    const cellKey = `${row}-${col}`;
    if (!userSolution[cellKey] || userSolution[cellKey] === '') {
      return cells[index];
    }
    index++;
  }
  
  // If no empty cell found, return first cell
  return cells[0];
};

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
  const [lastNavigationDirection, setLastNavigationDirection] = useState<string | null>(null);

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

    // Auto-advance to next empty cell in current slot
    if (value && currentSlot && crosswordData?.slots) {
      const slot = crosswordData.slots.find(s => s.id === currentSlot);
      if (slot) {
        const currentCellIndex = slot.cells.findIndex(([row, col]) => `${row}-${col}` === gridKey);
        if (currentCellIndex !== -1) {
          // Update userSolution first for correct empty cell detection
          const updatedSolution = { ...userSolution, [gridKey]: value.toUpperCase() };
          const nextEmptyIndex = findNextEmptyInSlot(slot, currentCellIndex, 1, updatedSolution);
          
          if (nextEmptyIndex >= 0) {
            const nextCell = slot.cells[nextEmptyIndex];
            const nextInput = document.querySelector(`input[data-cell="${nextCell[0]}-${nextCell[1]}"]`) as HTMLInputElement;
            if (nextInput) {
              nextInput.focus();
            }
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
      
      // Create ordered list: all across clues first, then all down clues
      const acrossSlots = crosswordData.slots.filter(s => s.direction === 'across');
      const downSlots = crosswordData.slots.filter(s => s.direction === 'down');
      const allSlotsInOrder = [...acrossSlots, ...downSlots];
      
      const currentIndex = allSlotsInOrder.findIndex(s => s.id === currentSlot);
      
      let nextIndex;
      if (e.shiftKey) {
        // Shift+Tab: go backwards
        nextIndex = currentIndex > 0 ? currentIndex - 1 : allSlotsInOrder.length - 1;
      } else {
        // Tab: go forwards
        nextIndex = currentIndex < allSlotsInOrder.length - 1 ? currentIndex + 1 : 0;
      }
      
      const nextSlot = allSlotsInOrder[nextIndex];
      setCurrentSlot(nextSlot.id);
      setCurrentDirection(nextSlot.direction);
      
      // Focus on first empty cell of next slot
      const firstEmptyCell = findNextEmptyCell(nextSlot, -1, userSolution);
      if (firstEmptyCell) {
        const firstInput = document.querySelector(`input[data-cell="${firstEmptyCell[0]}-${firstEmptyCell[1]}"]`) as HTMLInputElement;
        if (firstInput) {
          firstInput.focus();
        }
      }
      
      setLastNavigationDirection(null);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'ArrowUp' || e.key === 'ArrowDown') {
      e.preventDefault();
      
      const [row, col] = gridKey.split('-').map(Number);
      
      // Check if this is the first arrow key press in this direction
      const isFirstPress = lastNavigationDirection !== e.key;
      
      if (isFirstPress) {
        // First press: try to switch direction
        const slotsAtCell = crosswordData.slots.filter(slot => 
          slot.cells.some(([r, c]) => r === row && c === col)
        );
        
        let targetDirection: 'across' | 'down' | null = null;
        
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          targetDirection = 'down';
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          targetDirection = 'across';
        }
        
        if (targetDirection && currentDirection !== targetDirection) {
          // Switch to the other direction if available
          const targetSlot = slotsAtCell.find(s => s.direction === targetDirection);
          if (targetSlot) {
            setCurrentSlot(targetSlot.id);
            setCurrentDirection(targetDirection);
            setLastNavigationDirection(e.key);
            return;
          }
        }
      }
      
      // Second press or no direction change: navigate within current word or move to next/prev cell
      if (currentSlot) {
        // Navigate within current word to next/prev empty cell
        const slot = crosswordData.slots.find(s => s.id === currentSlot);
        if (slot) {
          const currentCellIndex = slot.cells.findIndex(([r, c]) => r === row && c === col);
          let targetCellIndex = -1;
          
          if ((e.key === 'ArrowRight' && currentDirection === 'across') || 
              (e.key === 'ArrowDown' && currentDirection === 'down')) {
            // Move forward in word
            targetCellIndex = findNextEmptyInSlot(slot, currentCellIndex, 1, userSolution);
          } else if ((e.key === 'ArrowLeft' && currentDirection === 'across') || 
                     (e.key === 'ArrowUp' && currentDirection === 'down')) {
            // Move backward in word
            targetCellIndex = findNextEmptyInSlot(slot, currentCellIndex, -1, userSolution);
          }
          
          if (targetCellIndex >= 0) {
            const targetCell = slot.cells[targetCellIndex];
            const targetInput = document.querySelector(`input[data-cell="${targetCell[0]}-${targetCell[1]}"]`) as HTMLInputElement;
            if (targetInput) {
              targetInput.focus();
              setLastNavigationDirection(e.key);
              return;
            }
          }
        }
      }
      
      // If no word navigation, move grid-wise but preserve current direction if it exists at new cell
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
        
        // Try to maintain current direction at new cell
        const slotsAtNewCell = crosswordData.slots.filter(slot => 
          slot.cells.some(([r, c]) => r === newRow && c === newCol)
        );
        
        // Check if current direction exists at new cell
        const sameDirectionSlot = slotsAtNewCell.find(s => s.direction === currentDirection);
        if (sameDirectionSlot) {
          // Keep the same direction
          setCurrentSlot(sameDirectionSlot.id);
          // currentDirection stays the same
        } else {
          // Fall back to cell click behavior if current direction not available
          handleCellClick(`${newRow}-${newCol}`);
        }
      }
      
      setLastNavigationDirection(e.key);
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
      setLastNavigationDirection(null);
    } else {
      setLastNavigationDirection(null);
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
      <div 
        className="grid grid-cols-5 gap-0 w-fit mx-auto"
        style={{ border: `2px solid ${colors.gridBorder}` }}
      >
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
            let cellBgColor = colors.emptyCell;
            let cellHoverColor = colors.cellHover;
            
            if (correctness === 'correct') {
              cellBgColor = colors.correctAnswer;
              cellHoverColor = colors.correctHover;
            } else if (correctness === 'incorrect') {
              cellBgColor = colors.incorrectAnswer;
              cellHoverColor = colors.incorrectHover;
            } else if (isInCurrentSlot) {
              cellBgColor = colors.slotHighlight;
              cellHoverColor = colors.slotHover;
            }
            
            return (
              <div
                key={`${rowIndex}-${colIndex}`}
                className="w-12 h-12 border relative transition-colors hover:cursor-pointer"
                style={{ 
                  backgroundColor: cell === '#' ? colors.blockedCell : cellBgColor,
                  borderColor: colors.gridCell
                }}
                onMouseEnter={(e) => {
                  if (cell !== '#') {
                    e.currentTarget.style.backgroundColor = cellHoverColor;
                  }
                }}
                onMouseLeave={(e) => {
                  if (cell !== '#') {
                    e.currentTarget.style.backgroundColor = cellBgColor;
                  }
                }}
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
                      className="w-full h-full text-center border-none outline-none text-lg font-bold pt-2 bg-transparent transition-colors"
                      style={{ textTransform: 'uppercase' }}
                      value={userSolution[cellKey] || ''}
                      onChange={(e) => handleCellChange(cellKey, e.target.value)}
                      onKeyDown={(e) => handleKeyDown(e, cellKey)}
                      onFocus={(e) => {
                        e.target.style.backgroundColor = colors.activeCell;
                      }}
                      onBlur={(e) => {
                        e.target.style.backgroundColor = 'transparent';
                      }}
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
          <h3 className="text-base font-semibold mb-2">Across</h3>
          <div className="space-y-1">
            {acrossClues.map(([clueId, clue]) => (
              <div 
                key={clueId} 
                className="text-sm px-2 py-1 rounded cursor-pointer transition-colors"
                style={{
                  backgroundColor: currentSlot === clueId ? colors.slotHighlight : 'transparent',
                  border: currentSlot === clueId ? `1px solid ${colors.selectedClueBorder}` : '1px solid transparent'
                }}
                onMouseEnter={(e) => {
                  if (currentSlot !== clueId) {
                    e.currentTarget.style.backgroundColor = colors.clueHover;
                  }
                }}
                onMouseLeave={(e) => {
                  if (currentSlot !== clueId) {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }
                }}
                onClick={() => {
                  if (currentSlot === clueId) {
                    // Deselect if clicking on currently selected clue
                    setCurrentSlot(null);
                  } else {
                    // Select the clue
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
                  }
                }}
              >
                <span className="font-medium">{clueId}:</span> {clue}
              </div>
            ))}
          </div>
        </div>
        
        <div>
          <h3 className="text-base font-semibold mb-2">Down</h3>
          <div className="space-y-1">
            {downClues.map(([clueId, clue]) => (
              <div 
                key={clueId} 
                className="text-sm px-2 py-1 rounded cursor-pointer transition-colors"
                style={{
                  backgroundColor: currentSlot === clueId ? colors.slotHighlight : 'transparent',
                  border: currentSlot === clueId ? `1px solid ${colors.selectedClueBorder}` : '1px solid transparent'
                }}
                onMouseEnter={(e) => {
                  if (currentSlot !== clueId) {
                    e.currentTarget.style.backgroundColor = colors.clueHover;
                  }
                }}
                onMouseLeave={(e) => {
                  if (currentSlot !== clueId) {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }
                }}
                onClick={() => {
                  if (currentSlot === clueId) {
                    // Deselect if clicking on currently selected clue
                    setCurrentSlot(null);
                  } else {
                    // Select the clue
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
                <div 
                  className="p-4 rounded-md"
                  style={{
                    backgroundColor: checkResult.correct ? colors.correctAnswer : colors.incorrectAnswer,
                    color: checkResult.correct ? colors.textSuccess : colors.textError
                  }}
                >
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
