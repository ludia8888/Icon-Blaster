"""
Vector embedding providers for multiple AI services.
Supports OpenAI, Cohere, Hugging Face, Azure OpenAI, and local models.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
import asyncio
import httpx
import numpy as np

# Optional ML dependencies
try:
    from sentence_transformers import SentenceTransformer
    import torch
    HAS_ML_DEPS = True
except ImportError:
    HAS_ML_DEPS = False
    SentenceTransformer = None
    torch = None
import time
from collections import defaultdict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# Custom exceptions for embedding providers
class EmbeddingProviderError(Exception):
    """Base exception for embedding provider errors."""
    pass


class EmbeddingAPIError(EmbeddingProviderError):
    """API-related errors (rate limits, authentication, etc.)."""
    pass


class EmbeddingBatchSizeError(EmbeddingProviderError):
    """Batch size exceeded error."""
    pass


class EmbeddingTokenLimitError(EmbeddingProviderError):
    """Token limit exceeded error."""
    pass


class EmbeddingProvider(Enum):
    OPENAI = "openai"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"
    AZURE_OPENAI = "azure_openai"
    LOCAL_SENTENCE_TRANSFORMERS = "local_sentence_transformers"
    GOOGLE_VERTEX = "google_vertex"
    ANTHROPIC_CLAUDE = "anthropic_claude"


@dataclass
class EmbeddingConfig:
    provider: EmbeddingProvider
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    dimensions: Optional[int] = None
    max_tokens: int = 8192
    batch_size: int = 100
    timeout: int = 30
    # Provider-specific limits
    max_tokens_per_request: Optional[int] = None
    max_items_per_batch: Optional[int] = None
    rate_limit_rpm: Optional[int] = None


class BaseEmbeddingProvider(ABC):
    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.client = self._initialize_client()
        # Rate limiting tracking
        self._request_times: Dict[str, List[datetime]] = defaultdict(list)
        self._rate_limit_lock = asyncio.Lock()

    @abstractmethod
    def _initialize_client(self):
        pass

    @abstractmethod
    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        pass

    @abstractmethod
    async def create_single_embedding(self, text: str) -> List[float]:
        pass

    def _split_into_batches(self, texts: List[str]) -> List[List[str]]:
        """Split texts into batches based on provider limits."""
        batch_size = self.config.batch_size
        max_tokens = self.config.max_tokens_per_request or self.config.max_tokens
        max_items = self.config.max_items_per_batch or batch_size
        
        batches = []
        current_batch = []
        current_tokens = 0
        
        for text in texts:
            # Estimate tokens (rough approximation: 1 token ≈ 4 chars)
            estimated_tokens = len(text) // 4 + 1
            
            # Check if adding this text would exceed limits
            if current_batch and (
                len(current_batch) >= max_items or 
                current_tokens + estimated_tokens > max_tokens
            ):
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            
            current_batch.append(text)
            current_tokens += estimated_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        return batches

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text."""
        # More accurate estimation based on provider
        if self.config.provider in [EmbeddingProvider.OPENAI, EmbeddingProvider.AZURE_OPENAI]:
            # OpenAI: ~1 token per 4 characters
            return len(text) // 4 + 1
        elif self.config.provider == EmbeddingProvider.COHERE:
            # Cohere: ~1 token per 3.5 characters
            return int(len(text) / 3.5) + 1
        else:
            # Default conservative estimate
            return len(text) // 3 + 1

    async def create_embeddings_with_batching(self, texts: List[str]) -> List[List[float]]:
        """Create embeddings with automatic batching for large inputs."""
        if len(texts) <= self.config.batch_size:
            return await self._create_embeddings_with_retry(texts)
        
        batches = self._split_into_batches(texts)
        all_embeddings = []
        
        for batch in batches:
            try:
                batch_embeddings = await self._create_embeddings_with_retry(batch)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                # Add zero vectors for failed batch
                for _ in batch:
                    all_embeddings.append([0.0] * (self.config.dimensions or 384))
        
        return all_embeddings

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limits."""
        if not self.config.rate_limit_rpm:
            return
        
        async with self._rate_limit_lock:
            now = datetime.now()
            window_start = now - timedelta(minutes=1)
            
            # Clean up old request times
            provider_key = self.config.provider.value
            self._request_times[provider_key] = [
                t for t in self._request_times[provider_key] 
                if t > window_start
            ]
            
            # Check if we're at the limit
            request_count = len(self._request_times[provider_key])
            if request_count >= self.config.rate_limit_rpm:
                # Calculate wait time
                oldest_request = min(self._request_times[provider_key])
                wait_time = (oldest_request + timedelta(minutes=1) - now).total_seconds()
                if wait_time > 0:
                    logger.warning(f"Rate limit reached for {provider_key}, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
            
            # Record this request
            self._request_times[provider_key].append(now)

    async def _create_embeddings_with_retry(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """Create embeddings with automatic retry on failure."""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Check rate limit before making request
                await self._check_rate_limit()
                
                # Make the actual request
                return await self.create_embeddings(texts)
                
            except EmbeddingAPIError as e:
                last_error = e
                if "rate_limit" in str(e).lower():
                    # Exponential backoff for rate limit errors
                    wait_time = min(60, (2 ** attempt) * 5)
                    logger.warning(f"Rate limit error, attempt {attempt + 1}/{max_retries}, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    # Shorter wait for other API errors
                    wait_time = min(10, (2 ** attempt))
                    logger.warning(f"API error, attempt {attempt + 1}/{max_retries}, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = min(5, (2 ** attempt) * 0.5)
                    logger.warning(f"Unexpected error, attempt {attempt + 1}/{max_retries}, waiting {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    break
        
        # All retries failed
        raise last_error or Exception("All retry attempts failed")

    async def similarity_search(self, query_embedding: List[float], 
                              document_embeddings: List[List[float]], 
                              top_k: int = 10) -> List[Dict[str, Any]]:
        """Calculate cosine similarity and return top-k results."""
        query_np = np.array(query_embedding)
        similarities = []
        
        for idx, doc_embedding in enumerate(document_embeddings):
            doc_np = np.array(doc_embedding)
            similarity = np.dot(query_np, doc_np) / (np.linalg.norm(query_np) * np.linalg.norm(doc_np))
            similarities.append({
                "index": idx,
                "similarity": float(similarity)
            })
        
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities[:top_k]


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self._init_tokenizer()
    
    def _initialize_client(self):
        try:
            import openai
            return openai.AsyncOpenAI(api_key=self.config.api_key)
        except ImportError:
            raise ImportError("openai package required for OpenAI provider")
    
    def _init_tokenizer(self):
        """Initialize tiktoken for accurate token counting."""
        try:
            import tiktoken
            # cl100k_base is used by text-embedding-3-* models
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
            logger.info("Initialized tiktoken for OpenAI provider")
        except ImportError:
            logger.warning("tiktoken not installed, using character-based estimation")
            self.tokenizer = None

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=self.config.model_name
            )
            return [embedding.embedding for embedding in response.data]
        except Exception as e:
            # Handle specific OpenAI exceptions
            error_message = str(e)
            if "rate_limit_exceeded" in error_message.lower():
                raise EmbeddingAPIError(f"OpenAI rate limit exceeded: {error_message}")
            elif "invalid_api_key" in error_message.lower() or "authentication" in error_message.lower():
                raise EmbeddingAPIError(f"OpenAI authentication failed: {error_message}")
            elif "context_length_exceeded" in error_message.lower():
                raise EmbeddingTokenLimitError(f"OpenAI token limit exceeded: {error_message}")
            else:
                raise EmbeddingProviderError(f"OpenAI API error: {error_message}")

    async def create_single_embedding(self, text: str) -> List[float]:
        embeddings = await self.create_embeddings([text])
        return embeddings[0]
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken if available."""
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Fallback to base class estimation
            return super()._estimate_tokens(text)
    
    def _split_into_batches(self, texts: List[str]) -> List[List[str]]:
        """Split texts into batches with accurate token counting."""
        if not self.tokenizer:
            # Use base class implementation if tiktoken not available
            return super()._split_into_batches(texts)
        
        max_tokens = self.config.max_tokens_per_request or 8191
        max_items = self.config.max_items_per_batch or 2048
        
        batches = []
        current_batch = []
        current_tokens = 0
        
        for text in texts:
            # Use tiktoken for accurate counting
            text_tokens = len(self.tokenizer.encode(text))
            
            # Check if adding this text would exceed limits
            if current_batch and (
                len(current_batch) >= max_items or 
                current_tokens + text_tokens > max_tokens
            ):
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            
            # Skip texts that are too long individually
            if text_tokens > max_tokens:
                logger.warning(f"Text exceeds token limit ({text_tokens} > {max_tokens}), truncating")
                # Truncate the text to fit
                tokens = self.tokenizer.encode(text)[:max_tokens - 100]  # Leave some buffer
                truncated_text = self.tokenizer.decode(tokens)
                current_batch.append(truncated_text)
                current_tokens += len(tokens)
            else:
                current_batch.append(text)
                current_tokens += text_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        return batches


