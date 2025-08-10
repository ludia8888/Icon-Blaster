import { NextRequest, NextResponse } from 'next/server';
import OpenAI from 'openai';

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export async function POST(request: NextRequest) {
  try {
    const { prompt, count = 10 } = await request.json();

    if (!prompt) {
      return NextResponse.json(
        { error: 'Prompt is required' },
        { status: 400 }
      );
    }

    if (count < 1 || count > 10) {
      return NextResponse.json(
        { error: 'Count must be between 1 and 10' },
        { status: 400 }
      );
    }

    if (!process.env.OPENAI_API_KEY) {
      return NextResponse.json(
        { error: 'OpenAI API key is not configured' },
        { status: 500 }
      );
    }

    // Helper function to generate a single icon with retry
    const generateSingleIcon = async (promptVariation: string, retries = 2): Promise<string | null> => {
      for (let attempt = 0; attempt <= retries; attempt++) {
        try {
          const result = await openai.images.generate({
            model: "dall-e-3",
            prompt: promptVariation,
            size: "1024x1024",
            quality: "standard",
            n: 1,
          });
          
          return result.data?.[0]?.url || null;
        } catch (error) {
          console.error(`Attempt ${attempt + 1} failed:`, error);
          if (attempt === retries) {
            return null;
          }
          // Wait before retry (exponential backoff)
          await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
        }
      }
      return null;
    };

    // Generate icons in parallel with retry logic
    const iconPromises = Array.from({ length: count }, (_, i) => {
      const enhancedPrompt = `${prompt}, icon style, flat design, simple, clean, professional, variation ${i + 1}`;
      return generateSingleIcon(enhancedPrompt);
    });

    // Execute all promises in parallel
    const results = await Promise.allSettled(iconPromises);
    
    const generatedIcons: Array<{id: string; imageUrl: string; liked: boolean}> = [];
    const errors: string[] = [];

    results.forEach((result, index) => {
      if (result.status === 'fulfilled' && result.value) {
        generatedIcons.push({
          id: `icon-${Date.now()}-${index}`,
          imageUrl: result.value,
          liked: false,
        });
      } else {
        const errorMessage = result.status === 'rejected' 
          ? `Icon ${index + 1}: ${result.reason?.message || 'Unknown error'}`
          : `Icon ${index + 1}: Generation failed`;
        errors.push(errorMessage);
      }
    });

    if (generatedIcons.length === 0) {
      return NextResponse.json(
        { error: 'Failed to generate any icons', details: errors },
        { status: 500 }
      );
    }

    return NextResponse.json({
      icons: generatedIcons,
      successCount: generatedIcons.length,
      totalAttempted: count,
      errors: errors.length > 0 ? errors : undefined,
    });

  } catch (error) {
    console.error('Error generating icons:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}