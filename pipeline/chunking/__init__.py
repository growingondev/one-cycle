"""Structure-aware chunking package for normalized HWP/HWPX JSON."""

from .chunker import StructureAwareChunker
from .config import ChunkingConfig

__all__ = ["StructureAwareChunker", "ChunkingConfig"]