class CohereEmbeddingProvider(BaseEmbeddingProvider):
    def _initialize_client(self):
        import cohere
        return cohere.AsyncClient(api_key=self.config.api_key)

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        response = await self.client.embed(
            texts=texts,
            model=self.config.model_name,
            input_type="search_document"
        )
        return response.embeddings

    async def create_single_embedding(self, text: str) -> List[float]:
        embeddings = await self.create_embeddings([text])
        return embeddings[0]


class HuggingFaceEmbeddingProvider(BaseEmbeddingProvider):
    def _initialize_client(self):
        return httpx.AsyncClient(
            base_url=self.config.api_base or "https://api-inference.huggingface.co",
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            timeout=self.config.timeout
        )

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            response = await self.client.post(
                f"/pipeline/feature-extraction/{self.config.model_name}",
                json={"inputs": text}
            )
            embedding = response.json()
            if isinstance(embedding[0], list):
                # Take mean of token embeddings
                embedding = np.mean(embedding, axis=0).tolist()
            embeddings.append(embedding)
        return embeddings

    async def create_single_embedding(self, text: str) -> List[float]:
        embeddings = await self.create_embeddings([text])
        return embeddings[0]


class LocalSentenceTransformersProvider(BaseEmbeddingProvider):
    def _initialize_client(self):
        if not HAS_ML_DEPS:
            raise ImportError(
                "ML dependencies not installed. Install with: "
                "pip install sentence-transformers torch"
            )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        return SentenceTransformer(self.config.model_name, device=device)

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self.client.encode, texts
        )
        return embeddings.tolist()

    async def create_single_embedding(self, text: str) -> List[float]:
        embeddings = await self.create_embeddings([text])
        return embeddings[0]


