"""
Validation Policy Signing System
명명 규칙 정책의 무결성과 신뢰성을 보장하는 서명 시스템
"""
import hashlib
import hmac
import json
import base64
import secrets
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Tuple
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from pydantic import BaseModel, Field
from enum import Enum

from core.validation.naming_convention import NamingConvention
from utils.logger import get_logger

logger = get_logger(__name__)


class SignatureAlgorithm(str, Enum):
    """지원하는 서명 알고리즘"""
    HMAC_SHA256 = "HMAC-SHA256"
    RSA_PSS_SHA256 = "RSA-PSS-SHA256"
    RSA_PKCS1_SHA256 = "RSA-PKCS1-SHA256"


class PolicySignature(BaseModel):
    """정책 서명 정보"""
    algorithm: SignatureAlgorithm
    signature: str
    timestamp: str
    signer: str
    policy_hash: str
    key_id: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class SignedNamingPolicy(BaseModel):
    """서명된 명명 규칙 정책"""
    policy: NamingConvention
    signature: PolicySignature
    integrity_hash: str  # 전체 정책의 해시값
    
    def verify_integrity(self) -> bool:
        """무결성 검증"""
        current_hash = self._calculate_policy_hash()
        return current_hash == self.integrity_hash
    
    def _calculate_policy_hash(self) -> str:
        """정책 해시 계산"""
        policy_dict = self.policy.model_dump()
        policy_json = json.dumps(policy_dict, sort_keys=True, default=str)
        return hashlib.sha256(policy_json.encode()).hexdigest()


