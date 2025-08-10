import { GeneratedIcon } from '@/types';

export async function downloadImage(url: string, filename: string): Promise<void> {
  try {
    const response = await fetch(url);
    const blob = await response.blob();
    
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
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

export async function downloadIcon(icon: GeneratedIcon, prompt: string): Promise<void> {
  const filename = `icon-${icon.id}-${prompt.replace(/[^a-zA-Z0-9]/g, '-')}.png`;
  await downloadImage(icon.imageUrl, filename);
}

export async function downloadSelectedIcons(
  icons: GeneratedIcon[], 
  prompt: string
): Promise<void> {
  const selectedIcons = icons.filter(icon => icon.liked);
  
  if (selectedIcons.length === 0) {
    throw new Error('No icons selected');
  }
  
  // Download each selected icon
  const downloadPromises = selectedIcons.map((icon, index) => {
    const filename = `icon-${index + 1}-${prompt.replace(/[^a-zA-Z0-9]/g, '-')}.png`;
    return downloadImage(icon.imageUrl, filename);
  });
  
  try {
    await Promise.all(downloadPromises);
  } catch (error) {
    console.error('Failed to download some icons:', error);
    throw new Error('Failed to download some icons');
  }
}

export function createZipDownload(icons: GeneratedIcon[], prompt: string): void {
  // This would require a zip library like JSZip
  // For now, we'll just download individually
  icons.forEach((icon, index) => {
    setTimeout(() => {
      const filename = `icon-${index + 1}-${prompt.replace(/[^a-zA-Z0-9]/g, '-')}.png`;
      downloadImage(icon.imageUrl, filename);
    }, index * 500); // Stagger downloads by 500ms to avoid overwhelming the browser
  });
}