class AzureOpenAIEmbeddingProvider(BaseEmbeddingProvider):
    def _initialize_client(self):
        import openai
        return openai.AsyncAzureOpenAI(
            api_key=self.config.api_key,
            api_version="2024-02-01",
            azure_endpoint=self.config.api_base
        )

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        response = await self.client.embeddings.create(
            input=texts,
            model=self.config.model_name
        )
        return [embedding.embedding for embedding in response.data]

    async def create_single_embedding(self, text: str) -> List[float]:
        embeddings = await self.create_embeddings([text])
        return embeddings[0]


class GoogleVertexEmbeddingProvider(BaseEmbeddingProvider):
    def _initialize_client(self):
        from google.cloud import aiplatform
        aiplatform.init()
        return aiplatform

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        from vertexai.language_models import TextEmbeddingModel
        
        # Run in thread pool to avoid blocking event loop
        def _get_embeddings():
            model = TextEmbeddingModel.from_pretrained(self.config.model_name)
            embeddings = []
            
            for text in texts:
                embedding = model.get_embeddings([text])[0]
                embeddings.append(embedding.values)
            
            return embeddings
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get_embeddings)

    async def create_single_embedding(self, text: str) -> List[float]:
        embeddings = await self.create_embeddings([text])
        return embeddings[0]


