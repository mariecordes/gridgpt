import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Use environment variable for backend URL, fallback to production
    const backendUrl = process.env.BACKEND_URL || 'https://gridgpt-backend.vercel.app';
    
    // Forward request to your Python backend
    const response = await fetch(`${backendUrl}/api/generate-crossword`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to generate crossword');
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error generating crossword:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to generate crossword' },
      { status: 500 }
    );
  }
}
