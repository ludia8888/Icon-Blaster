"use client";

import { useState } from "react";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Heart, Download, Loader2, AlertCircle, RefreshCw, Settings } from "lucide-react";
import { downloadIcon, downloadSelectedIcons } from "@/lib/download";

interface GeneratedIcon {
  id: string;
  imageUrl: string;
  liked: boolean;
}

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [iconCount, setIconCount] = useState(10);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedIcons, setGeneratedIcons] = useState<GeneratedIcon[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successCount, setSuccessCount] = useState(0);

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    
    setIsGenerating(true);
    setError(null);
    setGeneratedIcons([]);
    
    try {
      const response = await fetch('/api/generate-icons', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ prompt, count: iconCount }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to generate icons');
      }

      setGeneratedIcons(data.icons);
      setSuccessCount(data.successCount);
      
      // Show partial success message if some icons failed
      if (data.errors && data.errors.length > 0) {
        setError(`${data.successCount}/${iconCount}개의 아이콘이 생성되었습니다. 일부 생성에 실패했습니다.`);
      }
    } catch (error) {
      console.error('Error generating icons:', error);
      setError(error instanceof Error ? error.message : '아이콘 생성에 실패했습니다.');
      
      // Fallback to mock data for demo purposes when OpenAI key is not available
      if (error instanceof Error && error.message.includes('OpenAI API key')) {
        const mockIcons: GeneratedIcon[] = Array.from({ length: iconCount }, (_, i) => ({
          id: `icon-${Date.now()}-${i}`,
          imageUrl: `https://via.placeholder.com/200x200/6366f1/white?text=Icon+${i + 1}`,
          liked: false,
        }));
        setGeneratedIcons(mockIcons);
        setSuccessCount(iconCount);
        setError("데모 모드: OpenAI API 키가 설정되지 않아 샘플 이미지를 표시합니다.");
      }
    } finally {
      setIsGenerating(false);
    }
  };

  const toggleLike = (id: string) => {
    setGeneratedIcons(icons => 
      icons.map(icon => 
        icon.id === id ? { ...icon, liked: !icon.liked } : icon
      )
    );
  };

  const handleDownload = async (icon: GeneratedIcon) => {
    try {
      await downloadIcon(icon, prompt);
    } catch (error) {
      console.error("Failed to download icon:", error);
      alert("다운로드에 실패했습니다. 다시 시도해주세요.");
    }
  };

  const handleBatchDownload = async () => {
    try {
      await downloadSelectedIcons(generatedIcons, prompt);
    } catch (error) {
      console.error("Failed to download selected icons:", error);
      alert("선택된 아이콘 다운로드에 실패했습니다. 다시 시도해주세요.");
    }
  };

  // Dynamic grid layout based on icon count
  const getGridCols = () => {
    if (iconCount <= 2) return "grid-cols-1 md:grid-cols-2";
    if (iconCount <= 4) return "grid-cols-2 md:grid-cols-2 lg:grid-cols-4";
    if (iconCount <= 6) return "grid-cols-2 md:grid-cols-3 lg:grid-cols-3";
    if (iconCount <= 8) return "grid-cols-2 md:grid-cols-4 lg:grid-cols-4";
    return "grid-cols-2 md:grid-cols-3 lg:grid-cols-5";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <header className="text-center py-8">
          <h1 className="text-4xl font-bold text-slate-800 mb-2">
            Icon Blaster
          </h1>
          <p className="text-slate-600 text-lg">
            AI로 한 번에 여러 개의 아이콘을 생성하고 비교하세요
          </p>
        </header>

        {/* Input Section */}
        <div className="max-w-2xl mx-auto mb-8">
          <div className="flex gap-3 mb-3">
            <Input
              placeholder="예: 미니멀한 커피 아이콘"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="text-lg py-6 px-4 flex-1"
              disabled={isGenerating}
            />
          </div>
          
          <div className="flex gap-3">
            <div className="flex items-center gap-2 bg-slate-50 rounded-lg px-3 py-2">
              <Settings className="h-4 w-4 text-slate-600" />
              <span className="text-sm text-slate-600">개수:</span>
              <Select
                value={iconCount.toString()}
                onValueChange={(value) => setIconCount(parseInt(value))}
                disabled={isGenerating}
              >
                <SelectTrigger className="w-20 h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1개</SelectItem>
                  <SelectItem value="2">2개</SelectItem>
                  <SelectItem value="3">3개</SelectItem>
                  <SelectItem value="4">4개</SelectItem>
                  <SelectItem value="5">5개</SelectItem>
                  <SelectItem value="6">6개</SelectItem>
                  <SelectItem value="8">8개</SelectItem>
                  <SelectItem value="10">10개</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <Button
              onClick={handleGenerate}
              disabled={isGenerating || !prompt.trim()}
              className="px-8 py-6 text-lg flex-1"
            >
              {isGenerating ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  생성 중...
                </>
              ) : (
                `${iconCount}개 생성`
              )}
            </Button>
          </div>
        </div>

        {/* Error Display */}
        {error && !isGenerating && (
          <div className="max-w-2xl mx-auto mb-8">
            <Card className="border-orange-200 bg-orange-50">
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-orange-600 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <p className="text-orange-800 font-medium">{error}</p>
                    {generatedIcons.length === 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleGenerate}
                        className="mt-3 border-orange-300 text-orange-700 hover:bg-orange-100"
                      >
                        <RefreshCw className="mr-2 h-4 w-4" />
                        다시 시도
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Loading State */}
        {isGenerating && (
          <div className="max-w-4xl mx-auto mb-8">
            <Card>
              <CardContent className="p-8 text-center">
                <Loader2 className="mx-auto h-12 w-12 animate-spin text-blue-500 mb-4" />
                <h3 className="text-xl font-semibold mb-2">아이콘 생성 중...</h3>
                <p className="text-slate-600">
                  AI가 {iconCount}개의 다양한 아이콘을 생성하고 있습니다
                </p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Results Grid */}
        {generatedIcons.length > 0 && !isGenerating && (
          <div className="max-w-6xl mx-auto">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-2xl font-bold text-slate-800">
                생성된 아이콘 ({successCount > 0 ? successCount : generatedIcons.length}개)
              </h2>
              <Badge variant="outline" className="text-sm">
                {generatedIcons.filter(icon => icon.liked).length}개 선택됨
              </Badge>
            </div>
            
            <div className={`grid ${getGridCols()} gap-4 mb-8`}>
              {generatedIcons.map((icon) => (
                <Card
                  key={icon.id}
                  className={`transition-all hover:shadow-lg ${
                    icon.liked ? 'ring-2 ring-red-400 shadow-lg' : ''
                  }`}
                >
                  <CardContent className="p-4">
                    <div className="aspect-square bg-slate-100 rounded-lg mb-3 overflow-hidden">
                      <Image
                        src={icon.imageUrl}
                        alt={`Generated icon ${icon.id}`}
                        width={200}
                        height={200}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleLike(icon.id)}
                        className={`flex-1 ${
                          icon.liked 
                            ? 'bg-red-50 border-red-200 text-red-600 hover:bg-red-100' 
                            : ''
                        }`}
                      >
                        <Heart 
                          className={`h-4 w-4 ${icon.liked ? 'fill-current' : ''}`} 
                        />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownload(icon)}
                        className="flex-1"
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Download Selected */}
            {generatedIcons.filter(icon => icon.liked).length > 0 && (
              <div className="text-center">
                <Button size="lg" className="px-8 py-3" onClick={handleBatchDownload}>
                  선택된 아이콘 다운로드 ({generatedIcons.filter(icon => icon.liked).length}개)
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Empty State */}
        {generatedIcons.length === 0 && !isGenerating && (
          <div className="max-w-2xl mx-auto text-center py-12">
            <div className="text-6xl mb-4">🎨</div>
            <h3 className="text-xl font-semibold mb-2 text-slate-700">
              아이콘을 생성해보세요
            </h3>
            <p className="text-slate-500">
              원하는 아이콘을 설명하면 AI가 10가지 다양한 버전으로 생성합니다
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
