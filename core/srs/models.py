from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class WordCard:
    word: str
    slug: str
    category: str
    meaning: str
    pronunciation: str
    example: str
    details: str = ""

@dataclass
class CardProgress:
    box: int = 1  # Cajas Leitner 1..5
    interval_days: int = 1
    last_reviewed: Optional[str] = None
    next_review: str = field(default_factory=lambda: datetime.now().isoformat())
    consecutive_correct: int = 0
    lapses: int = 0

@dataclass
class UserStats:
    total_xp: int = 0
    current_streak: int = 0
    last_study_date: Optional[str] = None
    cards_mastered: int = 0
    total_reviews: int = 0
