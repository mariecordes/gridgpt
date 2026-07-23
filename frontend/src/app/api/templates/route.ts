import { NextResponse } from 'next/server';

export async function GET() {
  try {
    // Derive backend URL: prefer BACKEND_URL, else fall back to localhost in dev
    let backendUrl = process.env.BACKEND_URL;
    if (!backendUrl) {
      const isProd = process.env.VERCEL === '1' || process.env.NODE_ENV === 'production';
      if (isProd) {
        console.error('[Templates API] Missing BACKEND_URL in production environment.');
        return NextResponse.json({ error: 'Backend unavailable: BACKEND_URL not configured' }, { status: 500 });
      }
      backendUrl = 'http://localhost:8000';
      console.warn('[Templates API] BACKEND_URL not set; using local fallback http://localhost:8000');
    }

    const target = `${backendUrl.replace(/\/$/, '')}/api/templates`;
    const response = await fetch(target);

    if (!response.ok) {
      throw new Error(`Backend returned ${response.status}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Error loading templates:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to load templates' },
      { status: 500 }
    );
  }
}
