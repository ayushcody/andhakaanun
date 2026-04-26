import { NextRequest, NextResponse } from 'next/server';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export async function POST(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  try {
    const urlPath = params.path.join('/');
    const targetUrl = `${API_BASE_URL}/${urlPath}`;
    
    // Check if the original request was asking for a stream
    const isStream = request.nextUrl.searchParams.get('stream') === 'true';
    
    // Get the request body
    const body = await request.json();
    
    // Forward the request to FastAPI
    const response = await fetch(targetUrl + (isStream ? '?stream=true' : ''), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    // Handle SSE streaming
    if (isStream && response.headers.get('content-type')?.includes('text/event-stream')) {
      return new NextResponse(response.body, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    // Handle standard JSON response
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
    
  } catch (error) {
    console.error('Proxy error:', error);
    return NextResponse.json(
      { detail: { message: 'Failed to connect to backend service', error: 'PROXY_ERROR' } },
      { status: 502 }
    );
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  try {
    const urlPath = params.path.join('/');
    const searchParams = request.nextUrl.searchParams.toString();
    const targetUrl = `${API_BASE_URL}/${urlPath}${searchParams ? `?${searchParams}` : ''}`;
    
    const response = await fetch(targetUrl);
    const data = await response.json();
    
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Proxy error:', error);
    return NextResponse.json(
      { detail: { message: 'Failed to connect to backend service', error: 'PROXY_ERROR' } },
      { status: 502 }
    );
  }
}
