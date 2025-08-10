import { GeneratedIcon } from '@/types';

export async function downloadImage(
  url: string, 
  filename: string, 
  format: 'png' | 'svg' = 'png'
): Promise<void> {
  try {
    // Use server-side proxy to bypass CORS
    const proxyUrl = `/api/proxy-image?url=${encodeURIComponent(url)}&format=${format}`;
    const response = await fetch(proxyUrl);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const blob = await response.blob();
    
    // Ensure filename has correct extension
    const extension = format === 'svg' ? 'svg' : 'png';
    const finalFilename = filename.endsWith(`.${extension}`) 
      ? filename 
      : filename.replace(/\.(png|jpg|jpeg|svg)$/i, '') + `.${extension}`;
    
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = finalFilename;
    link.style.display = 'none';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    URL.revokeObjectURL(link.href);
  } catch (error) {
    console.error('Failed to download image:', error);
    throw new Error('Failed to download image');
  }
}

export async function downloadIcon(
  icon: GeneratedIcon, 
  prompt: string, 
  format: 'png' | 'svg' = 'png'
): Promise<void> {
  const baseFilename = `icon-${icon.id}-${prompt.replace(/[^a-zA-Z0-9]/g, '-')}`;
  const filename = `${baseFilename}.${format}`;
  await downloadImage(icon.imageUrl, filename, format);
}

export async function downloadSelectedIcons(
  icons: GeneratedIcon[], 
  prompt: string,
  format: 'png' | 'svg' = 'png'
): Promise<void> {
  const selectedIcons = icons.filter(icon => icon.liked);
  
  if (selectedIcons.length === 0) {
    throw new Error('No icons selected');
  }
  
  // Download each selected icon with format support
  const downloadPromises = selectedIcons.map((icon, index) => {
    const baseFilename = `icon-${index + 1}-${prompt.replace(/[^a-zA-Z0-9]/g, '-')}`;
    const filename = `${baseFilename}.${format}`;
    return downloadImage(icon.imageUrl, filename, format);
  });
  
  try {
    await Promise.all(downloadPromises);
  } catch (error) {
    console.error('Failed to download some icons:', error);
    throw new Error('Failed to download some icons');
  }
}

export async function downloadAllFormats(
  icon: GeneratedIcon,
  prompt: string
): Promise<void> {
  const baseFilename = `icon-${icon.id}-${prompt.replace(/[^a-zA-Z0-9]/g, '-')}`;
  
  try {
    // Download both PNG and SVG versions
    await Promise.all([
      downloadImage(icon.imageUrl, `${baseFilename}.png`, 'png'),
      downloadImage(icon.imageUrl, `${baseFilename}.svg`, 'svg')
    ]);
  } catch (error) {
    console.error('Failed to download all formats:', error);
    throw new Error('Failed to download all formats');
  }
}

export function createZipDownload(
  icons: GeneratedIcon[], 
  prompt: string,
  format: 'png' | 'svg' = 'png'
): void {
  // Download icons with format support and staggered timing
  icons.forEach((icon, index) => {
    setTimeout(() => {
      const baseFilename = `icon-${index + 1}-${prompt.replace(/[^a-zA-Z0-9]/g, '-')}`;
      const filename = `${baseFilename}.${format}`;
      downloadImage(icon.imageUrl, filename, format);
    }, index * 500); // Stagger downloads by 500ms to avoid overwhelming the browser
  });
}