# -*- coding: utf-8 -*-

"""The one value type the guardrail passes around."""

from typing import NamedTuple


class Finding(NamedTuple):
    """A detected span. Deliberately the same shape presidio's RecognizerResult
    exposes (entity_type/start/end), so a presidio analyzer could be plugged in
    as an extra detector later without changing anything downstream."""

    entity_type: str
    start: int
    end: int
