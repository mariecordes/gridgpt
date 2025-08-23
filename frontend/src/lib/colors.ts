/**
 * Color definitions
 */

const colors = {
  // Grid colors
  gridBorder: '#1F2937',            // Tailwind gray-800 (grid border)
  gridCell: '#9CA3AF',              // Tailwind gray-400 (cell borders)
  
  // Cell background colors
  emptyCell: '#FFFFFF',             // White (empty cell)
  blockedCell: '#000000',           // Black (blocked cell)
  slotHighlight: '#DBEAFE',         // Blue 100 (slot highlight)
  slotHover: '#BFDBFE',             // Blue 200 (slot hover)
  activeCell: '#FEF3C7',            // Yellow 100 (active cell)
  correctAnswer: '#DCFCE7',         // Green 100 (correct answer)
  correctHover: '#BBF7D0',          // Green 200 (correct hover)
  incorrectAnswer: '#FEE2E2',       // Red 100 (incorrect answer)
  incorrectHover: '#FECACA',        // Red 200 (incorrect hover)
  clueHover: '#F9FAFB',             // Gray 50 (clue hover)
  cellHover: '#EFF6FF',             // Blue 50 (cell hover)

  // Border colors
  selectedClueBorder: '#93C5FD',    // Blue 300 (selected clue border)
  
  // Text colors
  textSuccess: '#166534',           // Green 800 (success text)
  textError: '#991B1B',             // Red 800 (error text)
};

export default colors;
