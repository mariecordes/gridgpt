'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { CrosswordData, GenerateRequest } from '@/lib/types';
import { API_BASE_URL } from '@/lib/utils';

export default function CrosswordGenerator() {
  const [formData, setFormData] = useState<GenerateRequest>({
    template: '',
    theme: '',
    themeEntry: '',
    difficulty: 'easy'
  });
  
  const [crosswordData, setCrosswordData] = useState<CrosswordData | null>(null);
  const [userSolution, setUserSolution] = useState<{ [key: string]: string }>({});
  const [cellCorrectness, setCellCorrectness] = useState<{ [key: string]: 'correct' | 'incorrect' | 'unchecked' }>({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<{ correct: boolean; incorrectCount: number; totalCount: number } | null>(null);

  const templates = [
    { id: '5x5_basic', name: '5x5 Basic', difficulty: 'easy' },
    { id: '5x5_t_shape', name: '5x5 T-Shape', difficulty: 'medium' },
    { id: '5x5_corners', name: '5x5 Corner Black Squares', difficulty: 'hard' }
  ];

  const handleInputChange = (field: keyof GenerateRequest, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const generateCrossword = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/crossword', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to generate crossword');
      }

      const data = await response.json();
      setCrosswordData(data);
      setUserSolution({});
      setCellCorrectness({});
      setCheckResult(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCellChange = (gridKey: string, value: string) => {
    setUserSolution(prev => ({
      ...prev,
      [gridKey]: value.toUpperCase()
    }));
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
  };

  // Helper function to get clue numbers for a cell
  const getClueNumbers = (rowIndex: number, colIndex: number) => {
    if (!crosswordData?.slots) return [];
    
    const clueNumbers: string[] = [];
    
    // Check all slots to see if this cell is a starting position
    crosswordData.slots.forEach((slot: any) => {
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
            
            // Determine cell background color based on correctness
            let cellBgClass = 'bg-white hover:bg-blue-50';
            if (correctness === 'correct') {
              cellBgClass = 'bg-green-100 hover:bg-green-200';
            } else if (correctness === 'incorrect') {
              cellBgClass = 'bg-red-100 hover:bg-red-200';
            }
            
            return (
              <div
                key={`${rowIndex}-${colIndex}`}
                className={`
                  w-12 h-12 border border-gray-400 relative
                  ${cell === '#' ? 'bg-black' : cellBgClass}
                `}
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
                      className="w-full h-full text-center border-none outline-none text-lg font-bold pt-2 bg-transparent focus:bg-yellow-100 transition-colors"
                      value={userSolution[`${rowIndex}-${colIndex}`] || ''}
                      onChange={(e) => handleCellChange(`${rowIndex}-${colIndex}`, e.target.value)}
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
          <h3 className="text-lg font-semibold mb-3">Across</h3>
          <div className="space-y-2">
            {acrossClues.map(([clueId, clue]) => (
              <div key={clueId} className="text-sm">
                <span className="font-medium">{clueId}:</span> {clue}
                {/* {crosswordData.theme_entries[clueId] && (
                  <Badge variant="secondary" className="ml-2">Theme</Badge>
                )} */}
              </div>
            ))}
          </div>
        </div>
        
        <div>
          <h3 className="text-lg font-semibold mb-3">Down</h3>
          <div className="space-y-2">
            {downClues.map(([clueId, clue]) => (
              <div key={clueId} className="text-sm">
                <span className="font-medium">{clueId}:</span> {clue}
                {/* {crosswordData.theme_entries[clueId] && (
                  <Badge variant="secondary" className="ml-2">Theme</Badge>
                )} */}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Input Form */}
      <Card>
        <CardHeader>
          <CardTitle>Generate Crossword</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="theme">Theme</Label>
              <Input
                id="theme"
                placeholder="e.g., Space, Food, Movies"
                value={formData.theme || ''}
                onChange={(e) => handleInputChange('theme', e.target.value)}
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="themeEntry">Theme Entry (Optional)</Label>
              <Input
                id="themeEntry"
                placeholder="e.g., ASTRONAUT, PIZZA"
                value={formData.themeEntry || ''}
                onChange={(e) => handleInputChange('themeEntry', e.target.value)}
              />
            </div>
            
            <div className="space-y-2">
              <Label>Template</Label>
              <Select
                value={formData.template || ''}
                onValueChange={(value) => handleInputChange('template', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a template" />
                </SelectTrigger>
                <SelectContent>
                  {templates.map((template) => (
                    <SelectItem key={template.id} value={template.id}>
                      {template.name} ({template.difficulty})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
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
            </div>
          </div>
          
          <Button 
            onClick={generateCrossword} 
            disabled={isLoading || !formData.theme}
            className="w-full"
          >
            {isLoading ? 'Generating...' : 'Generate Crossword'}
          </Button>
          
          {error && (
            <div className="text-red-600 text-sm">{error}</div>
          )}
        </CardContent>
      </Card>

      {/* Crossword Grid */}
      {crosswordData && (
        <Card>
          <CardHeader>
            <CardTitle>Crossword Puzzle</CardTitle>
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
                        {checkResult.incorrectCount} of {checkResult.totalCount} checked letters need correction.
                      </p>
                      <p className="text-sm">
                        Incorrect letters are highlighted in red, correct ones in green.
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
            <CardTitle>Clues</CardTitle>
          </CardHeader>
          <CardContent>
            {renderClues()}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
