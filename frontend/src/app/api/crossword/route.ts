import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Derive backend URL: prefer BACKEND_URL, else fall back to localhost in dev
    let backendUrl = process.env.BACKEND_URL;
    if (!backendUrl) {
      const isProd = process.env.VERCEL === '1' || process.env.NODE_ENV === 'production';
      if (isProd) {
        console.error('[Crossword API] Missing BACKEND_URL in production environment.');
        return NextResponse.json({ error: 'Backend unavailable: BACKEND_URL not configured' }, { status: 500 });
      }
      backendUrl = 'http://localhost:8000';
      console.warn('[Crossword API] BACKEND_URL not set; using local fallback http://localhost:8000');
    }

    const target = `${backendUrl.replace(/\/$/, '')}/api/generate-crossword`;
    console.log('[Crossword API] Forwarding request to', target);

    const response = await fetch(target, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      let detail: any = undefined;
      try { detail = await response.json(); } catch {}
      console.error('[Crossword API] Backend error', response.status, detail);
      throw new Error(detail?.detail || `Backend returned ${response.status}`);
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
