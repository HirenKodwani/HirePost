from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDMixin


class Prompt(UUIDMixin, TimestampMixin, Base):
    script_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("script.id"), nullable=True
    )
    scene_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("scene.id"), nullable=True
    )
    prompt_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    optimized_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_optimized: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    version: Mapped[int] = mapped_column(Integer, default=1)

    script = relationship("Script", back_populates="prompts")
    scene = relationship("Scene", back_populates="prompts")


class Asset(UUIDMixin, TimestampMixin, Base):
    scene_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("scene.id"), nullable=True
    )
    asset_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_royalty_free: Mapped[bool] = mapped_column(Boolean, default=True)
    license_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    attribution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scene = relationship("Scene", back_populates="assets")
    video_clips = relationship("VideoClip", back_populates="asset")


class Image(UUIDMixin, TimestampMixin, Base):
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    prompt_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)


class Video(UUIDMixin, TimestampMixin, Base):
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[int] = mapped_column(Integer, default=1080)
    height: Mapped[int] = mapped_column(Integer, default=1920)
    fps: Mapped[float] = mapped_column(Float, default=30.0)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    published_platform: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    seo_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hashtags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project = relationship("Project", back_populates="videos")
    clips = relationship("VideoClip", back_populates="video", cascade="all, delete-orphan")


class VideoClip(UUIDMixin, TimestampMixin, Base):
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("video.id"), nullable=False
    )
    asset_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("asset.id"), nullable=True
    )
    clip_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_time: Mapped[float] = mapped_column(Float, default=0.0)
    end_time: Mapped[float] = mapped_column(Float, default=0.0)
    layer: Mapped[int] = mapped_column(Integer, default=0)
    opacity: Mapped[float] = mapped_column(Float, default=1.0)
    position_x: Mapped[float] = mapped_column(Float, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, default=0.0)
    scale_x: Mapped[float] = mapped_column(Float, default=1.0)
    scale_y: Mapped[float] = mapped_column(Float, default=1.0)
    rotation: Mapped[float] = mapped_column(Float, default=0.0)
    effects_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    video = relationship("Video", back_populates="clips")
    asset = relationship("Asset", back_populates="video_clips")


class Voice(UUIDMixin, TimestampMixin, Base):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_cloned: Mapped[bool] = mapped_column(Boolean, default=False)
    clone_source_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sample_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False)


class Music(UUIDMixin, TimestampMixin, Base):
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mood: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tempo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_royalty_free: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)


class Subtitle(UUIDMixin, TimestampMixin, Base):
    video_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("video.id"), nullable=True
    )
    language: Mapped[str] = mapped_column(String(10), default="en")
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    format_type: Mapped[str] = mapped_column(String(50), default="srt")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_burned_in: Mapped[bool] = mapped_column(Boolean, default=False)
    style_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class YouTubeAccount(UUIDMixin, TimestampMixin, Base):
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    channel_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    quota_used_today: Mapped[int] = mapped_column(Integer, default=0)
    quota_reset_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_upload_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_count: Mapped[int] = mapped_column(Integer, default=0)
    oauth_config: Mapped[str] = mapped_column(String(50), default="default")


class Thumbnail(UUIDMixin, TimestampMixin, Base):
    video_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("video.id"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    prompt_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    click_prediction: Mapped[float] = mapped_column(Float, default=0.0)
