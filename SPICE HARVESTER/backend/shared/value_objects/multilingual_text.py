"""
다국어 텍스트 값 객체
불변 객체로 구현하여 값 객체 패턴 적용
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass(frozen=True)
class MultiLingualText:
    """
    다국어 텍스트 값 객체
    
    불변 객체로 구현하여 값의 일관성 보장
    """
    ko: Optional[str] = None
    en: Optional[str] = None
    ja: Optional[str] = None
    zh: Optional[str] = None
    es: Optional[str] = None
    fr: Optional[str] = None
    de: Optional[str] = None
    
    def get(self, lang: str, fallback_chain: Optional[List[str]] = None) -> str:
        """
        언어별 텍스트 조회 (폴백 지원)
        
        Args:
            lang: 언어 코드
            fallback_chain: 폴백 언어 목록
            
        Returns:
            텍스트 또는 빈 문자열
        """
        # 요청한 언어 확인
        value = getattr(self, lang, None)
        if value:
            return value
        
        # 폴백 체인 사용
        if fallback_chain:
            for fallback_lang in fallback_chain:
                value = getattr(self, fallback_lang, None)
                if value:
                    return value
        
        # 기본 폴백 순서
        default_fallback = ['ko', 'en', 'ja', 'zh', 'es', 'fr', 'de']
        for fallback_lang in default_fallback:
            value = getattr(self, fallback_lang, None)
            if value:
                return value
        
        return ""
    
    def has_value(self, lang: str) -> bool:
        """특정 언어의 값 존재 여부"""
        return bool(getattr(self, lang, None))
    
    def has_any_value(self) -> bool:
        """어떤 언어든 값이 있는지 확인"""
        return any([
            self.ko, self.en, self.ja, self.zh,
            self.es, self.fr, self.de
        ])
    
    def get_available_languages(self) -> List[str]:
        """값이 있는 언어 목록 반환"""
        languages = []
        for lang in ['ko', 'en', 'ja', 'zh', 'es', 'fr', 'de']:
            if getattr(self, lang, None):
                languages.append(lang)
        return languages
    
    def to_dict(self) -> Dict[str, str]:
        """딕셔너리로 변환 (값이 있는 언어만)"""
        result = {}
        for lang in ['ko', 'en', 'ja', 'zh', 'es', 'fr', 'de']:
            value = getattr(self, lang, None)
            if value:
                result[lang] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "MultiLingualText":
        """딕셔너리에서 생성"""
        return cls(
            ko=data.get('ko'),
            en=data.get('en'),
            ja=data.get('ja'),
            zh=data.get('zh'),
            es=data.get('es'),
            fr=data.get('fr'),
            de=data.get('de')
        )
    
    @classmethod
    def from_string(cls, text: str, lang: str = 'ko') -> "MultiLingualText":
        """단일 문자열에서 생성"""
        kwargs = {lang: text}
        return cls(**kwargs)
    
    def __str__(self) -> str:
        """문자열 표현 (한국어 우선)"""
        return self.get('ko', ['en', 'ja', 'zh'])
    
    def __bool__(self) -> bool:
        """bool 변환 (값이 있으면 True)"""
        return self.has_any_value()