class AnthropicEmbeddingProvider(BaseEmbeddingProvider):
    """
    Anthropic Claude provider - delegates to another embedding provider.
    Since Anthropic doesn't provide embeddings API, this implementation:
    1. Uses Claude for text analysis/summarization
    2. Delegates actual embedding to another provider (default: local)
    """
    
    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        # Initialize fallback embedding provider
        self._init_fallback_provider()
    
    def _initialize_client(self):
        try:
            import anthropic
            return anthropic.AsyncAnthropic(api_key=self.config.api_key)
        except ImportError:
            raise ImportError("anthropic package required for Anthropic provider")
    
    def _init_fallback_provider(self):
        """Initialize a fallback embedding provider."""
        if HAS_ML_DEPS:
            self.fallback_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Anthropic provider using local Sentence Transformers for embeddings")
        else:
            self.fallback_model = None
            logger.warning("ML dependencies not available for fallback embeddings")

    async def create_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Process texts with Claude first, then create embeddings.
        This provides Claude's understanding with actual vector representations.
        """
        processed_texts = []
        
        for text in texts:
            try:
                # Use Claude for intelligent text processing (optional)
                if len(text) > 500:  # Only process long texts
                    message = await self.client.messages.create(
                        model=self.config.model_name or "claude-3-haiku-20240307",
                        max_tokens=150,
                        messages=[{
                            "role": "user",
                            "content": f"Summarize the key concepts in this text in one paragraph: {text[:2000]}"
                        }]
                    )
                    processed_text = message.content[0].text
                else:
                    processed_text = text
                
                processed_texts.append(processed_text)
                
            except Exception as e:
                logger.warning(f"Claude processing failed, using original text: {e}")
                processed_texts.append(text)
        
        # Generate actual embeddings using fallback model
        if self.fallback_model is None:
            raise EmbeddingProviderError(
                "Fallback model not available. Install ML dependencies: "
                "pip install sentence-transformers torch"
            )
        
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, self.fallback_model.encode, processed_texts
        )
        
        return embeddings.tolist()

    async def create_single_embedding(self, text: str) -> List[float]:
        embeddings = await self.create_embeddings([text])
        return embeddings[0]


class EmbeddingProviderFactory:
    """Factory for creating embedding providers."""
    
    _providers = {
        EmbeddingProvider.OPENAI: OpenAIEmbeddingProvider,
        EmbeddingProvider.COHERE: CohereEmbeddingProvider,
        EmbeddingProvider.HUGGINGFACE: HuggingFaceEmbeddingProvider,
        EmbeddingProvider.AZURE_OPENAI: AzureOpenAIEmbeddingProvider,
        EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS: LocalSentenceTransformersProvider,
        EmbeddingProvider.GOOGLE_VERTEX: GoogleVertexEmbeddingProvider,
        EmbeddingProvider.ANTHROPIC_CLAUDE: AnthropicEmbeddingProvider,
    }

    @classmethod
    def create_provider(cls, config: EmbeddingConfig) -> BaseEmbeddingProvider:
        provider_class = cls._providers.get(config.provider)
        if not provider_class:
            raise ValueError(f"Unsupported embedding provider: {config.provider}")
        
        return provider_class(config)

    @classmethod
    def get_default_configs(cls) -> Dict[EmbeddingProvider, EmbeddingConfig]:
        """Get default configurations for each provider."""
        return {
            EmbeddingProvider.OPENAI: EmbeddingConfig(
                provider=EmbeddingProvider.OPENAI,
                model_name="text-embedding-3-large",
                dimensions=3072,
                batch_size=100,
                max_tokens_per_request=8191,  # OpenAI limit
                max_items_per_batch=2048,     # OpenAI batch limit
                rate_limit_rpm=10000          # Tier 5 limit
            ),
            EmbeddingProvider.COHERE: EmbeddingConfig(
                provider=EmbeddingProvider.COHERE,
                model_name="embed-english-v3.0",
                dimensions=1024,
                batch_size=96,
                max_tokens_per_request=None,  # No strict token limit
                max_items_per_batch=96,       # Cohere recommends 96
                rate_limit_rpm=10000          # Production limit
            ),
            EmbeddingProvider.HUGGINGFACE: EmbeddingConfig(
                provider=EmbeddingProvider.HUGGINGFACE,
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                dimensions=384
            ),
            EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS: EmbeddingConfig(
                provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS,
                model_name="all-MiniLM-L6-v2",
                dimensions=384
            ),
            EmbeddingProvider.GOOGLE_VERTEX: EmbeddingConfig(
                provider=EmbeddingProvider.GOOGLE_VERTEX,
                model_name="textembedding-gecko@003",
                dimensions=768
            ),
            EmbeddingProvider.ANTHROPIC_CLAUDE: EmbeddingConfig(
                provider=EmbeddingProvider.ANTHROPIC_CLAUDE,
                model_name="claude-3-haiku-20240307",
                dimensions=384,
                batch_size=20  # Lower batch size due to API costs
            )
        }