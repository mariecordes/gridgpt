import React from 'react';

interface GridPreviewProps {
  type: string;
}

const GridPreview: React.FC<GridPreviewProps> = ({ type }) => {
  const getGridPattern = () => {
    switch (type) {
      case '5x5_blocked_corners':
        return (
          <svg className="w-6 h-6" viewBox="0 0 50 50">
            {/* Black corner blocks */}
            <rect x="0" y="0" width="10" height="10" fill="#1f2937" />
            <rect x="40" y="0" width="10" height="10" fill="#1f2937" />
            <rect x="0" y="40" width="10" height="10" fill="#1f2937" />
            <rect x="40" y="40" width="10" height="10" fill="#1f2937" />
            {/* White grid squares with borders */}
            {[...Array(5)].map((_, row) => 
              [...Array(5)].map((_, col) => {
                const isCorner = (row === 0 && col === 0) || (row === 0 && col === 4) || 
                                (row === 4 && col === 0) || (row === 4 && col === 4);
                if (isCorner) return null;
                return (
                  <rect 
                    key={`${row}-${col}`}
                    x={col * 10} 
                    y={row * 10} 
                    width="10" 
                    height="10" 
                    fill="white" 
                    stroke="#494949ff" 
                    strokeWidth="0.5" 
                  />
                );
              })
            )}
          </svg>
        );
      case '5x5_bottom_pillars':
        return (
          <svg className="w-6 h-6" viewBox="0 0 50 50">
            {/* Top 3 rows - white grid */}
            {[...Array(3)].map((_, row) => 
              [...Array(5)].map((_, col) => (
                <rect 
                  key={`${row}-${col}`}
                  x={col * 10} 
                  y={row * 10} 
                  width="10" 
                  height="10" 
                  fill="white" 
                  stroke="#494949ff" 
                  strokeWidth="0.5" 
                />
              ))
            )}
            {/* Bottom 2 rows with pillars */}
            {[3, 4].map(row => 
              [...Array(5)].map((_, col) => {
                const isPillar = col === 0 || col === 4;
                return (
                  <rect 
                    key={`${row}-${col}`}
                    x={col * 10} 
                    y={row * 10} 
                    width="10" 
                    height="10" 
                    fill={isPillar ? "#1f2937" : "white"} 
                    stroke="#494949ff" 
                    strokeWidth="0.5" 
                  />
                );
              })
            )}
          </svg>
        );
      case '5x5_diagonal_cut':
        return (
          <svg className="w-6 h-6" viewBox="0 0 50 50">
            {/* Create diagonal pattern */}
            {[...Array(5)].map((_, row) => 
              [...Array(5)].map((_, col) => {
                const isDiagonal = row + col === 0 || row + col === 1 || row + col === 7 || row + col === 8;
                return (
                  <rect 
                    key={`${row}-${col}`}
                    x={col * 10} 
                    y={row * 10} 
                    width="10" 
                    height="10" 
                    fill={isDiagonal ? "#1f2937" : "white"} 
                    stroke="#494949ff" 
                    strokeWidth="0.5" 
                  />
                );
              })
            )}
          </svg>
        );
      default:
        return (
          <svg className="w-6 h-6" viewBox="0 0 50 50">
            {/* Default 5x5 grid */}
            {[...Array(5)].map((_, row) => 
              [...Array(5)].map((_, col) => (
                <rect 
                  key={`${row}-${col}`}
                  x={col * 10} 
                  y={row * 10} 
                  width="10" 
                  height="10" 
                  fill="white" 
                  stroke="#494949ff" 
                  strokeWidth="0.5" 
                />
              ))
            )}
          </svg>
        );
    }
  };

  return getGridPattern();
};

export default GridPreview;
