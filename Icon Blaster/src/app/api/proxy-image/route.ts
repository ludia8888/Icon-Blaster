import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const imageUrl = searchParams.get('url');
    const format = searchParams.get('format') || 'png';
    
    if (!imageUrl) {
      return NextResponse.json(
        { error: 'Image URL is required' },
        { status: 400 }
      );
    }

    // Validate that URL is from OpenAI
    if (!imageUrl.includes('oaidalleapiprodscus.blob.core.windows.net')) {
      return NextResponse.json(
        { error: 'Invalid image source' },
        { status: 403 }
      );
    }

    // Fetch image from OpenAI (server-side, no CORS issues)
    const response = await fetch(imageUrl);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch image: ${response.status}`);
    }

    const imageBuffer = await response.arrayBuffer();
    
    if (format === 'svg') {
      // Convert PNG to SVG by embedding as base64 data URI
      const base64Data = Buffer.from(imageBuffer).toString('base64');
      const svgContent = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" 
     width="1024" height="1024" viewBox="0 0 1024 1024">
  <title>AI Generated Icon</title>
  <desc>Vector-wrapped AI generated icon from OpenAI</desc>
  <image x="0" y="0" width="1024" height="1024" 
         xlink:href="data:image/png;base64,${base64Data}" />
</svg>`;

      const headers = new Headers({
        'Content-Type': 'image/svg+xml',
        'Content-Length': Buffer.byteLength(svgContent, 'utf8').toString(),
        'Cache-Control': 'public, max-age=3600',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Disposition': 'inline; filename="ai-icon.svg"',
      });

      return new NextResponse(svgContent, {
        status: 200,
        headers,
      });
    } else {
      // Return PNG as-is
      const headers = new Headers({
        'Content-Type': 'image/png',
        'Content-Length': imageBuffer.byteLength.toString(),
        'Cache-Control': 'public, max-age=3600',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Content-Disposition': 'inline; filename="ai-icon.png"',
      });

      return new NextResponse(imageBuffer, {
        status: 200,
        headers,
      });
    }

  } catch (error) {
    console.error('Image proxy error:', error);
    return NextResponse.json(
      { error: 'Failed to proxy image' },
      { status: 500 }
    );
  }
}