class PolicySigner:
    """정책 서명 및 검증 클래스"""
    
    def __init__(
        self,
        hmac_secret: Optional[str] = None,
        private_key_path: Optional[str] = None,
        public_key_path: Optional[str] = None,
        key_id: Optional[str] = None
    ):
        """
        초기화
        
        Args:
            hmac_secret: HMAC 서명용 비밀키
            private_key_path: RSA 개인키 파일 경로
            public_key_path: RSA 공개키 파일 경로  
            key_id: 키 식별자
        """
        self.hmac_secret = hmac_secret
        self.private_key_path = private_key_path
        self.public_key_path = public_key_path
        self.key_id = key_id
        
        # 키 로드
        self._private_key = None
        self._public_key = None
        self._load_keys()
    
    def _load_keys(self):
        """RSA 키 로드"""
        if self.private_key_path and Path(self.private_key_path).exists():
            try:
                with open(self.private_key_path, 'rb') as f:
                    self._private_key = load_pem_private_key(f.read(), password=None)
                logger.info(f"Loaded private key from {self.private_key_path}")
            except Exception as e:
                logger.error(f"Failed to load private key: {e}")
        
        if self.public_key_path and Path(self.public_key_path).exists():
            try:
                with open(self.public_key_path, 'rb') as f:
                    self._public_key = load_pem_public_key(f.read())
                logger.info(f"Loaded public key from {self.public_key_path}")
            except Exception as e:
                logger.error(f"Failed to load public key: {e}")
    
    def generate_rsa_keypair(self, key_size: int = 2048) -> Tuple[str, str]:
        """
        RSA 키 쌍 생성
        
        Args:
            key_size: 키 크기 (bits)
            
        Returns:
            (private_key_pem, public_key_pem) 튜플
        """
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size
        )
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()
        
        return private_pem, public_pem
    
    def sign_policy(
        self,
        policy: NamingConvention,
        algorithm: SignatureAlgorithm,
        signer: str
    ) -> SignedNamingPolicy:
        """
        정책 서명
        
        Args:
            policy: 서명할 명명 규칙 정책
            algorithm: 사용할 서명 알고리즘
            signer: 서명자 정보
            
        Returns:
            서명된 정책
            
        Raises:
            ValueError: 지원하지 않는 알고리즘이나 키가 없는 경우
        """
        # 정책을 JSON으로 직렬화 (정렬된 순서)
        policy_dict = policy.model_dump()
        policy_json = json.dumps(policy_dict, sort_keys=True, default=str)
        policy_bytes = policy_json.encode('utf-8')
        
        # 정책 해시 계산
        policy_hash = hashlib.sha256(policy_bytes).hexdigest()
        
        # 서명 생성
        signature_data = self._create_signature(policy_bytes, algorithm)
        
        # 서명 정보 생성
        signature = PolicySignature(
            algorithm=algorithm,
            signature=signature_data,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signer=signer,
            policy_hash=policy_hash,
            key_id=self.key_id
        )
        
        # 서명된 정책 생성
        signed_policy = SignedNamingPolicy(
            policy=policy,
            signature=signature,
            integrity_hash=policy_hash
        )
        
        logger.info(f"Policy signed with {algorithm.value} by {signer}")
        return signed_policy
    
    def verify_policy(self, signed_policy: SignedNamingPolicy) -> bool:
        """
        정책 서명 검증
        
        Args:
            signed_policy: 검증할 서명된 정책
            
        Returns:
            검증 성공 여부
        """
        try:
            # 1. 무결성 검증
            if not signed_policy.verify_integrity():
                logger.error("Policy integrity check failed")
                return False
            
            # 2. 정책 직렬화
            policy_dict = signed_policy.policy.model_dump()
            policy_json = json.dumps(policy_dict, sort_keys=True, default=str)
            policy_bytes = policy_json.encode('utf-8')
            
            # 3. 서명 검증
            is_valid = self._verify_signature(
                policy_bytes,
                signed_policy.signature.signature,
                signed_policy.signature.algorithm
            )
            
            if is_valid:
                logger.info(f"Policy signature verified for signer: {signed_policy.signature.signer}")
            else:
                logger.error("Policy signature verification failed")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Policy verification error: {e}")
            return False
    
    def _create_signature(self, data: bytes, algorithm: SignatureAlgorithm) -> str:
        """서명 생성"""
        if algorithm == SignatureAlgorithm.HMAC_SHA256:
            if not self.hmac_secret:
                raise ValueError("HMAC secret not configured")
            
            signature = hmac.new(
                self.hmac_secret.encode(),
                data,
                hashlib.sha256
            ).digest()
            return base64.b64encode(signature).decode()
        
        elif algorithm == SignatureAlgorithm.RSA_PSS_SHA256:
            if not self._private_key:
                raise ValueError("RSA private key not loaded")
            
            signature = self._private_key.sign(
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode()
        
        elif algorithm == SignatureAlgorithm.RSA_PKCS1_SHA256:
            if not self._private_key:
                raise ValueError("RSA private key not loaded")
            
            signature = self._private_key.sign(
                data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode()
        
        else:
            raise ValueError(f"Unsupported signature algorithm: {algorithm}")
    
    def _verify_signature(
        self,
        data: bytes,
        signature: str,
        algorithm: SignatureAlgorithm
    ) -> bool:
        """서명 검증"""
        try:
            signature_bytes = base64.b64decode(signature)
            
            if algorithm == SignatureAlgorithm.HMAC_SHA256:
                if not self.hmac_secret:
                    raise ValueError("HMAC secret not configured")
                
                expected_signature = hmac.new(
                    self.hmac_secret.encode(),
                    data,
                    hashlib.sha256
                ).digest()
                return hmac.compare_digest(signature_bytes, expected_signature)
            
            elif algorithm == SignatureAlgorithm.RSA_PSS_SHA256:
                if not self._public_key:
                    raise ValueError("RSA public key not loaded")
                
                self._public_key.verify(
                    signature_bytes,
                    data,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
                return True
            
            elif algorithm == SignatureAlgorithm.RSA_PKCS1_SHA256:
                if not self._public_key:
                    raise ValueError("RSA public key not loaded")
                
                self._public_key.verify(
                    signature_bytes,
                    data,
                    padding.PKCS1v15(),
                    hashes.SHA256()
                )
                return True
            
            else:
                raise ValueError(f"Unsupported signature algorithm: {algorithm}")
                
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False


class PolicySigningManager:
    """정책 서명 관리자"""
    
    def __init__(self, config_path: str = "/etc/oms/signing"):
        """
        초기화
        
        Args:
            config_path: 서명 설정 디렉토리 경로
        """
        self.config_path = Path(config_path)
        self.config_path.mkdir(parents=True, exist_ok=True)
        
        # 설정 로드
        self.config = self._load_config()
        
        # 서명자 초기화
        self.signer = PolicySigner(
            hmac_secret=self.config.get('hmac_secret'),
            private_key_path=self.config.get('private_key_path'),
            public_key_path=self.config.get('public_key_path'),
            key_id=self.config.get('key_id')
        )
    
    def _load_config(self) -> Dict[str, Any]:
        """서명 설정 로드"""
        config_file = self.config_path / "signing_config.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load signing config: {e}")
        
        # 기본 설정 생성
        default_config = {
            "hmac_secret": secrets.token_urlsafe(32),
            "key_id": f"oms-{secrets.token_hex(8)}",
            "default_algorithm": SignatureAlgorithm.HMAC_SHA256.value
        }
        
        self._save_config(default_config)
        return default_config
    
    def _save_config(self, config: Dict[str, Any]):
        """서명 설정 저장"""
        config_file = self.config_path / "signing_config.json"
        
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Signing config saved to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save signing config: {e}")
    
    def setup_rsa_keys(self, key_size: int = 2048) -> bool:
        """
        RSA 키 쌍 설정
        
        Args:
            key_size: RSA 키 크기
            
        Returns:
            설정 성공 여부
        """
        try:
            # 키 쌍 생성
            private_pem, public_pem = self.signer.generate_rsa_keypair(key_size)
            
            # 키 파일 저장
            private_key_path = self.config_path / "private_key.pem"
            public_key_path = self.config_path / "public_key.pem"
            
            with open(private_key_path, 'w') as f:
                f.write(private_pem)
            
            with open(public_key_path, 'w') as f:
                f.write(public_pem)
            
            # 파일 권한 설정 (private key는 owner만 읽기 가능)
            private_key_path.chmod(0o600)
            public_key_path.chmod(0o644)
            
            # 설정 업데이트
            self.config.update({
                'private_key_path': str(private_key_path),
                'public_key_path': str(public_key_path),
                'default_algorithm': SignatureAlgorithm.RSA_PSS_SHA256.value
            })
            self._save_config(self.config)
            
            # 서명자 재초기화
            self.signer = PolicySigner(
                hmac_secret=self.config.get('hmac_secret'),
                private_key_path=str(private_key_path),
                public_key_path=str(public_key_path),
                key_id=self.config.get('key_id')
            )
            
            logger.info(f"RSA keys generated and saved to {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup RSA keys: {e}")
            return False
    
    def sign_policy(
        self,
        policy: NamingConvention,
        signer: str,
        algorithm: Optional[SignatureAlgorithm] = None
    ) -> SignedNamingPolicy:
        """정책 서명"""
        if not algorithm:
            algorithm = SignatureAlgorithm(self.config.get('default_algorithm', 'HMAC-SHA256'))
        
        return self.signer.sign_policy(policy, algorithm, signer)
    
    def verify_policy(self, signed_policy: SignedNamingPolicy) -> bool:
        """정책 서명 검증"""
        return self.signer.verify_policy(signed_policy)
    
    def save_signed_policy(self, signed_policy: SignedNamingPolicy, filename: str):
        """서명된 정책 저장"""
        policy_file = self.config_path / filename
        
        try:
            with open(policy_file, 'w') as f:
                json.dump(signed_policy.model_dump(), f, indent=2, default=str)
            logger.info(f"Signed policy saved to {policy_file}")
        except Exception as e:
            logger.error(f"Failed to save signed policy: {e}")
    
    def load_signed_policy(self, filename: str) -> Optional[SignedNamingPolicy]:
        """서명된 정책 로드"""
        policy_file = self.config_path / filename
        
        if not policy_file.exists():
            return None
        
        try:
            with open(policy_file, 'r') as f:
                data = json.load(f)
            
            # 수동으로 복원 (Pydantic의 복잡한 중첩 구조 때문)
            policy_data = data['policy']
            signature_data = data['signature']
            
            # NamingConvention 복원
            rules = {}
            for entity_type_str, rule_data in policy_data.get('rules', {}).items():
                from core.validation.naming_convention import EntityType, NamingPattern, NamingRule
                entity_type = EntityType(entity_type_str)
                rule_data['entity_type'] = entity_type
                rule_data['pattern'] = NamingPattern(rule_data['pattern'])
                rules[entity_type] = NamingRule(**rule_data)
            
            policy_data['rules'] = rules
            policy = NamingConvention(**policy_data)
            
            # PolicySignature 복원
            signature = PolicySignature(**signature_data)
            
            signed_policy = SignedNamingPolicy(
                policy=policy,
                signature=signature,
                integrity_hash=data['integrity_hash']
            )
            
            logger.info(f"Signed policy loaded from {policy_file}")
            return signed_policy
            
        except Exception as e:
            logger.error(f"Failed to load signed policy: {e}")
            return None


# 싱글톤 인스턴스
_signing_manager = None

def get_policy_signing_manager(config_path: Optional[str] = None) -> PolicySigningManager:
    """정책 서명 관리자 인스턴스 반환"""
    global _signing_manager
    if not _signing_manager or config_path:
        _signing_manager = PolicySigningManager(config_path or "/etc/oms/signing")
    return _signing_manager