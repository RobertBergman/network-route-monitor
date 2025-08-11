"""Database models and connection setup for route monitoring system."""

import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean, LargeBinary, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.postgresql import JSONB
from cryptography.fernet import Fernet

Base = declarative_base()


def get_encryption_key() -> bytes:
    """Get or generate encryption key for passwords."""
    key_file = ".encryption_key"
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, "wb") as f:
            f.write(key)
        os.chmod(key_file, 0o600)
        return key


class PasswordEncryption:
    """Handle password encryption/decryption."""
    
    def __init__(self):
        self.cipher = Fernet(get_encryption_key())
    
    def encrypt(self, password: str) -> bytes:
        """Encrypt a password."""
        return self.cipher.encrypt(password.encode())
    
    def decrypt(self, encrypted_password: bytes) -> str:
        """Decrypt a password."""
        return self.cipher.decrypt(encrypted_password).decode()


password_encryption = PasswordEncryption()


class Device(Base):
    """Network device configuration."""
    __tablename__ = "devices"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    hostname = Column(String(255), nullable=False)
    device_type = Column(String(50), nullable=False)
    username = Column(String(100), nullable=False)
    encrypted_password = Column(LargeBinary, nullable=False)
    port = Column(Integer, default=22)
    use_nxapi = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    snapshots = relationship("RouteSnapshot", back_populates="device", cascade="all, delete-orphan")
    bgp_snapshots = relationship("BGPSnapshot", back_populates="device", cascade="all, delete-orphan")
    
    @property
    def password(self) -> str:
        """Get decrypted password."""
        return password_encryption.decrypt(self.encrypted_password)
    
    @password.setter
    def password(self, value: str):
        """Set encrypted password."""
        self.encrypted_password = password_encryption.encrypt(value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format expected by netmiko."""
        return {
            "name": self.name,
            "host": self.hostname,  # netmiko expects 'host' not 'hostname'
            "device_type": self.device_type,
            "username": self.username,
            "password": self.password,
            "port": self.port,
            "use_nxapi": self.use_nxapi,
        }


class RouteSnapshot(Base):
    """RIB route snapshot."""
    __tablename__ = "route_snapshots"
    __table_args__ = (
        Index("idx_route_device_vrf_afi_ts", "device_id", "vrf", "afi", "timestamp"),
    )
    
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    vrf = Column(String(100), nullable=False)
    afi = Column(String(10), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    data = Column(JSONB, nullable=False)
    route_count = Column(Integer, nullable=False)
    
    device = relationship("Device", back_populates="snapshots")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "device": self.device.name,
            "vrf": self.vrf,
            "afi": self.afi,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "route_count": self.route_count,
        }


class BGPSnapshot(Base):
    """BGP route snapshot."""
    __tablename__ = "bgp_snapshots"
    __table_args__ = (
        Index("idx_bgp_device_vrf_afi_ts", "device_id", "vrf", "afi", "timestamp"),
    )
    
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    vrf = Column(String(100), nullable=False)
    afi = Column(String(10), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    data = Column(JSONB, nullable=False)
    route_count = Column(Integer, nullable=False)
    
    device = relationship("Device", back_populates="bgp_snapshots")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "device": self.device.name,
            "vrf": self.vrf,
            "afi": self.afi,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "route_count": self.route_count,
        }


class RouteDiff(Base):
    """Route change diff."""
    __tablename__ = "route_diffs"
    __table_args__ = (
        Index("idx_diff_device_vrf_afi_ts", "device_id", "vrf", "afi", "timestamp"),
    )
    
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    vrf = Column(String(100), nullable=False)
    afi = Column(String(10), nullable=False)
    table_type = Column(String(10), nullable=False)  # "rib" or "bgp"
    timestamp = Column(DateTime, nullable=False, index=True)
    added = Column(JSONB, default=list)
    removed = Column(JSONB, default=list)
    changed = Column(JSONB, default=list)
    
    device = relationship("Device")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "device": self.device.name,
            "vrf": self.vrf,
            "afi": self.afi,
            "table_type": self.table_type,
            "timestamp": self.timestamp.isoformat(),
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
        }


def get_db_url() -> str:
    """Get database URL from environment or use default."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://routemonitor:routemonitor@localhost/routemonitor"
    )


def get_session() -> Session:
    """Get database session."""
    engine = create_engine(get_db_url())
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def init_db():
    """Initialize database tables."""
    engine = create_engine(get_db_url())
    Base.metadata.create_all(engine)
    print(f"Database initialized at {get_db_url()}")