"""Fast forced alignment of single recordings. See README.md."""

from .aligner import Aligner, Alignment, AlignmentError, Interval

__version__ = '0.0.1'
__all__ = ['Aligner', 'Alignment', 'AlignmentError', 'Interval']
